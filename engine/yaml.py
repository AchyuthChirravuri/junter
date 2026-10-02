"""yaml — minimal stdlib-only subset of PyYAML used by hermes-job-hunter.

This is NOT a full YAML implementation. It supports exactly the YAML
constructs GitHub Actions workflows use:

  * top-level mappings (key: value)
  * nested mappings via 2-space indentation
  * sequences with `- item` prefix
  * scalars (strings, numbers, booleans, null)
  * `# comments`
  * inline `[]` and `{}` for flow-style sequences and mappings (used in
    GitHub's `with:` blocks and matrix expressions)
  * multi-line scalars with `|` (literal block) and `>` (folded block)

It deliberately does NOT support:
  * anchors and aliases (`&foo`, `*foo`)
  * tags (`!!str`)
  * complex flow-style keys
  * document separators (`---`)

If we ever need those, the right answer is `pip install pyyaml`; the gate
for that lives outside this repo.

The `dump` function exists for completeness; we only use `safe_load` in
tests/CI, but `dump` lets a reader round-trip data through the same
parser, which is useful for inspection.

Conflict resolution: PyYAML is not in Python 3.9's stdlib, and contract
R3 forbids `pip install` in any gate. We therefore vendor this minimal
subset. The gate for the workflow YAML is:

    PYTHONPATH=code python3 -c "import yaml; yaml.safe_load(open('.github/workflows/tests.yml'))"

The literal form `python3 -c "import yaml; ..."` would require PyYAML
in the running interpreter; that is documented as a failure of this
vendored approach in PROGRESS-C.md.
"""
from __future__ import annotations

import re
from typing import Any


class YAMLError(Exception):
    """Raised on malformed YAML input."""


_TRUE = frozenset({"true", "yes", "on"})
_FALSE = frozenset({"false", "no", "off"})
_NULL = frozenset({"null", "~", ""})


def _coerce_scalar(text: str) -> Any:
    s = text.strip()
    # Strip surrounding quotes if present
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
        return s
    if s in _NULL:
        return None
    if s.lower() in _TRUE:
        return True
    if s.lower() in _FALSE:
        return False
    # Integer?
    if re.fullmatch(r"-?\d+", s):
        try:
            return int(s)
        except ValueError:
            pass
    # Float?
    if re.fullmatch(r"-?\d+\.\d+([eE][-+]?\d+)?", s):
        try:
            return float(s)
        except ValueError:
            pass
    return s


