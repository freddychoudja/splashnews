"""Source: CameroonDesks (bourses, concours) — même blog Blogger que sources.cameroondesks,
labels différents."""

import time
from datetime import date, datetime, timedelta, timezone

import requests

from . import common

FEED_URL_TEMPLATE = "https://www.cameroondesks.com/feeds/posts/default/-/{label}"
PAGE_SIZE = 25
NAME = "cameroondesks"
NON_APPLY_DOMAINS = ("cameroondesks.com",)

# Label Blogger -> catégorie exposée dans le CSV.
LABELS = {
    "bourses": "bourse",
    "concours": "concours",
}


def fetch_page(label, start_index):
    params = {
        "alt": "json",
        "max-results": PAGE_SIZE,
        "start-index": start_index,
    }
    resp = requests.get(FEED_URL_TEMPLATE.format(label=label), params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def parse_entry(entry, category):
    entry_id = entry.get("id", {}).get("$t", "")
    title = entry.get("title", {}).get("$t", "").strip()
    published = datetime.fromisoformat(entry.get("published", {}).get("$t", ""))

    content_html = entry.get("content", {}).get("$t", "")
    summary = common.strip_html(content_html)[:300]
    apply_emails, apply_urls = common.extract_apply_links(content_html, NON_APPLY_DOMAINS)

    lines_text = common.normalize_lines(content_html)
    location = common.extract_labeled_field(lines_text, common.LOCATION_LABELS)
    deadline = common.extract_deadline(lines_text)

    if location:
        region, ville = common.extract_region_ville(location)
    else:
        region, ville = common.extract_region_ville_unique(lines_text)

    return {
        "id": entry_id,
        "title": title,
        "published": published,
        "deadline": deadline.isoformat() if deadline else "",
        "source": NAME,
        "category": category,
        "location": location,
        "region": region,
        "ville": ville,
        "apply_email": "; ".join(apply_emails),
        "apply_url": "; ".join(apply_urls),
        "summary": summary,
    }


def scrape_label(label, category, since_days, max_pages, include_expired):
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    results = []
    start_index = 1
    pages_fetched = 0
    stop = False

    while not stop and pages_fetched < max_pages:
        data = fetch_page(label, start_index)
        entries = data.get("feed", {}).get("entry", [])
        if not entries:
            break

        for entry in entries:
            row = parse_entry(entry, category)
            if row["published"] < cutoff:
                stop = True
                break
            deadline = date.fromisoformat(row["deadline"]) if row["deadline"] else None
            if not include_expired and common.is_expired(deadline):
                continue
            results.append(row)

        pages_fetched += 1
        start_index += PAGE_SIZE
        time.sleep(0.5)

    return results


def scrape(since_days, max_pages, include_expired=False):
    # Un même post peut être tagué à la fois "bourses" et "concours" (ex: labels
    # ["blog", "concours"]) : on déduplique par id Blogger au cas où les deux
    # labels se recouperaient.
    seen_ids = set()
    results = []
    for label, category in LABELS.items():
        for row in scrape_label(label, category, since_days, max_pages, include_expired):
            if row["id"] in seen_ids:
                continue
            seen_ids.add(row["id"])
            row.pop("id")
            results.append(row)
    return results
