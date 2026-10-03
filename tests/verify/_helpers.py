"""Shared, stdlib-only helpers for Junter's pre-deploy verification gates."""
from __future__ import annotations

import json
import re
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui"
DOCS = ROOT / "docs"
FIGMA_EXPORT = DOCS / "ui-evidence" / "figma-refresh-2026-10-03" / "export.json"
SEED = ROOT / "synthetic-data" / "seed.json"


def line_number(path: Path, needle: str) -> int:
    """Return a useful 1-indexed line number for an actionable test failure."""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if needle in line:
            return number
    return 1


def actionable(case, path: Path, needle: str, actual, expected, hint: str) -> None:
    case.fail(
        f"{path.relative_to(ROOT)}:{line_number(path, needle)}\n"
        f"actual: {actual!r}\nexpected: {expected!r}\nfix: {hint}"
    )


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(f"{path.relative_to(ROOT)}:1\nactual: unreadable JSON ({exc})\nexpected: valid JSON\nfix: regenerate or repair this synthetic fixture")


def normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def png_rgba(path: Path):
    """Decode a non-interlaced 8-bit RGB/RGBA PNG using only the stdlib."""
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{path.relative_to(ROOT)}:1\nactual: not a PNG\nexpected: PNG screenshot\nfix: recapture the named screen as PNG")
    offset, chunks = 8, []
    while offset < len(raw):
        size = struct.unpack(">I", raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        payload = raw[offset + 8:offset + 8 + size]
        chunks.append((kind, payload))
        offset += 12 + size
    header = next(payload for kind, payload in chunks if kind == b"IHDR")
    width, height, depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", header)
    if (depth, color_type, compression, filtering, interlace) not in {(8, 2, 0, 0, 0), (8, 6, 0, 0, 0)}:
        raise AssertionError(f"{path.relative_to(ROOT)}:1\nactual: PNG format {(depth, color_type, interlace)}\nexpected: non-interlaced 8-bit RGB/RGBA\nfix: export a standard PNG screenshot")
    channels = 4 if color_type == 6 else 3
    packed = zlib.decompress(b"".join(payload for kind, payload in chunks if kind == b"IDAT"))
    stride = width * channels
    rows, previous, cursor = [], bytearray(stride), 0
    for _ in range(height):
        filter_type = packed[cursor]
        cursor += 1
        scan = bytearray(packed[cursor:cursor + stride])
        cursor += stride
        for i, value in enumerate(scan):
            left = scan[i - channels] if i >= channels else 0
            up = previous[i]
            up_left = previous[i - channels] if i >= channels else 0
            if filter_type == 1:
                scan[i] = (value + left) & 255
            elif filter_type == 2:
                scan[i] = (value + up) & 255
            elif filter_type == 3:
                scan[i] = (value + ((left + up) // 2)) & 255
            elif filter_type == 4:
                p, pa, pb, pc = left + up - up_left, 0, 0, 0
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                scan[i] = (value + (left if pa <= pb and pa <= pc else up if pb <= pc else up_left)) & 255
            elif filter_type != 0:
                raise AssertionError(f"{path.relative_to(ROOT)}:1\nactual: PNG filter {filter_type}\nexpected: filter 0-4\nfix: recapture the screenshot")
        rows.append(bytes(scan))
        previous = scan
    return width, height, b"".join(rows)


def pixel_diff_percent(current: Path, golden: Path) -> float:
    cw, ch, cp = png_rgba(current)
    gw, gh, gp = png_rgba(golden)
    if (cw, ch) != (gw, gh):
        raise AssertionError(
            f"{current.relative_to(ROOT)}:1\nactual: {cw}x{ch}\nexpected: {gw}x{gh}\nfix: capture the current screen at the golden viewport"
        )
    # Treat a pixel as different when any channel changes. This deliberately
    # avoids hiding layout changes behind an averaged color distance.
    channels = len(cp) // (cw * ch)
    changed = sum(1 for i in range(0, len(cp), channels) if cp[i:i + channels] != gp[i:i + channels])
    return changed * 100.0 / (cw * ch)
