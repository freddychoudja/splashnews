"""Publie les offres extraites vers le back-office KamerJob.

Le mode par défaut est une simulation. Utiliser ``--send`` pour créer les
annonces après validation du rapport affiché par la simulation.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests


BASE_URL = "https://admin.kamerjob.com"
DEFAULT_INPUT = "offres_emploi_cameroun.csv"
DEFAULT_ENV = ".env.kamerjob"
DEFAULT_JOURNAL = "publication_kamerjob.jsonl"
DEFAULT_SOURCES = ("cameroondesks", "jobincamer", "jobcameroun")
GENERIC_COMPANY_TOKENS = {
    "cameroun", "cameroon", "sa", "sas", "sarl", "ltd", "limited", "plc",
    "groupe", "group", "company", "compagnie", "societe", "entreprise", "ong",
}
GENERIC_POSITION_TOKENS = {
    "recrutement", "recrutements", "recrute", "recherche", "offre", "offres",
    "emploi", "emplois", "job", "jobs", "chez", "pour", "poste", "postes",
    "ouvert", "ouverts", "plusieurs", "profil", "profils", "cameroun", "cameroon",
    "janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "jullet",
    "aout", "septembre", "octobre", "novembre", "decembre", "hf", "fh", "un",
    "une", "des", "de", "du", "le", "la", "les", "en", "et",
}

SECTOR_RULES = [
    (14, ("banque", "finance", "microfinance", "comptable", "audit")),
    (17, ("telecom", "télécom", "mtn", "orange cameroun")),
    (18, ("informatique", "développeur", "developpeur", "logiciel", "digital", "data ", "cyber")),
    (28, (" ong ", "giz", "humanitaire", "association", "nations unies")),
    (20, ("marketing", "communication", "publicité", "commercial", "vente")),
    (10, ("distribution", "commerce", "magasin", "hôtesse de vente")),
    (6, ("boulangerie", "agroalimentaire", "alimentaire")),
    (4, ("pétrole", "petrole", "gaz", "mines")),
    (11, ("transport", "logistique", "chauffeur", "conducteur")),
    (26, ("santé", "sante", "médecin", "infirm", "pharm")),
    (25, ("formation", "éducation", "education", "enseignant", "école", "ecole")),
    (9, ("btp", "construction", "génie civil", "genie civil")),
    (12, ("hôtel", "hotel", "tourisme")),
    (13, ("restaurant", "cuisine", "cuisinier")),
]

JOB_TYPE_RULES = [
    (1, (" cdi ", "contrat à durée indéterminée")),
    (2, (" cdd ", "contrat à durée déterminée")),
    (3, ("stage", "stagiaire")),
    (5, ("alternance",)),
    (6, ("freelance", "indépendant")),
    (7, ("intérim", "interim")),
    (9, ("consultant", "consultance")),
    (11, ("temps partiel",)),
    (12, ("journalier",)),
    (13, ("volontaire", "volontariat", "bénévole")),
]

MONTH_PATTERN = (
    r"janvier|février|fevrier|mars|avril|mai|juin|juillet|jullet|août|aout|"
    r"septembre|octobre|novembre|décembre|decembre"
)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def normalized(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().casefold()


def word_tokens(value: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", normalized(value)))


def company_tokens(value: str | None) -> set[str]:
    return word_tokens(value) - GENERIC_COMPANY_TOKENS


def same_company(left: str | None, right: str | None) -> bool:
    left_normalized = normalized(left)
    right_normalized = normalized(right)
    if not left_normalized or not right_normalized:
        return False
    if "entreprise non precisee" in {left_normalized, right_normalized}:
        return False
    if left_normalized == right_normalized:
        return True
    left_tokens = company_tokens(left)
    right_tokens = company_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    common = left_tokens & right_tokens
    if not common:
        return False
    if left_tokens <= right_tokens or right_tokens <= left_tokens:
        return True
    if any(len(token) >= 3 for token in common) and min(len(left_tokens), len(right_tokens)) <= 2:
        return True
    return len(common) / len(left_tokens | right_tokens) >= 0.5


def position_tokens(title: str | None, company: str | None) -> set[str]:
    tokens = word_tokens(title)
    tokens -= company_tokens(company)
    tokens -= GENERIC_POSITION_TOKENS
    tokens = {
        token
        for token in tokens
        if len(token) > 1 and not re.fullmatch(r"20\d{2}|\d{1,2}", token)
    }
    return tokens


def position_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def listing_identity(item: dict) -> dict:
    company = (
        item.get("company_name")
        or item.get("company_display_name")
        or (item.get("company_detail") or {}).get("name")
        or ""
    )
    url = fit_application_url(str(item.get("application_url") or ""))
    email = clean_application_email(str(item.get("application_email") or ""))
    deadline = str(item.get("expires_at") or "")[:10]
    return {
        "company": company,
        "position_tokens": sorted(position_tokens(item.get("title"), company)),
        "city": normalized(item.get("city")),
        "deadline": deadline,
        "url": (url or "").rstrip("/"),
        "email": normalized(email),
        "title": item.get("title") or "",
    }


def identities_match(left: dict, right: dict) -> bool:
    if not same_company(left.get("company"), right.get("company")):
        return False
    similarity = position_similarity(
        set(left.get("position_tokens") or []),
        set(right.get("position_tokens") or []),
    )
    if similarity < 0.65:
        return False

    support_matches = 0
    for field in ("city", "deadline"):
        left_value = left.get(field) or ""
        right_value = right.get(field) or ""
        if left_value and right_value:
            if left_value != right_value:
                return False
            support_matches += 1

    left_channels = {value for value in (left.get("url"), left.get("email")) if value}
    right_channels = {value for value in (right.get("url"), right.get("email")) if value}
    if left_channels and right_channels:
        if not left_channels & right_channels:
            return False
        support_matches += 1

    return support_matches > 0 or similarity >= 0.9


def journal_identities(path: Path) -> list[dict]:
    identities: list[dict] = []
    if not path.exists():
        return identities
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if entry.get("status") == "created" and isinstance(entry.get("identity"), dict):
            identities.append(entry["identity"])
    return identities


def clean_application_email(value: str) -> str | None:
    for part in re.split(r"[;,\s]+", value or ""):
        candidate = re.sub(r"^mailto:", "", part, flags=re.I).strip()
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", candidate):
            return candidate
    return None


def clean_application_url(value: str) -> str | None:
    for part in re.split(r"\s*;\s*", value or ""):
        candidate = part.strip()
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc and "@" not in parsed.netloc:
            return candidate
    return None


def fit_application_url(value: str) -> str | None:
    """Retourne une URL compatible avec la limite KamerJob de 200 caractères."""
    url = clean_application_url(value)
    if not url or len(url) <= 200:
        return url
    parsed = urlparse(url)
    without_tracking = parsed._replace(query="", fragment="").geturl()
    return without_tracking if len(without_tracking) <= 200 else None


def infer_company(title: str) -> str:
    text = re.sub(r"\s+", " ", title).strip()
    patterns = [
        rf"^recrutement\s+(.+?)(?=\s+(?:{MONTH_PATTERN})\s+\d{{4}}|\s*[:–—-])",
        r"^(.+?)\s+(?:recrute(?:ment)?|recherche|is looking for)\b",
        r"^offre(?:s)? d['’]emploi\s+(?:chez|auprès de)\s+(.+?)(?=\s*[:–—-]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            company = match.group(1).strip(" :–—-")
            company = re.sub(
                r"^(?:chez\s+|(?:à|a)\s+la\s+multinationale\s+|(?:à|a)\s+l['’]|"
                r"la\s+société\s+|l['’]agence\s+)",
                "",
                company,
                flags=re.I,
            )
            company = re.sub(r"\s+20\d{2}$", "", company).strip()
            return company
    return ""


def infer_sector(row: dict[str, str], fallback: int) -> int:
    haystack = f" {normalized(row.get('title'))} {normalized(row.get('summary'))} "
    for sector_id, keywords in SECTOR_RULES:
        if any(normalized(keyword) in haystack for keyword in keywords):
            return sector_id
    return fallback


def infer_job_type(row: dict[str, str], fallback: int) -> int:
    haystack = f" {normalized(row.get('title'))} {normalized(row.get('summary'))} "
    for job_type_id, keywords in JOB_TYPE_RULES:
        if any(normalized(keyword) in haystack for keyword in keywords):
            return job_type_id
    return fallback


def infer_experience(value: str) -> str:
    text = normalized(value)
    numbers = [int(item) for item in re.findall(r"\d+", text)]
    if any(word in text for word in ("senior", "expert", "plus de 5")) or (numbers and max(numbers) >= 5):
        return "senior"
    if any(word in text for word in ("intermediaire", "confirmé", "confirme", "mid")) or (numbers and max(numbers) >= 3):
        return "mid"
    return "junior"


def parse_salary(value: str) -> tuple[int | None, int | None]:
    numbers = []
    for item in re.findall(r"\d[\d\s.,]*", value or ""):
        digits = re.sub(r"\D", "", item)
        if digits:
            numbers.append(int(digits))
    if not numbers:
        return None, None
    if len(numbers) == 1:
        return numbers[0], None
    return min(numbers[:2]), max(numbers[:2])


def complete_description(value: str) -> str:
    """Évite de publier un résumé interrompu au milieu d'une phrase.

    Les scrapers limitent les résumés à 300 caractères. Lorsqu'une coupure est
    visible, on revient à la dernière fin de phrase fiable. Sans ponctuation de
    fin exploitable, le texte est conservé afin de ne pas produire une
    description presque vide.
    """
    text = re.sub(r"\s+", " ", value or "").strip()
    # Une description courte peut volontairement ne pas se terminer par un
    # point. La coupure automatique des scrapers est, elle, située à 300
    # caractères : on ne corrige que les textes proches de cette limite.
    if len(text) < 295 or re.search(r"[.!?…][\"'»”)]*$", text):
        return text

    sentence_ends = [
        match.end()
        for match in re.finditer(
            r"(?<!\b[A-ZÀ-Ý])[.!?…](?=(?:[\"'»”)]*)\s+[A-ZÀ-Ý0-9]|(?:[\"'»”)]*)$)",
            text,
        )
        if match.end() >= 50
    ]
    if sentence_ends:
        return text[:sentence_ends[-1]].rstrip()

    # Aucun point de phrase fiable : au minimum, ne jamais publier un mot
    # sectionné. L'ellipse indique explicitement que l'extrait continue.
    last_word = text.rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{last_word}…" if last_word else text


def build_payload(
    row: dict[str, str],
    region_ids: dict[str, int],
    default_sector: int,
    default_job_type: int,
) -> tuple[dict | None, str | None]:
    title = (row.get("title") or "").strip()
    description = complete_description(row.get("summary") or "")
    company = infer_company(title)
    email = clean_application_email(row.get("apply_email", ""))
    original_url = clean_application_url(row.get("apply_url", ""))
    url = fit_application_url(row.get("apply_url", ""))
    application_address = ""
    if original_url and not url:
        application_address = f"Candidature en ligne : {original_url}"
    if not email and not url and not application_address:
        source_label = {
            "cameroondesks": "CameroonDesks",
            "jobincamer": "JobinCamer",
            "jobcameroun": "Job Cameroun",
        }.get((row.get("source") or "").strip(), "la source de l'annonce")
        application_address = (
            f"Consulter l'annonce originale sur {source_label} pour les modalités "
            "de candidature."
        )
    if not title or not description:
        return None, "titre ou description manquant"
    if not company:
        company = "Entreprise non précisée"

    region_name = (row.get("region") or "").strip()
    region = region_ids.get(normalized(region_name), region_ids.get(normalized("Partout au Cameroun")))
    if not region:
        return None, "région KamerJob introuvable"

    mode = normalized(row.get("work_mode"))
    remote_mode = "remote" if "teletravail" in mode else "hybrid" if "hybride" in mode else "onsite"
    salary_min, salary_max = parse_salary(row.get("salary", ""))
    deadline = (row.get("deadline") or "").strip() or None
    if deadline:
        deadline = deadline[:10]

    payload = {
        "kind": "job",
        "language": "fr",
        "title": title,
        "description": description,
        "cover_image": None,
        "display_mode": "standard",
        "tags": row.get("source", ""),
        "region": region,
        "city": (row.get("ville") or "").strip(),
        "expires_at": deadline,
        "company": None,
        "company_name": company,
        "company_logo": None,
        "sector": infer_sector(row, default_sector),
        "job_type": infer_job_type(row, default_job_type),
        "remote_mode": remote_mode,
        "is_international": False,
        "is_student_job": False,
        "experience_level": infer_experience(row.get("experience", "")),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": "XAF",
        "salary_visible": bool(salary_min or salary_max),
        "requirements": (row.get("experience") or "").strip(),
        "application_url": url,
        "application_email": email,
        "application_address": application_address,
    }
    return payload, None


def authenticate(session: requests.Session, env_path: Path) -> None:
    values = load_env(env_path)
    email = os.environ.get("KAMERJOB_EMAIL") or values.get("KAMERJOB_EMAIL", "")
    password = os.environ.get("KAMERJOB_PASSWORD") or values.get("KAMERJOB_PASSWORD", "")
    if not email or not password:
        raise RuntimeError(f"Identifiants manquants dans {env_path}")
    response = session.post(
        f"{BASE_URL}/api/auth/token/",
        json={"email": email, "password": password, "use_cookies": True},
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Échec de connexion KamerJob (HTTP {response.status_code})")


def fetch_all(session: requests.Session, path: str) -> list[dict]:
    url = f"{BASE_URL}/api/{path.lstrip('/')}"
    results: list[dict] = []
    while url:
        response = None
        for attempt in range(3):
            try:
                response = session.get(url, timeout=30)
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
        assert response is not None
        data = response.json()
        if isinstance(data, list):
            return data
        results.extend(data.get("results", []))
        url = data.get("next")
    return results


def append_journal(path: Path, entry: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def journal_created_titles(path: Path) -> set[str]:
    titles: set[str] = set()
    if not path.exists():
        return titles
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if entry.get("status") == "created" and entry.get("title"):
            titles.add(normalized(entry["title"]))
    return titles


def journal_created_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if entry.get("status") == "created" and entry.get("id"):
            ids.add(str(entry["id"]))
    return ids


def journal_published_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if entry.get("status") == "published" and entry.get("id"):
            ids.add(str(entry["id"]))
    return ids


def journal_final_statuses(path: Path) -> dict[str, str]:
    statuses: dict[str, str] = {}
    if not path.exists():
        return statuses
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if entry.get("id") and entry.get("status") in {
            "created",
            "published",
            "pending_review",
        }:
            statuses[str(entry["id"])] = str(entry["status"])
    return statuses


def has_application_channel(listing: dict) -> bool:
    """Un email ou une URL dédiée est obligatoire pour l'approbation automatique."""
    return bool(
        clean_application_email(str(listing.get("application_email") or ""))
        or clean_application_url(str(listing.get("application_url") or ""))
    )


