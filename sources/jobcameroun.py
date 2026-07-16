"""Source: Job Cameroun (job-cameroun.com) — chaque offre embarque un bloc JSON-LD
schema.org/JobPosting structuré (titre, dates, localisation), donc peu d'heuristiques
sont nécessaires ici contrairement aux autres sources."""

import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

from . import common

BASE_URL = "https://job-cameroun.com"
LISTING_URL = f"{BASE_URL}/offres"
NAME = "jobcameroun"
NON_APPLY_DOMAINS = ("job-cameroun.com", "play.google.com", "tiktok.com")
TIMEZONE_WAT = timezone(timedelta(hours=1))  # Afrique/Douala, pas d'heure d'été
PAGE_SIZE = 20
REQUEST_TIMEOUT = (5, 10)
REQUEST_ATTEMPTS = 2

OFFER_LINK_RE = re.compile(r'href="(/offre/\d+-[^"]+)"')
JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
# Le lien de candidature principal est distingué par sa classe CSS "btn-whatsapp" :
# les autres liens wa.me sur la page (bouton "Partager") ne sont pas des contacts
# de candidature et doivent être ignorés.
WHATSAPP_APPLY_RE = re.compile(r'<a href="(https://wa\.me/[^"]+)"[^>]*class="btn-whatsapp"')
# La description de l'offre est le seul endroit où un lien de candidature fourni par
# le recruteur peut apparaître ; le reste de la page (pub, contenu "sponsorisé",
# offres similaires...) contient des liens externes qui n'ont rien à voir.
STATIC_CONTENT_RE = re.compile(r'<div class="static-content[^"]*"[^>]*>(.*?)</div>', re.S)


def fetch_url(url, **kwargs):
    for attempt in range(REQUEST_ATTEMPTS):
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            )
            resp.raise_for_status()
            return resp.text
        except requests.RequestException:
            if attempt == REQUEST_ATTEMPTS - 1:
                raise
            time.sleep(1)


def fetch_listing_page(page):
    return fetch_url(LISTING_URL, params={"page": page})


def parse_listing(html_text):
    seen = []
    for path in OFFER_LINK_RE.findall(html_text):
        if path not in seen:
            seen.append(path)
    return [BASE_URL + path for path in seen]


def fetch_offer_detail(url):
    return fetch_url(url)


def parse_offer_detail(url, html_text):
    ld_match = JSON_LD_RE.search(html_text)
    posting = json.loads(ld_match.group(1)) if ld_match else {}

    published = datetime.strptime(posting["datePosted"], "%Y-%m-%d").replace(tzinfo=TIMEZONE_WAT)
    deadline = date.fromisoformat(posting["validThrough"]) if posting.get("validThrough") else None

    address = posting.get("jobLocation", {}).get("address", {})
    location = address.get("streetAddress", "")
    ville_hint = address.get("addressLocality", "") or location
    region, ville = common.extract_region_ville(ville_hint) if ville_hint else ("", "")

    description_html = "".join(STATIC_CONTENT_RE.findall(html_text))
    body_lines = common.normalize_lines(description_html)
    experience = common.extract_labeled_field(body_lines, common.EXPERIENCE_LABELS)
    salary = common.extract_labeled_field(body_lines, common.SALARY_LABELS)
    work_mode = common.extract_work_mode(body_lines)

    apply_emails, apply_urls = common.extract_apply_links(description_html, NON_APPLY_DOMAINS)
    whatsapp_match = WHATSAPP_APPLY_RE.search(html_text)
    if whatsapp_match and whatsapp_match.group(1) not in apply_urls:
        apply_urls.append(whatsapp_match.group(1))

    return common.make_row(
        title=posting.get("title", "").strip(),
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
        summary=common.strip_html(posting.get("description", ""))[:300],
        source=NAME,
    )


def scrape(since_days, max_pages, include_expired=False):
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    results = []
    page = 1
    stop = False

    while not stop and page <= max_pages:
        try:
            offer_urls = parse_listing(fetch_listing_page(page))
        except requests.RequestException as exc:
            print(f"Avertissement: page {page} de {NAME} ignorée ({exc})", file=sys.stderr)
            break
        if not offer_urls:
            break

        for offer_url in offer_urls:
            try:
                detail_html = fetch_offer_detail(offer_url)
            except requests.RequestException as exc:
                print(f"Avertissement: offre ignorée {offer_url} ({exc})", file=sys.stderr)
                continue
            row = parse_offer_detail(offer_url, detail_html)
            if row["published"] < cutoff:
                stop = True
                break
            deadline = date.fromisoformat(row["deadline"]) if row["deadline"] else None
            if not include_expired and common.is_expired(deadline):
                continue
            results.append(row)
            time.sleep(0.3)

        page += 1

    return results
