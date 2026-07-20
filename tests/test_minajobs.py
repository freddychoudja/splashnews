import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from xml.etree import ElementTree

from sources import minajobs


RSS_ITEM = """
<item>
  <title><![CDATA[Développeur Python]]></title>
  <link>https://cameroun.minajobs.net/offre/123</link>
  <pubDate>Sat, 18 Jul 2026 10:00:00 +0100</pubDate>
  <description><![CDATA[
    <p>Localisation : Douala</p>
    <p>Expérience requise : 2 ans</p>
    <p>Date limite : 31 juillet 2026</p>
  ]]></description>
</item>
"""


class MinaJobsTests(unittest.TestCase):
    def test_parse_rss_item(self):
        detail_html = """
        <div class="detail-font">
          Envoyez votre CV à recrutement@example.org
          ou <a href="https://jobs.example.org/apply/123">postulez ici</a>.
          <a href="https://cameroun.minajobs.net/contact">MinaJobs</a>
        </div>
        """
        row = minajobs.parse_item(ElementTree.fromstring(RSS_ITEM), detail_html)

        self.assertEqual(row["title"], "Développeur Python")
        self.assertEqual(row["ville"], "Douala")
        self.assertEqual(row["region"], "Littoral")
        self.assertEqual(row["experience"], "2 ans")
        self.assertEqual(row["deadline"], "2026-07-31")
        self.assertEqual(row["apply_email"], "mailto:recrutement@example.org")
        self.assertEqual(row["apply_url"], "https://jobs.example.org/apply/123")
        self.assertNotIn("minajobs", row["apply_url"])

    @patch("sources.minajobs.fetch_feed")
    @patch("sources.minajobs.fetch_detail")
    @patch("sources.minajobs.time.sleep")
    def test_scrape_ignores_old_items(self, _sleep, fetch_detail, fetch_feed):
        recent = datetime.now(timezone.utc) - timedelta(days=1)
        old = datetime.now(timezone.utc) - timedelta(days=60)

        def item(title, published):
            return (
                f"<item><title>{title}</title><link>https://example.com/{title}</link>"
                f"<pubDate>{published.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"
                "<description>Offre au Cameroun</description></item>"
            )

        fetch_feed.return_value = (
            "<rss><channel>" + item("Recent", recent) + item("Old", old)
            + "</channel></rss>"
        ).encode()
        fetch_detail.return_value = (
            '<div class="detail-font">'
            '<a href="https://employer.example/apply">Postuler</a></div>'
        )

        rows = minajobs.scrape(30, 20)

        self.assertEqual([row["title"] for row in rows], ["Recent"])

    @patch("sources.minajobs.fetch_feed")
    @patch("sources.minajobs.fetch_detail")
    def test_scrape_rejects_offer_without_direct_channel(self, fetch_detail, fetch_feed):
        fetch_feed.return_value = (
            "<rss><channel>" + RSS_ITEM + "</channel></rss>"
        ).encode()
        fetch_detail.return_value = (
            '<div class="detail-font">Postulez sur MinaJobs.'
            '<a href="https://cameroun.minajobs.net/login">Connexion</a></div>'
        )

        self.assertEqual(minajobs.scrape(30, 20), [])


if __name__ == "__main__":
    unittest.main()
