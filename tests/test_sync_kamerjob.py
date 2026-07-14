import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_kamerjob


class SyncKamerJobTests(unittest.TestCase):
    @patch("sync_kamerjob.subprocess.run")
    @patch("sync_kamerjob.write_csv")
    @patch("sync_kamerjob.scrape_sources")
    def test_scrapes_expected_sources_then_publishes(
        self, scrape_sources, write_csv, subprocess_run
    ):
        scrape_sources.return_value = [{"title": "Une offre"}]
        subprocess_run.return_value.returncode = 0
        output = Path("offres.csv")

        result = sync_kamerjob.run_sync(
            days=30,
            max_pages=20,
            output=output,
            dry_run=False,
            limit=None,
        )

        self.assertEqual(result, 0)
        scrape_sources.assert_called_once_with(("cameroondesks", "jobincamer"), 30, 20)
        write_csv.assert_called_once_with(scrape_sources.return_value, output)
        command = subprocess_run.call_args.args[0]
        self.assertIn("--send", command)
        input_index = command.index("--input")
        self.assertEqual(command[input_index + 1], "offres.csv")

    @patch("sync_kamerjob.subprocess.run")
    @patch("sync_kamerjob.write_csv")
    @patch("sync_kamerjob.scrape_sources", return_value=[])
    def test_empty_scrape_stops_before_publication(
        self, scrape_sources, write_csv, subprocess_run
    ):
        with tempfile.TemporaryDirectory() as directory:
            result = sync_kamerjob.run_sync(
                days=30,
                max_pages=20,
                output=Path(directory) / "offres.csv",
                dry_run=False,
                limit=None,
            )
        self.assertEqual(result, 1)
        subprocess_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
