"""Design-token contract gate: docs are source-of-truth, CSS is the mirror."""
from __future__ import annotations

import re
import unittest

from tests.verify._helpers import DOCS, UI, actionable

EXPECTED = {
    "--text-display": "32px", "--text-display-lh": "40px", "--text-display-weight": "600",
    "--text-display-large": "40px", "--text-display-large-lh": "48px", "--text-display-large-weight": "600",
    "--text-h1": "24px", "--text-h1-lh": "32px", "--text-h1-weight": "600",
    "--text-h2": "18px", "--text-h2-lh": "26px", "--text-h2-weight": "600",
    "--text-body": "14px", "--text-body-lh": "22px", "--text-body-weight": "400",
    "--text-meta": "12px", "--text-meta-lh": "18px", "--text-meta-weight": "400",
    "--text-meta-tight": "11px", "--text-meta-tight-lh": "16px", "--text-meta-tight-weight": "400",
    "--text-mono": "13px", "--text-mono-lh": "20px", "--text-mono-weight": "400",
    "--space-2": "4px", "--space-3": "8px", "--space-4": "12px", "--space-5": "16px", "--space-6": "24px", "--space-7": "32px",
    "--color-bg": "#FFFFFF", "--color-surface": "#F7F8FA", "--color-border": "#E5E7EB", "--color-text-primary": "#111827", "--color-text-secondary": "#6B7280", "--color-accent": "#2563EB", "--color-warning": "#D97706", "--color-danger": "#DC2626", "--color-success": "#10B981",
    "--radius-sm": "4px", "--radius-md": "8px", "--radius-lg": "12px", "--shadow-overlay": "0 1px 2px rgba(17, 24, 39, 0.06)",
}


class DesignTokenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css_path = UI / "styles.css"
        cls.css = cls.css_path.read_text(encoding="utf-8")
        cls.docs = (DOCS / "ui-design-tokens.md").read_text(encoding="utf-8")
        root = re.search(r":root\s*\{([\s\S]*?)\n\}", cls.css)
        cls.declared = dict(re.findall(r"^\s*(--[\w-]+):\s*([^;]+);", root.group(1), re.M)) if root else {}

    def test_every_css_variable_has_the_documented_value(self):
        self.assertEqual(set(self.declared), set(EXPECTED), "ui/styles.css: :root variable set drifted\nfix: add the token to docs/ui-design-tokens.md and this verification contract, or remove the orphan")
        for name, expected in EXPECTED.items():
            actual = self.declared.get(name)
            if actual != expected:
                actionable(self, self.css_path, name, actual, expected, "restore the documented token value")

    def test_documentation_contains_every_canonical_token_value(self):
        for name, value in EXPECTED.items():
            if name.startswith("--color-"):
                self.assertIn(value, self.docs, f"docs/ui-design-tokens.md: missing {name} value {value}; document it before CSS uses it")
        for literal in ("32 / 40", "40 / 48", "24 / 32", "18 / 26", "14 / 22", "12 / 18", "11 / 16", "13 / 20"):
            self.assertIn(literal, self.docs, f"docs/ui-design-tokens.md: missing type token {literal}")

    def test_css_has_no_orphan_hex_codes(self):
        declared_colors = {value.upper() for name, value in EXPECTED.items() if name.startswith("--color-")}
        all_hex = set(re.findall(r"#[0-9A-Fa-f]{6}\b", self.css))
        self.assertEqual({item.upper() for item in all_hex}, declared_colors, "ui/styles.css: orphan hex code found\nfix: replace it with an approved --color-* variable")

    def test_token_references_resolve_to_declared_variables(self):
        referenced = set(re.findall(r"var\((--[\w-]+)", self.css))
        unresolved = sorted(referenced - set(self.declared))
        self.assertEqual(unresolved, [], f"ui/styles.css: unresolved variables {unresolved}\nfix: declare each token in :root or correct the var() reference")


if __name__ == "__main__":
    unittest.main()
