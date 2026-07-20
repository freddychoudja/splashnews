import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock, patch

import sync_kamerjob


class SyncKamerJobTests(unittest.TestCase):
    @patch("sync_kamerjob.smtplib.SMTP")
    @patch.dict(
        "sync_kamerjob.os.environ",
        {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "sender@example.com",
            "SMTP_PASSWORD": "secret",
            "REPORT_EMAIL_TO": "recipient@example.com",
        },
        clear=True,
    )
    def test_sends_email_report_with_starttls(self, smtp_class):
        smtp = MagicMock()
        smtp_class.return_value.__enter__.return_value = smtp

        sent = sync_kamerjob.send_email_report("Rapport", "Tout va bien")

        self.assertTrue(sent)
        smtp.starttls.assert_called_once_with()
        smtp.login.assert_called_once_with("sender@example.com", "secret")
        message = smtp.send_message.call_args.args[0]
        self.assertIsInstance(message, EmailMessage)
        self.assertEqual(message["To"], "recipient@example.com")
        self.assertEqual(message["Subject"], "Rapport")

    @patch.dict("sync_kamerjob.os.environ", {}, clear=True)
    def test_missing_smtp_configuration_does_not_fail_sync(self):
        self.assertFalse(sync_kamerjob.send_email_report("Rapport", "Contenu"))

    @patch("sync_kamerjob.subprocess.run")
    @patch("sync_kamerjob.send_email_report")
    @patch("sync_kamerjob.write_csv")
    @patch("sync_kamerjob.scrape_sources")
    def test_scrapes_expected_sources_then_publishes(
        self, scrape_sources, write_csv, send_email_report, subprocess_run
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
        scrape_sources.assert_called_once_with(
            ("cameroondesks", "jobincamer", "jobcameroun", "reliefweb"), 30, 20
        )
        write_csv.assert_called_once_with(scrape_sources.return_value, output)
        command = subprocess_run.call_args.args[0]
        self.assertIn("--send", command)
        input_index = command.index("--input")
        self.assertEqual(command[input_index + 1], "offres.csv")
        send_email_report.assert_called_once()

    @patch("sync_kamerjob.subprocess.run")
    @patch("sync_kamerjob.send_email_report")
    @patch("sync_kamerjob.write_csv")
    @patch("sync_kamerjob.scrape_sources", return_value=[])
    def test_empty_scrape_stops_before_publication(
        self, scrape_sources, write_csv, send_email_report, subprocess_run
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
        send_email_report.assert_called_once()


if __name__ == "__main__":
    unittest.main()
