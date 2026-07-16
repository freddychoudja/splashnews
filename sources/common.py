"""Helpers partagés entre les différentes sources d'offres d'emploi."""

import html
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

CAMEROON_TZ = timezone(timedelta(hours=1))  # Afrique/Douala, pas d'heure d'été

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.,])")
HREF_RE = re.compile(r'href="([^"]+)"')
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>",
    re.I | re.S,
)

# Balises de bloc qui séparent visuellement deux informations dans un post ; on les
# convertit en retour à la ligne avant de retirer le reste des balises, pour ne pas
# fusionner deux champs "Label : valeur" distincts en une seule ligne de texte.
BLOCK_BREAK_RE = re.compile(r"(?i)<(?:br\s*/?|/p|/div|/li|/h[1-6])>")
LINE_SPACE_RE = re.compile(r"[ \t]+")

# Un "Label :" générique (mots commençant par une majuscule suivis de ':') sert de
# limite pour ne pas capturer la valeur d'un champ jusque dans le champ suivant,
# quand les deux sont sur la même ligne (ex: "Lieu : Douala Contrat : CDI").
GENERIC_LABEL_BOUNDARY_RE = re.compile(
    r"[A-ZÀ-Ý][\w'\-]*(?:\s*/\s*[A-Za-zÀ-ÿ][\w'\-]*|\s+[A-Za-zÀ-ÿ][\w'\-]*){0,4}\s*:"
)

LOCATION_LABELS = (
    r"lieu de travail", r"lieu de fonction", r"location\s*/\s*lieu", r"duty station",
    r"workplace", r"localisation", r"lieu d'affectation", r"deployment area",
    r"zone de d[ée]ploiement", r"poste bas[ée] [àa]", r"based in", r"lieu",
)
EXPERIENCE_LABELS = (
    r"exp[ée]rience professionnelle", r"exp[ée]rience requise", r"exp[ée]rience exig[ée]e",
    r"exp[ée]rience minimum", r"minimum d'exp[ée]rience", r"years? of experience",
    r"exp[ée]rience",
)
SALARY_LABELS = (
    r"salaire", r"r[ée]mun[ée]ration", r"salary", r"package salarial",
)
WORK_MODE_KEYWORDS = (
    ("Télétravail", (r"t[ée]l[ée]travail", r"work[-\s]from[-\s]home", r"\bremote\b")),
    ("Hybride", (r"\bhybrid",)),
    ("Présentiel", (r"pr[ée]sentiel", r"on[-\s]?site")),
)

