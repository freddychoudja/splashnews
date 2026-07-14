"""Synchronisation quotidienne : scrape puis publie sur KamerJob."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import requests

from scraper import SOURCES, write_csv


DEFAULT_SOURCES = ("cameroondesks", "jobincamer")
DEFAULT_OUTPUT = "offres_emploi_cameroun.csv"


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
        "1/2 Scraping de CameroonDesks et JobinCamer "
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

    completed = subprocess.run(command, check=False)
    if completed.returncode:
        print(
            "Synchronisation terminée avec au moins une erreur de publication.",
            file=sys.stderr,
        )
        return completed.returncode
    print("Synchronisation KamerJob terminée.", flush=True)
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
