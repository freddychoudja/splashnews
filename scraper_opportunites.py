"""Scraper de bourses et concours concernant le Cameroun - agrège plusieurs sources en un CSV."""

import argparse
import csv

from sources import cameroondesks_opportunites, infospratiques, opportunitydesk

SOURCES = {
    cameroondesks_opportunites.NAME: cameroondesks_opportunites.scrape,
    infospratiques.NAME: infospratiques.scrape,
    opportunitydesk.NAME: opportunitydesk.scrape,
}

FIELDNAMES = [
    "title", "published", "deadline", "source", "category",
    "location", "region", "ville", "apply_email", "apply_url", "summary",
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
    parser = argparse.ArgumentParser(description="Scrape les bourses et concours récents concernant le Cameroun")
    parser.add_argument(
        "--source", choices=list(SOURCES) + ["all"], default="all",
        help="Source à scraper (défaut : all)",
    )
    parser.add_argument("--days", type=int, default=30, help="Ne garder que les annonces des N derniers jours (défaut: 30)")
    parser.add_argument("--max-pages", type=int, default=20, help="Nombre max de pages à parcourir par source (défaut: 20)")
    parser.add_argument(
        "--include-expired", action="store_true",
        help="Inclure aussi les annonces dont la date limite est dépassée (exclues par défaut)",
    )
    parser.add_argument("--output", default="opportunites_cameroun.csv", help="Chemin du fichier CSV de sortie")
    args = parser.parse_args()

    source_names = list(SOURCES) if args.source == "all" else [args.source]
    rows = scrape_all(source_names, args.days, args.max_pages, args.include_expired)
    write_csv(rows, args.output)
    print(f"{len(rows)} annonces écrites dans {args.output}")


if __name__ == "__main__":
    main()
