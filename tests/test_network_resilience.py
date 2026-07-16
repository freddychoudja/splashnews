import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import requests

import scraper
from sources import jobcameroun


class JobCamerounResilienceTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "published": datetime.now(timezone.utc),
            "deadline": None,
        }

    @patch("sources.jobcameroun.time.sleep")
    @patch("sources.jobcameroun.parse_offer_detail")
    @patch("sources.jobcameroun.fetch_offer_detail")
    @patch("sources.jobcameroun.parse_listing")
    @patch("sources.jobcameroun.fetch_listing_page")
    def test_unavailable_offer_is_skipped(
        self, fetch_listing, parse_listing, fetch_detail, parse_detail, _sleep
    ):
        fetch_listing.side_effect = ["listing", "empty"]
        parse_listing.side_effect = [["bad-url", "good-url"], []]
        fetch_detail.side_effect = [requests.Timeout("timeout"), "detail"]
        parse_detail.return_value = self.row

        rows = jobcameroun.scrape(30, 2)

        self.assertEqual(rows, [self.row])
        parse_detail.assert_called_once_with("good-url", "detail")

    @patch("sources.jobcameroun.time.sleep")
    @patch("sources.jobcameroun.parse_offer_detail")
    @patch("sources.jobcameroun.fetch_offer_detail", return_value="detail")
    @patch("sources.jobcameroun.parse_listing", return_value=["good-url"])
    @patch("sources.jobcameroun.fetch_listing_page")
    def test_listing_timeout_keeps_previous_pages(
        self, fetch_listing, _parse_listing, _fetch_detail, parse_detail, _sleep
    ):
        fetch_listing.side_effect = ["listing", requests.Timeout("timeout")]
        parse_detail.return_value = self.row

        rows = jobcameroun.scrape(30, 2)

        self.assertEqual(rows, [self.row])


class AggregatorResilienceTests(unittest.TestCase):
    def test_unavailable_source_does_not_stop_other_sources(self):
        row = {"published": datetime.now(timezone.utc)}
        sources = {
            "unavailable": lambda *_args: (_ for _ in ()).throw(requests.Timeout()),
            "available": lambda *_args: [row],
        }

        with patch.object(scraper, "SOURCES", sources):
            rows = scraper.scrape_all(list(sources), 30, 20, False)

        self.assertEqual(rows, [row])


if __name__ == "__main__":
    unittest.main()
