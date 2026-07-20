"""Synchronisation quotidienne : scrape puis publie sur KamerJob."""

from __future__ import annotations

import argparse
import os
import smtplib
import subprocess
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import requests

from scraper import SOURCES, write_csv


DEFAULT_SOURCES = (
    "cameroondesks", "jobincamer", "jobcameroun", "reliefweb", "minajobs",
)
DEFAULT_OUTPUT = "offres_emploi_cameroun.csv"


def load_local_env(path: Path) -> None:
    """Charge les valeurs locales sans remplacer l'environnement du runner."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def send_email_report(subject: str, body: str) -> bool:
    """Envoie le rapport avec les paramètres SMTP fournis par l'environnement."""
    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    recipient = (
        os.environ.get("REPORT_EMAIL_TO", "").strip()
        or os.environ.get("KAMERJOB_EMAIL", "").strip()
    )
    sender = os.environ.get("SMTP_FROM", "").strip() or user
    if not all((host, user, password, recipient, sender)):
        print(
            "Rapport email non envoyé : configuration SMTP incomplète.",
            file=sys.stderr,
        )
        return False

    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        print("Rapport email non envoyé : SMTP_PORT invalide.", file=sys.stderr)
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
                smtp.login(user, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(user, password)
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        print(f"Échec de l'envoi du rapport email : {exc}", file=sys.stderr)
        return False

    print(f"Rapport envoyé à {recipient}.", flush=True)
    return True


def report_body(*, rows_count: int, status: str, output: Path, details: str = "") -> str:
    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    body = (
        "Rapport de synchronisation KamerJob\n\n"
        f"Date : {generated_at}\n"
        f"Statut : {status}\n"
        f"Offres collectées : {rows_count}\n"
        f"Fichier : {output}\n"
    )
    if details.strip():
        body += f"\nDétails de publication :\n{details.strip()}\n"
    return body


def scrape_sources(source_names: tuple[str, ...], days: int, max_pages: int) -> list[dict]:
    rows: list[dict] = []
    for name in source_names:
        try:
            rows.extend(SOURCES[name](days, max_pages, include_expired=False))
        except requests.RequestException as exc:
            print(f"Avertissement: source {name} ignorée ({exc})", file=sys.stderr)
    rows.sort(key=lambda row: row["published"], reverse=True)
    return rows


def run_sync(
    *,
    days: int,
    max_pages: int,
    output: Path,
    dry_run: bool,
    limit: int | None,
) -> int:
    print(
        "1/2 Scraping de CameroonDesks, JobinCamer, JobCameroun, ReliefWeb et MinaJobs "
        f"sur les {days} derniers jours…",
        flush=True,
    )
    rows = scrape_sources(DEFAULT_SOURCES, days, max_pages)
    write_csv(rows, output)
    print(f"{len(rows)} offres extraites dans {output}", flush=True)

    if not rows:
        print(
            "Aucune offre extraite : publication annulée par sécurité.",
            file=sys.stderr,
        )
        send_email_report(
            "[KamerJob] Échec de la synchronisation",
            report_body(
                rows_count=0,
                status="ÉCHEC — aucune offre extraite",
                output=output,
            ),
        )
        return 1

    print(
        f"2/2 {'Simulation de la publication' if dry_run else 'Publication sur KamerJob'}…",
        flush=True,
    )
    command = [
        sys.executable,
        str(Path(__file__).with_name("publish_kamerjob.py")),
        "--input",
        str(output),
    ]
    if not dry_run:
        command.append("--send")
    if limit is not None:
        command.extend(("--limit", str(limit)))

    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    publication_log = completed.stdout if isinstance(completed.stdout, str) else ""
    if publication_log:
        print(publication_log, end="" if publication_log.endswith("\n") else "\n")
    if completed.returncode:
        print(
            "Synchronisation terminée avec au moins une erreur de publication.",
            file=sys.stderr,
        )
        send_email_report(
            "[KamerJob] Synchronisation terminée avec erreur",
            report_body(
                rows_count=len(rows),
                status=f"ÉCHEC — publication retournée avec le code {completed.returncode}",
                output=output,
                details=publication_log,
            ),
        )
        return completed.returncode
    print("Synchronisation KamerJob terminée.", flush=True)
    send_email_report(
        "[KamerJob] Rapport de synchronisation réussi",
        report_body(
            rows_count=len(rows),
            status="SUCCÈS" if not dry_run else "SUCCÈS — simulation",
            output=output,
            details=publication_log,
        ),
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape CameroonDesks/JobinCamer puis publie les nouvelles offres sur KamerJob"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="fenêtre de scraping en jours (défaut : 30)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="nombre maximal de pages par source (défaut : 20)",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="CSV intermédiaire")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="scraper et simuler sans publier",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="limiter le nombre de nouvelles offres publiées",
    )
    args = parser.parse_args()
    load_local_env(Path(".env.kamerjob"))
    if args.days <= 0 or args.max_pages <= 0:
        parser.error("--days et --max-pages doivent être strictement positifs")
    if args.limit is not None and args.limit < 0:
        parser.error("--limit doit être positif ou nul")
    return run_sync(
        days=args.days,
        max_pages=args.max_pages,
        output=Path(args.output),
        dry_run=args.dry_run,
        limit=args.limit,
    )


if __name__ == "__main__":
    raise SystemExit(main())