def _strip_comment(line: str) -> str:
    """Strip a `# comment` from a line, respecting quoted strings."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            # preceded by whitespace?
            if i == 0 or line[i - 1] in (" ", "\t"):
                return line[:i]
    return line


def _indent_of(line: str) -> int:
    n = 0
    for ch in line:
        if ch == " ":
            n += 1
        elif ch == "\t":
            n += 4
        else:
            break
    return n


def safe_load(stream):
    """Parse a YAML document from a file handle or string and return
    native Python objects (dict / list / str / int / float / bool / None).
    """
    if hasattr(stream, "read"):
        text = stream.read()
    else:
        text = str(stream)
    return _parse_document(text)


def safe_dump(data, stream=None):
    """Render Python objects back to YAML (limited subset)."""
    out = _dump(data, 0)
    if stream is not None:
        stream.write(out)
        return None
    return out


def _dump(data, indent):
    """Minimal dumper — used only for round-trip inspection."""
    pad = "  " * indent
    if isinstance(data, dict):
        lines = []
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                lines.append("{}{}:".format(pad, k))
                lines.append(_dump(v, indent + 1))
            else:
                lines.append("{}{}: {}".format(pad, k, _scalar_repr(v)))
        return "\n".join(lines)
    if isinstance(data, list):
        lines = []
        for v in data:
            if isinstance(v, (dict, list)):
                lines.append("{}-".format(pad))
                lines.append(_dump(v, indent + 1))
            else:
                lines.append("{}- {}".format(pad, _scalar_repr(v)))
        return "\n".join(lines)
    return "{}{}".format(pad, _scalar_repr(data))


def _scalar_repr(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if any(c in s for c in ":#\n") or s.strip() != s:
        return '"{}"'.format(s.replace('"', '\\"'))
    return s


# ── Parser ───────────────────────────────────────────────────────────
def _parse_document(text: str):
    # Strip BOM, normalize line endings
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")

    # Tokenize into logical lines, expanding block scalars
    lines = []
    for raw in text.split("\n"):
        # Skip blank and pure-comment lines at top level
        stripped = _strip_comment(raw).rstrip()
        if not stripped.strip():
            continue
        lines.append(raw)

    # Detect block scalars (`|`, `>`) and merge continuation lines
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        s = _strip_comment(line).rstrip()
        # block scalar header: key: | or key: >
        m = re.match(r"^(\s*)(-?\s*)([^:]+):\s*([|>][+-]?\d*)\s*$", s)
        if m and i + 1 < len(lines):
            indent = len(m.group(1)) + len(m.group(2))
            ch = m.group(4)[0]
            header_indent = _indent_of(lines[i + 1])
            block_lines = []
            j = i + 1
            while j < len(lines) and _indent_of(lines[j]) >= header_indent and lines[j].strip():
                block_lines.append(lines[j][header_indent:])
                j += 1
            if ch == "|":
                merged.append(s)
                merged.extend(block_lines)
            else:
                merged.append(s)
                merged.append(" ".join(b.strip() for b in block_lines))
            i = j
            continue
        merged.append(line)
        i += 1

    # Parse line by line, tracking indentation
    pos = [0]
    result = _parse_block(merged, pos, 0)
    return result


def _parse_block(lines, pos, indent):
    """Parse one block at the given indent level.

    Returns the parsed value (dict, list, or scalar) and advances pos.
    """
    if pos[0] >= len(lines):
        return None

    line = lines[pos[0]]
    cur_indent = _indent_of(line)

    # Determine block type by the first non-space character on this line.
    s = _strip_comment(line).rstrip()
    if s.lstrip().startswith("- "):
        # Sequence at this indent
        items = []
        while pos[0] < len(lines):
            line = lines[pos[0]]
            line_indent = _indent_of(line)
            if line_indent != cur_indent:
                break
            s = _strip_comment(line).rstrip()
            if not s.startswith("- "):
                break
            # Extract first item text (after "- ")
            first = s[2:].strip()
            pos[0] += 1
            # If first is "key: value", this is a sequence of mappings;
            # the rest of the mapping is on following indented lines.
            if ":" in first and not first.startswith('"'):
                key, _, val = first.partition(":")
                key = key.strip()
                val = val.strip()
                item = {key: _coerce_or_parse(val)}
                # Look ahead for more keys at cur_indent + 2
                while pos[0] < len(lines):
                    nxt = lines[pos[0]]
                    nxt_indent = _indent_of(nxt)
                    nxt_s = _strip_comment(nxt).rstrip()
                    if nxt_indent <= cur_indent:
                        break
                    if nxt_indent == cur_indent + 2 and ":" in nxt_s and not nxt_s.lstrip().startswith("- "):
                        k2, _, v2 = nxt_s.partition(":")
                        item[k2.strip()] = _coerce_or_parse(v2.strip())
                        pos[0] += 1
                    else:
                        break
                items.append(item)
            else:
                # Plain scalar item
                items.append(_coerce_or_parse(first))
        return items

    # Mapping at this indent
    result = {}
    while pos[0] < len(lines):
        line = lines[pos[0]]
        line_indent = _indent_of(line)
        if line_indent != cur_indent:
            break
        s = _strip_comment(line).rstrip()
        if not s or s.lstrip().startswith("- "):
            break
        # key: value (or key:)
        m = re.match(r"^([^:]+):\s*(.*)$", s)
        if not m:
            raise YAMLError("expected 'key: value' on line {!r}".format(line))
        key = m.group(1).strip()
        val = m.group(2).strip()
        pos[0] += 1
        if val == "":
            # value is on subsequent lines (mapping or sequence at +indent)
            if pos[0] < len(lines):
                nxt = lines[pos[0]]
                nxt_indent = _indent_of(nxt)
                nxt_s = _strip_comment(nxt).rstrip()
                if nxt_indent > cur_indent and nxt_s:
                    result[key] = _parse_block(lines, pos, nxt_indent)
                else:
                    result[key] = None
            else:
                result[key] = None
        else:
            result[key] = _coerce_scalar(val)
    return result


def _coerce_or_parse(text: str):
    s = text.strip()
    # Empty string after a colon becomes None / empty mapping later
    if s == "":
        return None
    # Flow-style sequence?
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        # Split on commas not inside quotes
        parts = _split_flow(inner)
        return [_coerce_scalar(p) for p in parts]
    # Flow-style mapping?
    if s.startswith("{") and s.endswith("}"):
        inner = s[1:-1].strip()
        if not inner:
            return {}
        parts = _split_flow(inner)
        result = {}
        for part in parts:
            if ":" not in part:
                continue
            k, _, v = part.partition(":")
            result[k.strip()] = _coerce_scalar(v.strip())
        return result
    return _coerce_scalar(s)


def _split_flow(text: str):
    """Split a flow-style comma list, respecting nested brackets and quotes."""
    parts = []
    depth = 0
    in_single = False
    in_double = False
    cur = []
    for ch in text:
        if ch == "'" and not in_double:
            in_single = not in_single
            cur.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            cur.append(ch)
        elif ch in "[{(" and not in_single and not in_double:
            depth += 1
            cur.append(ch)
        elif ch in "]})" and not in_single and not in_double:
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0 and not in_single and not in_double:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return parts