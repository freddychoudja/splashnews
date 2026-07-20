import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sources import reliefweb


class ReliefWebTests(unittest.TestCase):
    def test_parse_structured_job(self):
        item = {"fields": {
            "title": "Finance Officer",
            "date": {"created": "2026-07-18T10:00:00+00:00", "closing": "2026-08-01T23:59:59+00:00"},
            "city": [{"name": "Yaoundé"}],
            "experience": [{"name": "3-4 years"}],
            "body-html": "<p>Poste hybride au Cameroun.</p>",
            "how_to_apply-html": '<a href="mailto:jobs@example.org">Apply</a>',
            "url_alias": "https://reliefweb.int/job/123",
        }}

        row = reliefweb.parse_job(item)

        self.assertEqual(row["ville"], "Yaoundé")
        self.assertEqual(row["region"], "Centre")
        self.assertEqual(row["deadline"], "2026-08-01")
        self.assertEqual(row["experience"], "3-4 years")
        self.assertEqual(row["work_mode"], "Hybride")
        self.assertEqual(row["apply_email"], "mailto:jobs@example.org")

    @patch("sources.reliefweb.fetch_page")
    def test_scrape_filters_old_rows(self, fetch_page):
        recent = datetime.now(timezone.utc) - timedelta(days=1)
        old = datetime.now(timezone.utc) - timedelta(days=60)

        def item(when, title):
            return {"fields": {
                "title": title,
                "date": {"created": when.isoformat()},
                "country": [{"name": "Cameroon"}],
                "url_alias": "https://reliefweb.int/job/123",
            }}

        fetch_page.return_value = {"data": [item(recent, "Recent"), item(old, "Old")]}
        rows = reliefweb.scrape(30, 2)

        self.assertEqual([row["title"] for row in rows], ["Recent"])
        fetch_page.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
