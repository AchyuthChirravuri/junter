#!/usr/bin/env python3
"""make-resume-pdf: designed one-page resume PDF from structured markdown.

Format:
  NAME: Your Name
  CONTACT: New York, NY | (000) 000-0000 | you@example.com | linkedin.com/in/your-handle
  TAGLINE: BUSINESS STRATEGY | PRODUCT ROADMAPS | ...
  SUMMARY: 2-line positioning summary
  SECTION Experience
  JOB: Company | Title | Dates
  CONTEXT: optional italic line
  - bullet (STAR, one line, wraps)
  GROUP: Label | comma,separated,items
  SECTION Education
  JOB: School | Degree | Dates

Design tokens live in resume-style.md. One-page enforced via auto-scale (9.2 -> 8.9 -> 8.6pt)
then hard error: cut writing instead of squeezing.
"""
import sys
from pathlib import Path

from fpdf import FPDF

INK = (27, 42, 74)        # #1B2A4A
BODY = (34, 34, 34)       # #222222
GRAY = (85, 85, 85)       # #555555
ACCENT = (14, 90, 94)     # #0E5A5E
ACCENT_SOFT = (14, 90, 94)

MM = 1.0


def parse(src: str):
    name = contact = tagline = summary = ""
    sections = []           # list of dicts: {name, jobs:[{company,title,dates,context,bullets}]}
    cur_section = None
    cur_job = None
    for raw in Path(src).read_text().splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("NAME:"):
            name = line[5:].strip()
        elif line.startswith("CONTACT:"):
            contact = line[8:].strip()
        elif line.startswith("TAGLINE:"):
            tagline = line[8:].strip()
        elif line.startswith("SUMMARY:"):
            summary = line[8:].strip()
            summary += " " + next(Path(src).read_text().splitlines(), "")
            # SUMMARY may span until next directive; handled by join below
        elif line.startswith("SECTION"):
            cur_section = {"name": line.split(None, 1)[1].strip(), "jobs": []}
            sections.append(cur_section)
            cur_job = None
        elif line.startswith("JOB:"):
            parts = [p.strip() for p in line[4:].split("|")]
            parts += [""] * (3 - len(parts))
            cur_job = {"company": parts[0], "title": parts[1] if len(parts) > 1 else "",
                       "dates": parts[2] if len(parts) > 2 else "", "context": "", "bullets": []}
            cur_section["jobs"].append(cur_job)
        elif line.startswith("CONTEXT:"):
            if cur_job:
                cur_job["context"] = line[8:].strip()
        elif line.lstrip().startswith("- "):
            if cur_job is not None:
                cur_job["bullets"].append(line.lstrip()[2:].strip())
        elif line.startswith("GROUP:"):
            if cur_job is not None:
                cur_job["bullets"].append("GROUP::" + line[6:].strip())
    # merge multi-line SUMMARY (consecutive lines after SUMMARY: until blank/next token)
    return name, contact, tagline, summary, sections


def parse_strict(src_text: str):
    template = "default"
    name = contact = tagline = None
    summary_lines = []
    sections = []
    cur_section = None
    cur_job = None
    state = "head"
    for raw in src_text.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s:
            if state == "summary":
                state = "head"
            continue
        if s.startswith("TEMPLATE:"):
            template = s[9:].strip().lower(); state = "head"
        elif s.startswith("NAME:"):
            name = s[5:].strip(); state = "head"
        elif s.startswith("CONTACT:"):
            contact = s[8:].strip(); state = "head"
        elif s.startswith("TAGLINE:"):
            tagline = s[8:].strip(); state = "head"
        elif s.startswith("SUMMARY:"):
            summary_lines.append(s[8:].strip()); state = "summary"
        elif s.startswith("SECTION"):
            cur_section = {"name": s.split(None, 1)[1].strip(), "jobs": [], "bullets": []}
            sections.append(cur_section); cur_job = None; state = "head"
        elif s.startswith("JOB:"):
            parts = [p.strip() for p in s[4:].split("|")]
            parts += [""] * (4 - len(parts))
            cur_job = {"company": parts[0], "title": parts[1], "dates": parts[2],
                       "city": parts[3], "context": "", "bullets": [], "groups": []}
            cur_section["jobs"].append(cur_job); state = "head"
        elif s.startswith("CONTEXT:"):
            if cur_job: cur_job["context"] = s[8:].strip()
        elif s.startswith("GROUP:"):
            if cur_job:
                label, _, items = s[6:].partition("|")
                cur_job["groups"].append((label.strip(), [i.strip() for i in items.split(",") if i.strip()]))
        elif s.startswith("- "):
            if cur_job is not None:
                cur_job["bullets"].append(s[2:].strip())
            elif cur_section is not None:
                cur_section["bullets"].append(s[2:].strip())  # section-level bullet (no JOB)
        elif state == "summary":
            summary_lines.append(s)
    summary = " ".join(summary_lines)
    return template, name, contact, tagline, summary, sections