def publish_pending_from_journal(
    session: requests.Session,
    journal_path: Path,
) -> tuple[int, int, int]:
    """Publie uniquement les annonces créées par ce script et encore en modération."""
    unresolved_ids = {
        listing_id
        for listing_id, status in journal_final_statuses(journal_path).items()
        if status == "created"
    }
    if not unresolved_ids:
        return 0, 0, 0
    published = 0
    review_pending = 0
    failed = 0
    for listing_id in unresolved_ids:
        try:
            detail = session.get(
                f"{BASE_URL}/api/admin/listings/{listing_id}/", timeout=30
            )
            detail.raise_for_status()
            item = detail.json()
            title = item.get("title") or listing_id
            if not has_application_channel(item):
                if item.get("status") == "published":
                    response = session.patch(
                        f"{BASE_URL}/api/admin/listings/{listing_id}/status/",
                        json={"status": "pending_review"},
                        timeout=30,
                    )
                    response.raise_for_status()
                print(f"EN MODÉRATION  {title} — email/URL de candidature absent")
                review_pending += 1
                append_journal(
                    journal_path,
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "status": "pending_review",
                        "id": listing_id,
                        "title": title,
                        "reason": "missing_application_email_or_url",
                    },
                )
                continue
            if item.get("status") == "pending_review":
                response = session.patch(
                    f"{BASE_URL}/api/admin/listings/{listing_id}/status/",
                    json={"status": "published"},
                    timeout=30,
                )
                response.raise_for_status()
                published += 1
                print(f"PUBLIÉ   {title}")
            elif item.get("status") != "published":
                print(
                    f"MODÉRATION IGNORÉE  {title} — statut {item.get('status')}",
                    file=sys.stderr,
                )
                continue
            append_journal(
                journal_path,
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "published",
                    "id": listing_id,
                    "title": title,
                },
            )
        except (requests.RequestException, ValueError) as exc:
            failed += 1
            error_detail = ""
            if isinstance(exc, requests.RequestException) and exc.response is not None:
                try:
                    error_detail = json.dumps(exc.response.json(), ensure_ascii=False)
                except ValueError:
                    error_detail = f"HTTP {exc.response.status_code}"
            print(
                f"ÉCHEC MODÉRATION  {listing_id} — {error_detail or exc}",
                file=sys.stderr,
            )
    return published, review_pending, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Publie le CSV d'emplois vers KamerJob")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="CSV à publier")
    parser.add_argument("--env", default=DEFAULT_ENV, help="fichier local contenant les identifiants")
    parser.add_argument("--journal", default=DEFAULT_JOURNAL, help="journal JSONL des envois")
    parser.add_argument(
        "--source",
        action="append",
        choices=("cameroondesks", "jobincamer", "jobcameroun"),
        help=(
            "source à publier (répétable ; par défaut : cameroondesks, "
            "jobincamer et jobcameroun)"
        ),
    )
    parser.add_argument("--send", action="store_true", help="effectuer les créations (sinon simulation)")
    parser.add_argument("--limit", type=int, help="nombre maximal de nouvelles offres à traiter")
    parser.add_argument("--default-sector", type=int, default=21, help="secteur de repli (défaut: 21, conseil)")
    parser.add_argument("--default-job-type", type=int, default=10, help="contrat de repli (défaut: 10, temps plein)")
    parser.add_argument("--verbose", action="store_true", help="afficher aussi chaque doublon et offre ignorée")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": "KamerJob CSV Publisher/1.0"})
    try:
        authenticate(session, Path(args.env))
        regions = fetch_all(session, "regions/")
        existing = fetch_all(session, "jobs/?page_size=100")
        pending_existing = fetch_all(
            session, "admin/listings/?status=pending_review&page_size=100"
        )
        companies = fetch_all(session, "companies/?page_size=100")
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 1

    region_ids = {normalized(item.get("name_fr") or item.get("name")): item["id"] for item in regions}
    existing_titles = {normalized(item.get("title")) for item in existing}
    existing_titles.update(normalized(item.get("title")) for item in pending_existing)
    existing_titles.update(journal_created_titles(Path(args.journal)))
    seen_identities = [listing_identity(item) for item in existing]
    seen_identities.extend(journal_identities(Path(args.journal)))
    company_ids = {normalized(item.get("name")): item["id"] for item in companies}
    created_this_run: set[str] = set()
    selected_sources = set(args.source or DEFAULT_SOURCES)
    counts = {
        "ready": 0,
        "duplicate": 0,
        "skipped": 0,
        "source_filtered": 0,
        "created": 0,
        "failed": 0,
        "published": 0,
        "review_pending": 0,
        "moderation_failed": 0,
    }

    with Path(args.input).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        if (row.get("source") or "").strip() not in selected_sources:
            counts["source_filtered"] += 1
            continue
        title = (row.get("title") or "").strip()
        key = normalized(title)
        if key in existing_titles or key in created_this_run:
            counts["duplicate"] += 1
            if args.verbose:
                print(f"DOUBLON  {title} — titre déjà présent")
            continue
        payload, reason = build_payload(row, region_ids, args.default_sector, args.default_job_type)
        if reason:
            counts["skipped"] += 1
            if args.verbose:
                print(f"IGNORÉ   {title} — {reason}")
            continue
        payload["company"] = company_ids.get(normalized(payload["company_name"]))
        identity = listing_identity(payload)
        composite_duplicate = next(
            (item for item in seen_identities if identities_match(identity, item)),
            None,
        )
        if composite_duplicate is not None:
            counts["duplicate"] += 1
            if args.verbose:
                print(
                    f"DOUBLON  {title} — même entreprise/poste/ville/date/candidature "
                    f"que {composite_duplicate.get('title') or 'une offre existante'}"
                )
            continue
        if args.limit is not None and counts["ready"] >= args.limit:
            break
        counts["ready"] += 1
        print(
            f"{'ENVOI' if args.send else 'PRÊT'}    {title} | "
            f"entreprise={payload['company_name']} secteur={payload['sector']} "
            f"contrat={payload['job_type']} région={payload['region']}"
        )
        if not args.send:
            seen_identities.append(identity)
            continue
        try:
            response = session.post(f"{BASE_URL}/api/admin/listings/", json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            created_this_run.add(key)
            seen_identities.append(identity)
            counts["created"] += 1
            append_journal(
                Path(args.journal),
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "created",
                    "id": data.get("id"),
                    "title": title,
                    "identity": identity,
                },
            )
        except (requests.RequestException, ValueError) as exc:
            counts["failed"] += 1
            detail = ""
            if getattr(exc, "response", None) is not None:
                try:
                    detail = json.dumps(exc.response.json(), ensure_ascii=False)
                except ValueError:
                    detail = f"HTTP {exc.response.status_code}"
            print(f"ÉCHEC    {title} — {detail or exc}", file=sys.stderr)
            append_journal(
                Path(args.journal),
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "failed",
                    "title": title,
                    "error": detail or str(exc),
                },
            )

    if args.send:
        try:
            (
                counts["published"],
                counts["review_pending"],
                counts["moderation_failed"],
            ) = publish_pending_from_journal(session, Path(args.journal))
        except (requests.RequestException, ValueError) as exc:
            counts["moderation_failed"] += 1
            print(f"ÉCHEC DE LA REPRISE DE MODÉRATION — {exc}", file=sys.stderr)

    mode = "ENVOI" if args.send else "SIMULATION"
    print(
        f"\n{mode}: {counts['ready']} prêtes, {counts['created']} créées, "
        f"{counts['duplicate']} doublons, {counts['skipped']} ignorées, "
        f"{counts['source_filtered']} hors sources, {counts['published']} publiées, "
        f"{counts['review_pending']} laissées en modération, "
        f"{counts['failed']} échecs d'envoi, "
        f"{counts['moderation_failed']} échecs de modération."
    )
    return 1 if counts["failed"] or counts["moderation_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
