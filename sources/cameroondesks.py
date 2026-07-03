"""Source: CameroonDesks (blog Blogger, label 'jobs')."""

import time
from datetime import date, datetime, timedelta, timezone

import requests

from . import common

FEED_URL = "https://www.cameroondesks.com/feeds/posts/default/-/jobs"
PAGE_SIZE = 25
NAME = "cameroondesks"
NON_APPLY_DOMAINS = ("cameroondesks.com",)


def fetch_page(start_index):
    params = {
        "alt": "json",
        "max-results": PAGE_SIZE,
        "start-index": start_index,
    }
    resp = requests.get(FEED_URL, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def parse_entry(entry):
    title = entry.get("title", {}).get("$t", "").strip()
    published = datetime.fromisoformat(entry.get("published", {}).get("$t", ""))

    content_html = entry.get("content", {}).get("$t", "")
    summary = common.strip_html(content_html)[:300]
    apply_emails, apply_urls = common.extract_apply_links(content_html, NON_APPLY_DOMAINS)

    lines_text = common.normalize_lines(content_html)
    location = common.extract_labeled_field(lines_text, common.LOCATION_LABELS)
    experience = common.extract_labeled_field(lines_text, common.EXPERIENCE_LABELS)
    salary = common.extract_labeled_field(lines_text, common.SALARY_LABELS)
    work_mode = common.extract_work_mode(lines_text)
    deadline = common.extract_deadline(lines_text)

    if location:
        region, ville = common.extract_region_ville(location)
    else:
        region, ville = common.extract_region_ville_unique(lines_text)

    return common.make_row(
        title=title,
        published=published,
        deadline=deadline,
        location=location,
        region=region,
        ville=ville,
        experience=experience,
        salary=salary,
        work_mode=work_mode,
        apply_email="; ".join(apply_emails),
        apply_url="; ".join(apply_urls),
        summary=summary,
        source=NAME,
    )


def scrape(since_days, max_pages, include_expired=False):
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    results = []
    start_index = 1
    pages_fetched = 0
    stop = False

    while not stop and pages_fetched < max_pages:
        data = fetch_page(start_index)
        entries = data.get("feed", {}).get("entry", [])
        if not entries:
            break

        for entry in entries:
            row = parse_entry(entry)
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
