"""Source: Opportunity Desk (opportunitydesk.org, API REST WordPress) — plateforme
mondiale de bourses/concours/subventions, filtrée sur les annonces mentionnant le
Cameroun (`search=cameroon`) et limitée aux catégories pertinentes (on exclut
notamment `Hot Jobs`, hors périmètre de ce scraper)."""

import time
from datetime import date, datetime, timedelta, timezone

import requests

from . import common

API_URL = "https://opportunitydesk.org/wp-json/wp/v2/posts"
# Contests (11) -> concours ; Fellowships (24), Scholarships (6), Grants (30),
# Awards (29) -> bourse.
CONTEST_CATEGORY_IDS = {11}
BOURSE_CATEGORY_IDS = {24, 6, 30, 29}
CATEGORY_IDS = ",".join(str(i) for i in CONTEST_CATEGORY_IDS | BOURSE_CATEGORY_IDS)
PAGE_SIZE = 20
NAME = "opportunitydesk"
NON_APPLY_DOMAINS = ("opportunitydesk.org",)


def fetch_page(page):
    params = {
        "search": "cameroon",
        "categories": CATEGORY_IDS,
        "per_page": PAGE_SIZE,
        "page": page,
    }
    resp = requests.get(API_URL, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def parse_post(post):
    title = common.strip_html(post.get("title", {}).get("rendered", "")).strip()
    published = datetime.fromisoformat(post["date_gmt"]).replace(tzinfo=timezone.utc)
    category = "concours" if CONTEST_CATEGORY_IDS & set(post.get("categories", [])) else "bourse"

    content_html = post.get("content", {}).get("rendered", "")
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


def scrape(since_days, max_pages, include_expired=False):
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    results = []
    page = 1
    stop = False

    while not stop and page <= max_pages:
        data = fetch_page(page)
        if not data:
            break

        for post in data:
            row = parse_post(post)
            if row["published"] < cutoff:
                stop = True
                break
            deadline = date.fromisoformat(row["deadline"]) if row["deadline"] else None
            if not include_expired and common.is_expired(deadline):
                continue
            results.append(row)

        page += 1
        time.sleep(0.5)

    return results
