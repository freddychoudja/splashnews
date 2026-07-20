"""Source: MinaJobs Cameroun, via son flux RSS public toutes catégories."""

import html
import re
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests

from . import common

FEED_URL = "https://cameroun.minajobs.net/rss/all/"
NAME = "minajobs"
REQUEST_TIMEOUT = (5, 20)
DETAIL_RE = re.compile(r'<div class="detail-font"[^>]*>(.*?)</div>', re.I | re.S)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PLAIN_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


def fetch_feed():
    response = requests.get(
        FEED_URL,
        headers={"User-Agent": "KamerJob/1.0 (+https://kamerjob.com)"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.content


def fetch_detail(url):
    response = requests.get(
        url,
        headers={"User-Agent": "KamerJob/1.0 (+https://kamerjob.com)"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.text


def _text(item, tag):
    node = item.find(tag)
    return (node.text or "").strip() if node is not None else ""


def extract_direct_channels(detail_html):
    """Extrait uniquement les coordonnées présentes dans le corps de l'offre."""
    body_match = DETAIL_RE.search(detail_html)
    body_html = body_match.group(1) if body_match else ""
    emails, urls = common.extract_apply_links(body_html, ("minajobs.net",))

    body_text = html.unescape(common.strip_html(body_html))
    for email_address in EMAIL_RE.findall(body_text):
        mailto = f"mailto:{email_address}"
        if mailto not in emails:
            emails.append(mailto)
    for url in PLAIN_URL_RE.findall(body_text):
        url = url.rstrip(".,);]")
        if "minajobs.net" not in url.lower() and url not in urls:
            urls.append(url)
    return emails, urls


def parse_item(item, detail_html=""):
    title = common.strip_html(_text(item, "title")).strip()
    published = parsedate_to_datetime(_text(item, "pubDate"))
    if published.tzinfo is None:
        published = published.replace(tzinfo=common.CAMEROON_TZ)

    description_html = _text(item, "description")
    # Certains générateurs RSS placent le corps complet dans content:encoded.
    for child in item:
        if child.tag.endswith("}encoded") and (child.text or "").strip():
            description_html = child.text.strip()
            break

    text = common.normalize_lines(description_html)
    location = common.extract_labeled_field(text, common.LOCATION_LABELS)
    if location:
        region, ville = common.extract_region_ville(location)
    else:
        region, ville = common.extract_region_ville_unique(text)

    deadline = common.extract_deadline(text)
    apply_emails, apply_urls = common.extract_apply_links(description_html, ("minajobs.net",))
    detail_emails, detail_urls = extract_direct_channels(detail_html)
    for email_address in detail_emails:
        if email_address not in apply_emails:
            apply_emails.append(email_address)
    for url in detail_urls:
        if url not in apply_urls:
            apply_urls.append(url)

    return common.make_row(
        title=title,
        published=published,
        deadline=deadline,
        location=location,
        region=region,
        ville=ville,
        experience=common.extract_labeled_field(text, common.EXPERIENCE_LABELS),
        salary=common.extract_labeled_field(text, common.SALARY_LABELS),
        work_mode=common.extract_work_mode(text),
        apply_email="; ".join(apply_emails),
        apply_url="; ".join(apply_urls),
        summary=common.strip_html(description_html)[:300],
        source=NAME,
    )


def scrape(since_days, max_pages, include_expired=False):
    del max_pages  # Un flux RSS est une ressource unique, sans pagination.
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    root = ElementTree.fromstring(fetch_feed())
    results = []

    for item in root.findall("./channel/item"):
        # Évite une requête de détail pour les entrées déjà hors fenêtre.
        feed_row = parse_item(item)
        if feed_row["published"] < cutoff:
            continue
        original_url = _text(item, "link")
        try:
            detail_html = fetch_detail(original_url) if original_url else ""
        except requests.RequestException:
            continue
        row = parse_item(item, detail_html)
        deadline = date.fromisoformat(row["deadline"]) if row["deadline"] else None
        if not include_expired and common.is_expired(deadline):
            continue
        # Une URL MinaJobs n'est jamais un canal de candidature. Sans contact
        # recruteur direct, l'annonce n'est pas transmise à KamerJob.
        if not row["apply_email"] and not row["apply_url"]:
            continue
        results.append(row)
        time.sleep(0.3)

    return results