# Villes camerounaises usuelles associées à leur région administrative, utilisées
# pour dériver `region`/`ville` à partir du texte libre du champ `location`. Liste
# non exhaustive (chefs-lieux + villes secondaires les plus fréquentes dans les
# annonces), les petites localités non répertoriées ne seront pas résolues.
CITY_REGIONS = {
    "yaounde": ("Yaoundé", "Centre"),
    "mbalmayo": ("Mbalmayo", "Centre"),
    "obala": ("Obala", "Centre"),
    "monatele": ("Monatélé", "Centre"),
    "eseka": ("Eséka", "Centre"),
    "bafia": ("Bafia", "Centre"),
    "mfou": ("Mfou", "Centre"),
    "akonolinga": ("Akonolinga", "Centre"),
    "douala": ("Douala", "Littoral"),
    "nkongsamba": ("Nkongsamba", "Littoral"),
    "edea": ("Edéa", "Littoral"),
    "loum": ("Loum", "Littoral"),
    "manjo": ("Manjo", "Littoral"),
    "garoua": ("Garoua", "Nord"),
    "guider": ("Guider", "Nord"),
    "poli": ("Poli", "Nord"),
    "tchollire": ("Tchollire", "Nord"),
    "maroua": ("Maroua", "Extrême-Nord"),
    "kousseri": ("Kousséri", "Extrême-Nord"),
    "mokolo": ("Mokolo", "Extrême-Nord"),
    "yagoua": ("Yagoua", "Extrême-Nord"),
    "kaele": ("Kaélé", "Extrême-Nord"),
    "ngaoundere": ("Ngaoundéré", "Adamaoua"),
    "meiganga": ("Meiganga", "Adamaoua"),
    "tibati": ("Tibati", "Adamaoua"),
    "tignere": ("Tignère", "Adamaoua"),
    "bertoua": ("Bertoua", "Est"),
    "abong-mbang": ("Abong-Mbang", "Est"),
    "batouri": ("Batouri", "Est"),
    "yokadouma": ("Yokadouma", "Est"),
    "bamenda": ("Bamenda", "Nord-Ouest"),
    "kumbo": ("Kumbo", "Nord-Ouest"),
    "wum": ("Wum", "Nord-Ouest"),
    "ndop": ("Ndop", "Nord-Ouest"),
    "bafoussam": ("Bafoussam", "Ouest"),
    "dschang": ("Dschang", "Ouest"),
    "foumban": ("Foumban", "Ouest"),
    "mbouda": ("Mbouda", "Ouest"),
    "bangangte": ("Bangangté", "Ouest"),
    "ebolowa": ("Ebolowa", "Sud"),
    "kribi": ("Kribi", "Sud"),
    "sangmelima": ("Sangmélima", "Sud"),
    "ambam": ("Ambam", "Sud"),
    "campo": ("Campo", "Sud"),
    "buea": ("Buea", "Sud-Ouest"),
    "limbe": ("Limbe", "Sud-Ouest"),
    "kumba": ("Kumba", "Sud-Ouest"),
    "mamfe": ("Mamfe", "Sud-Ouest"),
    "tiko": ("Tiko", "Sud-Ouest"),
    "muyuka": ("Muyuka", "Sud-Ouest"),
}
# Ordre de recherche : les noms les plus longs d'abord pour qu'un composé
# ("abong-mbang") ne soit pas court-circuité par un sous-mot.
_CITY_KEYS_BY_LENGTH = sorted(CITY_REGIONS, key=len, reverse=True)

DEADLINE_LABELS = (
    r"date limite de candidature", r"date limite de d[ée]p[ôo]t(?: des dossiers)?",
    r"date limite", r"deadline", r"postuler avant", r"cl[ôo]ture des candidatures",
    r"d[ée]lai de candidature", r"d[ée]lai", r"apply before", r"application deadline",
    r"date de fin de publication",
)

FRENCH_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10,
    "novembre": 11, "décembre": 12, "decembre": 12,
}
ENGLISH_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")
FRENCH_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+(" + "|".join(FRENCH_MONTHS) + r")\s+(\d{4})\b", re.I
)
ENGLISH_DATE_RE = re.compile(
    r"\b(" + "|".join(ENGLISH_MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})\b", re.I
)

# Liens présents dans quasi tous les articles/annonces (réseaux sociaux, navigation
# interne, images) qui ne mènent jamais vers un formulaire/contact de candidature.
COMMON_NON_APPLY_DOMAINS = (
    "blogger.googleusercontent.com",
    "t.me",
    "wa.me",
    "whatsapp.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "linkedin.com/sharing",
    "pinterest.com",
    "chariow.ly",
)


def strip_html(text):
    # Le contenu des balises style/script doit être supprimé avant les balises
    # elles-mêmes. Sinon le CSS (couleurs ``#...`` et déclarations séparées par
    # des ``;``) devient du texte visible dans les résumés publiés.
    text = HTML_COMMENT_RE.sub(" ", text)
    text = SCRIPT_STYLE_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = SPACE_RE.sub(" ", text).strip()
    text = SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    return text


