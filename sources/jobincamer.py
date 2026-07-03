"""Source: JobinCamer (portail d'offres Drupal, catégorie 'jobs')."""

import re
import time
from datetime import datetime, timedelta, timezone

import requests

from . import common

BASE_URL = "https://www.jobincamer.com"
LISTING_URL = f"{BASE_URL}/adverts/jobs"
NAME = "jobincamer"
NON_APPLY_DOMAINS = ("jobincamer.com",)
TIMEZONE_WAT = timezone(timedelta(hours=1))  # Afrique/Douala, pas d'heure d'été

JOB_CARD_RE = re.compile(
    r'<a href="(/job/[^"]+)" hreflang="zxx">([^<]+)</a>.*?'
    r'<a href="/employer/[^"]+" hreflang="zxx">[^<]+</a>\s*\|\s*'
    r'<i class="fas fa-map-marker-alt"></i>\s*(.*?)\s*\|\s*'
    r"Publié le (\d{2}-\d{2}-\d{4})\s*\|\s*Postuler avant le (\d{2}-\d{2}-\d{4})",
    re.S,
)
SUMMARY_LIST_ITEM_RE = re.compile(
    r'<li class="list-group-item"><b>([^<]+):</b>(.*?)</li>', re.S
)
BODY_RE = re.compile(
    r'<div class="field field--name-body[^"]*"[^>]*>(.*?)</div>\s*'
    r"<!-- END OUTPUT from 'themes/contrib/bootstrap/templates/field/field.html.twig' -->",
    re.S,
)
APPLY_FORM_RE = re.compile(r'class="job-apply-btn">\s*<a href="([^"]+)"')


def parse_listing(html_text):
    jobs = []
    for match in JOB_CARD_RE.finditer(html_text):
        job_path, title, location, published_str, deadline_str = match.groups()
        published = datetime.strptime(published_str, "%d-%m-%Y").replace(tzinfo=TIMEZONE_WAT)
        deadline = datetime.strptime(deadline_str, "%d-%m-%Y").date()
        jobs.append(
            {
                "url": BASE_URL + job_path,
                "title": common.strip_html(title).strip(),
                "location": common.strip_html(location).strip(),
                "published": published,
                "deadline": deadline,
            }
        )
    return jobs


def fetch_job_detail(url):
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_job_detail(job, html_text):
    summary_fields = {}
    for label, value in SUMMARY_LIST_ITEM_RE.findall(html_text):
        summary_fields[label.strip()] = common.strip_html(value).strip()

    body_match = BODY_RE.search(html_text)
    body_html = body_match.group(1) if body_match else ""
    summary = common.strip_html(body_html)[:300]

    apply_emails, apply_urls = common.extract_apply_links(body_html, NON_APPLY_DOMAINS)
    if not apply_emails and not apply_urls:
        form_match = APPLY_FORM_RE.search(html_text)
        if form_match:
            apply_urls = [BASE_URL + form_match.group(1)]

    body_lines = common.normalize_lines(body_html)
    salary = common.extract_labeled_field(body_lines, common.SALARY_LABELS)
    work_mode = common.extract_work_mode(body_lines)

    location = summary_fields.get("Localisation", job["location"])
    if location:
        region, ville = common.extract_region_ville(location)
    else:
        region, ville = common.extract_region_ville_unique(body_lines)

    return common.make_row(
        title=job["title"],
        published=job["published"],
        deadline=job["deadline"],
        location=location,
        region=region,
        ville=ville,
        experience=summary_fields.get("Experience requise", ""),
        salary=salary,
        work_mode=work_mode,
        apply_email="; ".join(apply_emails),
        apply_url="; ".join(apply_urls),
        summary=summary,
        source=NAME,
    )


def scrape(since_days, max_pages, include_expired=False):
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    resp = requests.get(LISTING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    jobs = parse_listing(resp.text)

    results = []
    for job in jobs:
        if job["published"] < cutoff:
            continue
        if not include_expired and common.is_expired(job["deadline"]):
            continue
        detail_html = fetch_job_detail(job["url"])
        results.append(parse_job_detail(job, detail_html))
        time.sleep(0.3)

    return results