class ResumePDF(FPDF):
    def __init__(self, scale=1.0):
        super().__init__("P", "mm", "Letter")
        self.scale = scale
        self.set_margins(14, 12, 14)
        self.set_auto_page_break(True, margin=10)

    def scaled(self, base):
        return round(base * self.scale, 2)


def build(src_text: str, out: str, accent=(14, 90, 94)):
    template, name, contact, tagline, summary, sections = parse_strict(src_text)
    assert name and contact, "NAME: and CONTACT: required"
    if template == "gabelli":
        accent = (17, 17, 17)  # all-black ink for the Gabelli template

    # Fit-to-page: pick the LARGEST scale that renders on exactly one page
    # AND leaves bottom clearance (last line ends >= 14mm above page bottom,
    # i.e. above the auto-break line minus a 4mm safety gap). Prevents the
    # "ADDITIONAL section clipped at page edge" failure.
    scales = (1.12, 1.06, 1.0, 0.965, 0.935, 0.905, 0.88, 0.855)
    doc = None
    for scale in scales:
        try:
            candidate, used = render(scale, name, contact, tagline, summary, sections, accent, template)
        except OverflowError:
            continue
        if len(candidate.pages) == 1 and candidate.get_y() <= 279.4 - 14.0:
            doc = candidate
            break
    if doc is None:
        # relax: accept any single-page render even if tight at the bottom
        for scale in scales:
            try:
                candidate, used = render(scale, name, contact, tagline, summary, sections, accent, template)
            except OverflowError:
                continue
            if len(candidate.pages) == 1:
                doc = candidate
                break
    if doc is None:
        raise SystemExit("OVERFLOW: content exceeds one page even at minimum scale — cut bullets, do not squeeze.")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    doc.output(str(out))
    return str(out)


def render(scale, name, contact, tagline, summary, sections, accent, template="default"):
    d = ResumePDF(scale)
    d.add_page()
    d.set_text_color(*BODY)
    eff = d.scaled
    gabelli = template == "gabelli"
    start_y = d.get_y()

    # ── Header block ─────────────────────────────────────────────
    if gabelli:
        # Right-aligned header stack: name / contact / tagline, all black.
        d.set_font("helvetica", "B", eff(17))
        d.set_text_color(*INK)
        d.cell(0, eff(7.5), name.upper(), align="R", new_x="LMARGIN", new_y="NEXT")
        d.set_font("helvetica", "", eff(8.3))
        d.set_text_color(*BODY)
        d.cell(0, eff(4.0), contact, align="R", new_x="LMARGIN", new_y="NEXT")
        if tagline:
            d.set_font("helvetica", "B", eff(8.3))
            d.cell(0, eff(4.0), "  ".join(tagline.split("|")), align="R", new_x="LMARGIN", new_y="NEXT")
        d.set_y(d.get_y() + eff(1.2))
    else:
        # Name
        d.set_font("helvetica", "B", eff(20))
        d.set_text_color(*INK)
        d.cell(0, eff(8.5), name, new_x="LMARGIN", new_y="NEXT")

        # Contact
        d.set_font("helvetica", "", eff(8.5))
        d.set_text_color(*GRAY)
        d.cell(0, eff(4.4), contact, new_x="LMARGIN", new_y="NEXT")

        # Tagline + accent rule
        if tagline:
            d.ln(eff(0.8))
            d.set_font("helvetica", "B", eff(8.6))
            d.set_text_color(*accent)
            d.cell(0, eff(4.2), "  ".join(tagline.split("|")), new_x="LMARGIN", new_y="NEXT")
            d.set_draw_color(*accent)
            d.set_line_width(0.5)
            d.line(14, d.get_y(), 196, d.get_y())

    # Summary
    if summary:
        d.ln(eff(1.8))
        d.set_font("helvetica", "", eff(9.0))
        d.set_text_color(*BODY)
        d.multi_cell(0, eff(4.2), summary, new_x="LMARGIN", new_y="NEXT")

    for sec in sections:
        d.ln(eff(2.6))
        d.set_font("helvetica", "B", eff(9.5))
        d.set_text_color(*(17, 17, 17) if gabelli else accent)
        d.cell(0, eff(4.6), sec["name"].upper(), new_x="LMARGIN", new_y="NEXT")
        d.set_line_width(0.3)
        d.set_draw_color(*(17, 17, 17) if gabelli else accent)
        d.line(14, d.get_y(), 196, d.get_y())
        d.ln(eff(1.2))
        for job in sec["jobs"]:
            _job(d, job, eff, accent, gabelli)
        # section-level bullets (e.g. ADDITIONAL without JOB entries)
        for bullet in sec.get("bullets", []):
            d.set_font("helvetica", "", eff(9.0) if gabelli else eff(9.2))
            d.set_text_color(*BODY)
            y_top = d.get_y()
            d.set_x(d.l_margin + 4)
            d.multi_cell(182 - 4, eff(3.9) if gabelli else eff(4.1), bullet, new_x="LMARGIN", new_y="NEXT")
            gy = y_top + eff(1.5)
            d.set_fill_color(*accent)
            d.ellipse(d.l_margin + 1.0, gy, 1.3, 1.3, "F")
    used = d.get_y() - start_y + 12  # top margin + bottom slack reference
    return d, used