def normalize_lines(content_html):
    content_html = HTML_COMMENT_RE.sub(" ", content_html)
    content_html = SCRIPT_STYLE_RE.sub(" ", content_html)
    text = BLOCK_BREAK_RE.sub("\n", content_html)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    lines = [LINE_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def extract_labeled_field(text, label_patterns):
    label_alt = "(?:" + "|".join(label_patterns) + ")"
    match = re.search(label_alt + r"\s*:\s*", text, re.I)
    if not match:
        return ""

    rest = text[match.end():match.end() + 220]
    cut = len(rest)
    newline_pos = rest.find("\n")
    if newline_pos != -1:
        cut = min(cut, newline_pos)
    boundary = GENERIC_LABEL_BOUNDARY_RE.search(rest)
    if boundary:
        cut = min(cut, boundary.start())
    cut = min(cut, 100)

    return rest[:cut].strip(" -\t,;.")


def extract_work_mode(text):
    for label, patterns in WORK_MODE_KEYWORDS:
        if any(re.search(p, text, re.I) for p in patterns):
            return label
    return ""


def strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def extract_region_ville(location_text):
    normalized = strip_accents(location_text).lower()
    for city_key in _CITY_KEYS_BY_LENGTH:
        if re.search(r"\b" + re.escape(city_key) + r"\b", normalized):
            ville, region = CITY_REGIONS[city_key]
            return region, ville
    return "", ""


def extract_region_ville_unique(text):
    """Comme extract_region_ville, mais ne renvoie un résultat que si une seule
    ville distincte est mentionnée dans tout le texte : utile pour scanner un
    corps de texte entier (sans label explicite) sans deviner à tort parmi
    plusieurs villes citées (ex: liste de zones de déploiement)."""
    normalized = strip_accents(text).lower()
    matches = set()
    for city_key in _CITY_KEYS_BY_LENGTH:
        if re.search(r"\b" + re.escape(city_key) + r"\b", normalized):
            matches.add(CITY_REGIONS[city_key])
    if len(matches) == 1:
        ville, region = next(iter(matches))
        return region, ville
    return "", ""


def parse_any_date(text):
    """Convention DD/MM/YYYY pour les dates numériques (usage local au Cameroun)."""
    match = NUMERIC_DATE_RE.search(text)
    if match:
        day, month, year = (int(g) for g in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            pass

    match = FRENCH_DATE_RE.search(text)
    if match:
        day, month_name, year = match.groups()
        month = FRENCH_MONTHS[month_name.lower()]
        try:
            return date(int(year), month, int(day))
        except ValueError:
            pass

    match = ENGLISH_DATE_RE.search(text)
    if match:
        month_name, day, year = match.groups()
        month = ENGLISH_MONTHS[month_name.lower()]
        try:
            return date(int(year), month, int(day))
        except ValueError:
            pass

    return None


def extract_deadline(text):
    label_alt = "(?:" + "|".join(DEADLINE_LABELS) + ")"
    match = re.search(label_alt, text, re.I)
    if not match:
        return None

    after_label = text[match.end():match.end() + 40]
    colon_idx = after_label.find(":")
    start = match.end() + (colon_idx + 1 if colon_idx != -1 else 0)
    return parse_any_date(text[start:start + 60])


def is_expired(deadline):
    return deadline is not None and deadline < datetime.now(CAMEROON_TZ).date()


def extract_apply_links(content_html, extra_non_apply_domains=()):
    non_apply_domains = COMMON_NON_APPLY_DOMAINS + tuple(extra_non_apply_domains)
    links = [html.unescape(h) for h in HREF_RE.findall(content_html)]

    emails = []
    urls = []
    for link in links:
        if link.startswith("mailto:"):
            email = link[len("mailto:"):].split("?")[0]
            mailto = f"mailto:{email}"
            if mailto not in emails:
                emails.append(mailto)
        elif link.startswith("http") and not any(d in link for d in non_apply_domains):
            if link not in urls:
                urls.append(link)

    return emails, urls


def make_row(title, published, deadline=None, location="", region="", ville="",
             experience="", salary="", work_mode="", apply_email="", apply_url="",
             summary="", source=""):
    return {
        "title": title,
        "published": published,
        "deadline": deadline.isoformat() if deadline else "",
        "location": location,
        "region": region,
        "ville": ville,
        "experience": experience,
        "salary": salary,
        "work_mode": work_mode,
        "apply_email": apply_email,
        "apply_url": apply_url,
        "summary": summary,
        "source": source,
    }
