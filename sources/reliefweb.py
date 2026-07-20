"""Source: ReliefWeb Jobs (API publique UN-OCHA), filtrée sur le Cameroun."""

import time
from datetime import date, datetime, timedelta, timezone

import requests

from . import common

API_URL = "https://api.reliefweb.int/v2/jobs"
NAME = "reliefweb"
PAGE_SIZE = 100
REQUEST_TIMEOUT = (5, 20)


def fetch_page(offset):
    params = {
        "appname": "kamerjob",
        "profile": "full",
        "limit": PAGE_SIZE,
        "offset": offset,
        "sort[]": "date.created:desc",
        "filter[field]": "country.iso3",
        "filter[value]": "cmr",
    }
    response = requests.get(API_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _names(values):
    return [value.get("name", "") for value in values or [] if value.get("name")]


def parse_job(item):
    fields = item.get("fields", {})
    published = datetime.fromisoformat(fields["date"]["created"].replace("Z", "+00:00"))
    closing = fields.get("date", {}).get("closing", "")
    deadline = date.fromisoformat(closing[:10]) if closing else None

    cities = _names(fields.get("city"))
    location = "; ".join(cities) or "Cameroun"
    region, ville = common.extract_region_ville(location)

    body_html = fields.get("body-html", "")
    apply_html = fields.get("how_to_apply-html", "")
    apply_emails, apply_urls = common.extract_apply_links(apply_html)
    # L'annonce canonique reste un canal sûr lorsque les instructions ne
    # contiennent aucun lien direct (formulaire parfois rendu côté client).
    canonical_url = fields.get("url_alias") or fields.get("url", "")
    if not apply_urls and canonical_url:
        apply_urls.append(canonical_url)

    experience = "; ".join(_names(fields.get("experience")))
    return common.make_row(
        title=fields.get("title", "").strip(),
        published=published,
        deadline=deadline,
        location=location,
        region=region,
        ville=ville,
        experience=experience,
        work_mode=common.extract_work_mode(common.strip_html(body_html)),
        apply_email="; ".join(apply_emails),
        apply_url="; ".join(apply_urls),
        summary=common.strip_html(body_html)[:300],
        source=NAME,
    )


def scrape(since_days, max_pages, include_expired=False):
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    results = []

    for page in range(max_pages):
        items = fetch_page(page * PAGE_SIZE).get("data", [])
        if not items:
            break

        stop = False
        for item in items:
            row = parse_job(item)
            if row["published"] < cutoff:
                stop = True
                break
            deadline = date.fromisoformat(row["deadline"]) if row["deadline"] else None
            if not include_expired and common.is_expired(deadline):
                continue
            results.append(row)

        if stop or len(items) < PAGE_SIZE:
            break
        time.sleep(0.5)

    return results
