"""Scraper d'offres d'emploi Cameroun - agrège plusieurs sources en un seul CSV."""

import argparse
import csv

from sources import cameroondesks, jobincamer

SOURCES = {
    cameroondesks.NAME: cameroondesks.scrape,
    jobincamer.NAME: jobincamer.scrape,
}

FIELDNAMES = [
    "title", "published", "deadline", "source", "location", "region", "ville",
    "experience", "salary", "work_mode", "apply_email", "apply_url", "summary",
]


def scrape_all(source_names, since_days, max_pages, include_expired):
    rows = []
    for name in source_names:
        rows.extend(SOURCES[name](since_days, max_pages, include_expired))
    rows.sort(key=lambda r: r["published"], reverse=True)
    return rows


def write_csv(rows, output_path):
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "published": row["published"].isoformat()})


def main():
    parser = argparse.ArgumentParser(description="Scrape les offres d'emploi récentes concernant le Cameroun")
    parser.add_argument(
        "--source", choices=list(SOURCES) + ["all"], default="all",
        help="Source à scraper (défaut : all)",
    )
    parser.add_argument("--days", type=int, default=30, help="Ne garder que les offres des N derniers jours (défaut: 30)")
    parser.add_argument("--max-pages", type=int, default=20, help="Nombre max de pages à parcourir par source (défaut: 20)")
    parser.add_argument(
        "--include-expired", action="store_true",
        help="Inclure aussi les offres dont la date limite de candidature est dépassée (exclues par défaut)",
    )
    parser.add_argument("--output", default="offres_emploi_cameroun.csv", help="Chemin du fichier CSV de sortie")
    args = parser.parse_args()

    source_names = list(SOURCES) if args.source == "all" else [args.source]
    rows = scrape_all(source_names, args.days, args.max_pages, args.include_expired)
    write_csv(rows, args.output)
    print(f"{len(rows)} offres écrites dans {args.output}")


if __name__ == "__main__":
    main()
