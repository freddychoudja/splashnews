import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from publish_kamerjob import (
    build_payload,
    clean_application_email,
    clean_application_url,
    fit_application_url,
    has_application_channel,
    infer_company,
    identities_match,
    journal_created_ids,
    journal_final_statuses,
    journal_published_ids,
    listing_identity,
    normalized,
    parse_salary,
)


REGIONS = {normalized("Centre"): 2, normalized("Partout au Cameroun"): 11}


class PublishKamerJobTests(unittest.TestCase):
    def test_company_from_recruitment_title(self):
        self.assertEqual(
            infer_company("Recrutement ONG GIZ Cameroun juillet 2026"),
            "ONG GIZ Cameroun",
        )
        self.assertEqual(
            infer_company("Recrutement chez Africa Global Logistics Cameroun 2026 : postes ouverts"),
            "Africa Global Logistics Cameroun",
        )

    def test_application_cleanup(self):
        self.assertEqual(clean_application_email("mailto:jobs@example.cm"), "jobs@example.cm")
        self.assertEqual(clean_application_url("http://bad@email; https://example.com/apply"), "https://example.com/apply")
        long_url = "https://example.com/apply?tracking=" + ("x" * 220)
        self.assertEqual(fit_application_url(long_url), "https://example.com/apply")

    def test_salary_range(self):
        self.assertEqual(parse_salary("300 000 - 600 000 FCFA"), (300000, 600000))

    def test_payload_maps_csv_fields(self):
        payload, reason = build_payload(
            {
                "title": "Recrutement MTN Cameroon juillet 2026 : Responsable marketing",
                "summary": "MTN recrute un responsable marketing.",
                "region": "Centre",
                "ville": "Yaoundé",
                "work_mode": "Hybride",
                "experience": "3 ans",
                "salary": "300 000 - 500 000 FCFA",
                "deadline": "2026-07-31",
                "source": "cameroondesks",
                "apply_email": "mailto:jobs@mtn.cm",
                "apply_url": "",
            },
            REGIONS,
            default_sector=21,
            default_job_type=10,
        )
        self.assertIsNone(reason)
        self.assertEqual(payload["company_name"], "MTN Cameroon")
        self.assertEqual(payload["sector"], 17)
        self.assertEqual(payload["region"], 2)
        self.assertEqual(payload["remote_mode"], "hybrid")
        self.assertEqual(payload["application_email"], "jobs@mtn.cm")

    def test_missing_application_channel_is_allowed(self):
        payload, reason = build_payload(
            {
                "title": "Recrutement ACME juillet 2026",
                "summary": "Une offre",
                "region": "",
                "source": "cameroondesks",
            },
            REGIONS,
            21,
            10,
        )
        self.assertIsNone(reason)
        self.assertEqual(payload["company_name"], "ACME")
        self.assertIsNone(payload["application_url"])
        self.assertIsNone(payload["application_email"])
        self.assertIn("CameroonDesks", payload["application_address"])

    def test_journal_created_ids_ignores_other_events(self):
        with TemporaryDirectory() as directory:
            journal = Path(directory) / "journal.jsonl"
            journal.write_text(
                '{"status":"created","id":"abc","title":"Offre"}\n'
                '{"status":"failed","id":"def","title":"Autre"}\n'
                '{"status":"published","id":"abc","title":"Offre"}\n',
                encoding="utf-8",
            )
            self.assertEqual(journal_created_ids(journal), {"abc"})
            self.assertEqual(journal_published_ids(journal), {"abc"})
            self.assertEqual(journal_final_statuses(journal), {"abc": "published"})

    def test_automatic_approval_requires_email_or_url(self):
        self.assertTrue(has_application_channel({"application_email": "jobs@example.cm"}))
        self.assertTrue(has_application_channel({"application_url": "https://example.cm/apply"}))
        self.assertFalse(
            has_application_channel(
                {"application_address": "Consulter l'annonce originale sur CameroonDesks"}
            )
        )

    def test_composite_identity_detects_cross_source_duplicate(self):
        left = listing_identity(
            {
                "title": "Recrutement AGL Cameroun : Développeur Full Stack",
                "company_name": "AGL Cameroun",
                "city": "Douala",
                "expires_at": "2026-07-31T23:00:00+01:00",
                "application_url": "https://example.cm/apply",
            }
        )
        right = listing_identity(
            {
                "title": "Africa Global Logistics (AGL) recrute un Développeur Full Stack H/F",
                "company_name": "Africa Global Logistics (AGL)",
                "city": "douala",
                "expires_at": "2026-07-31",
                "application_url": "https://example.cm/apply/",
            }
        )
        self.assertTrue(identities_match(left, right))

    def test_composite_identity_keeps_distinct_positions(self):
        common = {
            "company_name": "AGL Cameroun",
            "city": "Douala",
            "expires_at": "2026-07-31",
            "application_email": "jobs@agl.cm",
        }
        developer = listing_identity({**common, "title": "AGL recrute un Développeur Full Stack"})
        accountant = listing_identity({**common, "title": "AGL recrute un Chef Comptable"})
        self.assertFalse(identities_match(developer, accountant))

    def test_composite_identity_rejects_conflicting_city(self):
        common = {
            "title": "Recrutement ACME : Commercial",
            "company_name": "ACME",
            "expires_at": "2026-07-31",
            "application_email": "jobs@acme.cm",
        }
        douala = listing_identity({**common, "city": "Douala"})
        yaounde = listing_identity({**common, "city": "Yaoundé"})
        self.assertFalse(identities_match(douala, yaounde))


if __name__ == "__main__":
    unittest.main()
