"""test_pdf_layout.py — PDF layout regression tests.

These tests pin the layout contract documented in
docs/resume-writing-design-standard.md:
  * Body content lives within 14 mm left margin and 14 mm right margin.
  * The Letter page is 215.9 mm wide; the usable content width is 182 mm.

The four fixture files in this directory each stress one missing-or-long
case the audit (transcript at
/Users/achyuth/.hermes/profiles/forge/cache/delegation/live/deleg_6f584246/task-1.log)
found in the original generator:

  resume_baseline.txt     — all fields present; control case.
  resume_missing_city.txt — JOB: company | title | dates | (empty city).
                            The original code did not advance the cursor
                            after writing the company when city was
                            missing, so the title rendered on the SAME
                            line as the company at x=196 mm, running past
                            the page width.
  resume_missing_dates.txt — JOB: company | title | (empty dates) | city.
                             Same class of cursor-advance defect.
  resume_long_title.txt    — extremely long title row; must still wrap or
                             fit inside 182 mm.
  resume_long_company.txt  — extremely long company row; same constraint.

For every fixture, the test asserts:
  * the parser succeeds and the PDF renders exactly one page, AND
  * the rightmost x coordinate actually written to the page (xMax) does
    not exceed CONTENT_RIGHT_EDGE_MM = 196 mm.

A test that just asserts "a page was produced" would let the missing-city
defect pass: the original generator happily produced a one-page PDF whose
title sat on the same line as the company and ran to x=367 mm.
"""
import unittest
from pathlib import Path

from engine import make_resume_pdf as mrp


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _render(name):
    text = (FIXTURES / name).read_text()
    return mrp.render_in_memory(text, scale=1.0, template="gabelli")


class PDFLayoutUsableWidthTests(unittest.TestCase):
    """The xMax of the rendered PDF must stay within the usable width."""

    def assert_within_usable_width(self, fixture):
        pdf, x_max, last_y = _render(fixture)
        self.assertEqual(
            len(pdf.pages), 1,
            "{} rendered {} pages, expected 1".format(fixture, len(pdf.pages)),
        )
        self.assertLessEqual(
            x_max, mrp.CONTENT_RIGHT_EDGE_MM,
            "{}: xMax={:.2f}mm exceeds CONTENT_RIGHT_EDGE_MM={:.2f}mm".format(
                fixture, x_max, mrp.CONTENT_RIGHT_EDGE_MM,
            ),
        )
        # And it must be positive — i.e. something was actually drawn.
        self.assertGreater(x_max, mrp.USABLE_WIDTH_MM / 2.0)

    def test_baseline_within_usable_width(self):
        self.assert_within_usable_width("resume_baseline.txt")

    def test_missing_city_within_usable_width(self):
        """Regression: missing city caused title to render on company line."""
        self.assert_within_usable_width("resume_missing_city.txt")

    def test_missing_dates_within_usable_width(self):
        """Regression: missing dates caused context to collide with title."""
        self.assert_within_usable_width("resume_missing_dates.txt")

    def test_long_title_within_usable_width(self):
        """Long titles must fit or wrap inside 182 mm of usable width."""
        self.assert_within_usable_width("resume_long_title.txt")

    def test_long_company_within_usable_width(self):
        """Long company names must fit or wrap inside 182 mm of usable width."""
        self.assert_within_usable_width("resume_long_company.txt")


class PDFLayoutStrictParserTests(unittest.TestCase):
    """The strict parser rejects malformed input with typed errors."""

    def test_unknown_template_rejected(self):
        bad = "TEMPLATE: foobar\nNAME: A\nCONTACT: NYC\nSECTION X\n"
        with self.assertRaises(mrp.ResumeParseError) as ctx:
            mrp.parse_resume(bad)
        self.assertEqual(ctx.exception.line_no, 1)
        self.assertIn("foobar", str(ctx.exception))

    def test_missing_template_defaults_to_default(self):
        good = "NAME: A\nCONTACT: NYC\nSECTION X\n"
        parsed = mrp.parse_resume(good)
        self.assertEqual(parsed["template"], "default")

    def test_gabelli_template_accepted(self):
        good = "TEMPLATE: gabelli\nNAME: A\nCONTACT: NYC\nSECTION X\n"
        parsed = mrp.parse_resume(good)
        self.assertEqual(parsed["template"], "gabelli")

    def test_unknown_directive_carries_line_number(self):
        bad = "NAME: A\nCONTACT: NYC\nFROBNICATE: bar\nSECTION X\n"
        with self.assertRaises(mrp.ResumeParseError) as ctx:
            mrp.parse_resume(bad)
        self.assertEqual(ctx.exception.line_no, 3)
        self.assertIn("FROBNICATE", str(ctx.exception))

    def test_job_outside_section_rejected(self):
        bad = "NAME: A\nCONTACT: NYC\nJOB: Foo | Bar | Dates | City\n"
        with self.assertRaises(mrp.ResumeParseError) as ctx:
            mrp.parse_resume(bad)
        self.assertEqual(ctx.exception.line_no, 3)
        self.assertIn("JOB", str(ctx.exception))

    def test_context_outside_job_rejected(self):
        bad = "NAME: A\nCONTACT: NYC\nSECTION X\nCONTEXT: nope\n"
        with self.assertRaises(mrp.ResumeParseError) as ctx:
            mrp.parse_resume(bad)
        self.assertEqual(ctx.exception.line_no, 4)
        self.assertIn("CONTEXT", str(ctx.exception))

    def test_group_outside_job_rejected(self):
        bad = "NAME: A\nCONTACT: NYC\nSECTION X\nGROUP: foo | bar\n"
        with self.assertRaises(mrp.ResumeParseError) as ctx:
            mrp.parse_resume(bad)
        self.assertEqual(ctx.exception.line_no, 4)
        self.assertIn("GROUP", str(ctx.exception))

    def test_bullet_outside_section_rejected(self):
        bad = "NAME: A\nCONTACT: NYC\n- floating bullet\n"
        with self.assertRaises(mrp.ResumeParseError) as ctx:
            mrp.parse_resume(bad)
        self.assertEqual(ctx.exception.line_no, 3)
        self.assertIn("bullet", str(ctx.exception))


class PDFLayoutConstantsTests(unittest.TestCase):
    def test_letter_page_width_constant(self):
        # US Letter, 8.5 inches × 25.4 mm/in
        self.assertAlmostEqual(mrp.LETTER_PAGE_WIDTH_MM, 215.9, places=1)

    def test_usable_width_matches_generator(self):
        # Generator sets l_margin = 14 mm and uses 182 mm body width.
        self.assertEqual(mrp.USABLE_WIDTH_MM, 182.0)
        self.assertEqual(mrp.CONTENT_RIGHT_EDGE_MM, 196.0)


if __name__ == "__main__":
    unittest.main()