import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from text_cleaner import clean_text, html_to_text


class TextCleanerTest(unittest.TestCase):
    def test_html_tags_removed(self):
        raw = "<html><body><p>测评时间：2026-08-25 23:00</p><a href='https://example.com'>链接</a></body></html>"
        cleaned = html_to_text(raw)
        self.assertNotIn("<p>", cleaned)
        self.assertIn("测评时间：2026-08-25 23:00", cleaned)

    def test_entities_decoded(self):
        self.assertIn("&", html_to_text("A &amp; B"))

    def test_whitespace_collapsed(self):
        self.assertEqual(clean_text("一\n\n\n二"), "一\n二")

    def test_script_style_removed(self):
        raw = "<script>alert(1)</script>正文<style>.x{color:red}</style>"
        self.assertNotIn("alert", html_to_text(raw))
        self.assertIn("正文", html_to_text(raw))


if __name__ == "__main__":
    unittest.main()