def _job(d, job, eff, accent, gabelli=False):
    """Job header. gabelli: COMPANY caps left + city right; title bold left + dates right.
    default: company|title inline left + dates right (wraps when long)."""
    if gabelli:
        # Line 1: COMPANY caps + city right
        city_w = 0.0
        if job.get("city"):
            d.set_font("helvetica", "", eff(8.8))
            city_w = d.get_string_width(job["city"]) + 4
        else:
            city_w = 0
        d.set_font("helvetica", "B", eff(9.8))
        d.set_text_color(*(17, 17, 17))
        d.cell(182 - city_w, eff(4.6), job["company"].upper(), new_x="RIGHT", new_y="TOP")
        if job.get("city"):
            d.set_font("helvetica", "", eff(8.8))
            d.cell(0, eff(4.6), job["city"], align="R", new_x="LMARGIN", new_y="NEXT")
        # Line 2: title bold + dates right
        if job["title"] or job["dates"]:
            d.set_font("helvetica", "B", eff(9.3))
            d.set_text_color(*(17, 17, 17))
            dates_w = 0
            if job["dates"]:
                d.set_font("helvetica", "", eff(8.8))
                dates_w = d.get_string_width(job["dates"]) + 4
                d.set_font("helvetica", "B", eff(9.3))
            d.cell(182 - dates_w, eff(4.3), job["title"], new_x="RIGHT", new_y="TOP")
            if job["dates"]:
                d.set_font("helvetica", "", eff(8.8))
                d.cell(0, eff(4.3), job["dates"], align="R", new_x="LMARGIN", new_y="NEXT")
        if job["context"]:
            d.set_font("helvetica", "", eff(8.8))
            d.set_text_color(*BODY)
            d.multi_cell(0, eff(3.6), job["context"], new_x="LMARGIN", new_y="NEXT")
    else:
        # Legacy inline layout
        dates_w = 0.0
        if job["dates"]:
            d.set_font("helvetica", "", eff(8.8))
            dates_w = d.get_string_width(job["dates"]) + 4
        inline = f'{job["company"]}   |   {job["title"]}' if job["title"] else job["company"]
        d.set_font("helvetica", "B", eff(9.8))
        d.set_text_color(*INK)
        inline_w = d.get_string_width(inline)
        if inline_w <= 182 - dates_w - 6:
            d.cell(182 - dates_w, eff(4.6), inline, new_x="RIGHT", new_y="TOP")
            if job["dates"]:
                d.set_font("helvetica", "", eff(8.8))
                d.set_text_color(*GRAY)
                d.cell(0, eff(4.6), job["dates"], align="R", new_x="LMARGIN", new_y="NEXT")
        else:
            y0 = d.get_y()
            d.cell(182 - dates_w, eff(4.6), job["company"], new_x="RIGHT", new_y="TOP")
            if job["dates"]:
                d.set_font("helvetica", "", eff(8.8))
                d.set_text_color(*GRAY)
                d.cell(0, eff(4.6), job["dates"], align="R", new_x="LMARGIN", new_y="TOP")
            d.set_y(y0 + eff(4.6))
            d.set_x(d.l_margin)
            d.set_font("helvetica", "", eff(9.0))
            d.set_text_color(*INK)
            d.cell(0, eff(4.2), job["title"], new_x="LMARGIN", new_y="NEXT")
        if job["context"]:
            d.set_font("helvetica", "I", eff(8.6))
            d.set_text_color(*GRAY)
            d.multi_cell(0, eff(3.6), job["context"], new_x="LMARGIN", new_y="NEXT")
    for bullet in job["bullets"]:
        d.set_font("helvetica", "", eff(9.2) if not gabelli else eff(9.0))
        d.set_text_color(*BODY)
        y_top = d.get_y()
        d.set_x(d.l_margin + 4)
        d.multi_cell(182 - 4, eff(4.1) if not gabelli else eff(3.9), bullet, new_x="LMARGIN", new_y="NEXT")
        gy = y_top + eff(1.5)
        d.set_fill_color(*accent)
        d.ellipse(d.l_margin + 1.0, gy, 1.3, 1.3, "F")
    for label, items in job.get("groups", []):
        d.set_font("helvetica", "B", eff(8.8))
        d.set_text_color(*INK)
        d.cell(d.get_string_width(label + ":  ") + 1, eff(4.0), label + ":  ", new_x="END", new_y="TOP")
        d.set_font("helvetica", "", eff(8.8))
        d.set_text_color(*BODY)
        d.multi_cell(0, eff(4.0), ",  ".join(items), new_x="LMARGIN", new_y="NEXT")


if __name__ == "__main__":
    src, out = sys.argv[1], sys.argv[2]
    print(build(Path(src).read_text(), out))