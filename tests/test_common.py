import unittest

from sources.common import normalize_lines, strip_html


class HtmlCleaningTests(unittest.TestCase):
    def test_strip_html_removes_css_and_javascript_contents(self):
        content = (
            '<style>.card{color:#fff;background:#008751;margin:2px 0;}</style>'
            '<script>window.alert("parasite");</script>'
            '<p>Une offre <strong>intéressante</strong>.</p>'
        )

        self.assertEqual(strip_html(content), "Une offre intéressante.")

    def test_normalize_lines_removes_style_and_preserves_text_lines(self):
        content = (
            '<style>.card{color:#fff;background:#008751;}</style>'
            '<p>Lieu : Douala</p><p>Expérience : 3 ans</p>'
        )

        self.assertEqual(
            normalize_lines(content),
            "Lieu : Douala\nExpérience : 3 ans",
        )

    def test_strip_html_decodes_entities(self):
        self.assertEqual(strip_html("Architecture &#038; Urbanisme"), "Architecture & Urbanisme")


if __name__ == "__main__":
    unittest.main()
