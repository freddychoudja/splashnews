# Scraper d'offres d'emploi Cameroun

Récupère les offres d'emploi, bourses et concours récents concernant le Cameroun depuis plusieurs sources, et les exporte en CSV. Deux scrapers indépendants, sur le même modèle :

- [scraper.py](scraper.py) → offres d'emploi (`offres_emploi_cameroun.csv`)
- [scraper_opportunites.py](scraper_opportunites.py) → bourses et concours (`opportunites_cameroun.csv`)

Chaque source est un module dans [sources/](sources/) qui expose une fonction `scrape(since_days, max_pages, include_expired)`. Pour ajouter un site, créer un nouveau module sur ce modèle et l'enregistrer dans le dict `SOURCES` du scraper concerné.

## Emplois

Sources :
- [CameroonDesks](https://www.cameroondesks.com/search/label/jobs) (`cameroondesks`) : blog Blogger, offres au format texte libre.
- [JobinCamer](https://www.jobincamer.com/adverts/jobs) (`jobincamer`) : portail d'offres Drupal, données structurées (localisation, expérience, secteur...).
- [JobCameroun](https://job-cameroun.com/offres) (`jobcameroun`) : chaque offre embarque un bloc JSON-LD `schema.org/JobPosting` structuré (titre, dates, localisation).
- [ReliefWeb Jobs](https://reliefweb.int/jobs) (`reliefweb`) : API publique de l'ONU (OCHA), filtrée sur le Cameroun ; elle apporte surtout des postes d'ONG et d'organisations internationales.

### Fonctionnement

- **cameroondesks** : interroge le flux JSON public de Blogger (`/feeds/posts/default/-/jobs`) plutôt que de parser le HTML de la page, ce qui le rend robuste aux changements de mise en page. Ce flux renvoie déjà le contenu complet de chaque article, donc aucune requête supplémentaire n'est nécessaire.
- **jobincamer** : récupère la liste des offres sur `/adverts/jobs` (titre, lieu, date de publication), puis visite chaque page d'offre pour en extraire les champs structurés (`Localisation`, `Experience requise`...) et le contact de candidature.
- **jobcameroun** : récupère la liste des offres sur `/offres`, puis visite chaque page d'offre pour en extraire le bloc JSON-LD structuré et le contact de candidature (email, lien externe ou WhatsApp).
- **reliefweb** : interroge directement l'API officielle avec le filtre pays `CMR`. Les villes, dates, exigences d'expérience et modalités de candidature sont fournies sous forme structurée.

Par défaut, seules les offres **encore valides** (date limite de candidature non dépassée, ou inconnue) sont incluses — voir `--include-expired` ci-dessous.

Pour chaque offre, le CSV contient :
- `title` : titre de l'offre
- `published` : date de publication (ISO 8601)
- `deadline` : date limite de candidature (ISO 8601), vide si non trouvée
- `source` : `cameroondesks`, `jobincamer` ou `jobcameroun`
- `location` : lieu du poste tel que rédigé dans l'annonce (texte libre)
- `region` : région administrative du Cameroun déduite de `location` (Centre, Littoral, Ouest...)
- `ville` : ville déduite de `location`, normalisée (ex : "Yaounde"/"Yaoundé" → `Yaoundé`)
- `experience` : expérience requise
- `salary` : salaire/rémunération (rarement indiqué dans ces annonces)
- `work_mode` : mode de travail détecté — `Télétravail`, `Hybride` ou `Présentiel`
- `apply_email` : email(s) de candidature (liens `mailto:`)
- `apply_url` : lien(s) externe(s) de candidature (formulaire, ATS...), en excluant les liens décoratifs (réseaux sociaux, pub, navigation interne)
- `summary` : extrait du contenu (300 caractères)

Sur JobinCamer, `location` et `experience` viennent de champs structurés du site (fiables). Sur JobCameroun, `location` et `deadline` viennent du bloc JSON-LD structuré (fiables), mais `experience` reste extraite par heuristique depuis le texte de l'annonce. ReliefWeb fournit également des données structurées. Sur CameroonDesks, les champs sont extraits par heuristique depuis du texte libre — voir Limites connues.

## Bourses et concours

Sources :
- [CameroonDesks](https://www.cameroondesks.com/) (`cameroondesks`) : mêmes flux Blogger que pour les emplois, mais labels `bourses` et `concours`.
- [InfosPratiques.cm](https://infospratiques.cm/) (`infospratiques`) : API REST WordPress (`/wp-json/wp/v2/posts`), catégorie « Concours & Résultats » — données JSON structurées, pas de parsing HTML.

### Fonctionnement

- **cameroondesks** : interroge séparément les flux JSON des labels `bourses` et `concours`, puis déduplique par id (un post peut porter les deux labels). Chaque post est tagué avec sa `category` (`bourse` ou `concours`).
- **infospratiques** : pagine sur l'API REST WordPress filtrée par catégorie, en s'arrêtant dès qu'un post est plus vieux que la fenêtre `--days` (l'API renvoie les posts triés par date décroissante).

Le CSV contient les mêmes champs que celui des emplois, à l'exception de `experience`, `salary` et `work_mode` (non pertinents ici), et avec un champ `category` en plus (`bourse` ou `concours`).

**Hors périmètre** : hackathons et événements. Aucune source structurée et régulièrement mise à jour n'a été trouvée pour le Cameroun (ni CameroonDesks, ni [hackathon.com](https://www.hackathon.com/country/cameroon) n'ont d'entrées) — ces annonces sont dispersées sur des pages Facebook ou formulaires ponctuels d'organisateurs, sans format stable à scraper. LinkedIn n'est pas non plus une source possible : le scraping y est bloqué techniquement (mur de connexion, anti-bot) et interdit par ses conditions d'utilisation.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Utilisation

```bash
python3 scraper.py --days 30 --output offres_emploi_cameroun.csv
python3 scraper_opportunites.py --days 30 --output opportunites_cameroun.csv
```

### Publication vers KamerJob

Copier le fichier d'exemple, puis renseigner les identifiants administrateur dans
le fichier local ignoré par Git :

```bash
cp .env.kamerjob.example .env.kamerjob
```

Toujours commencer par une simulation. Elle contrôle les doublons déjà
présents sur KamerJob, les champs obligatoires et les canaux de candidature :

```bash
python3 publish_kamerjob.py
```

La déduplication croise le titre normalisé et une identité composée de
l'entreprise, du poste, de la ville, de la date limite et de l'URL/email de
candidature. Elle reconnaît les variations de casse, d'accents et certains noms
d'entreprise abrégés, tout en conservant deux offres lorsque des champs connus
se contredisent ou que les postes sont différents.

Par défaut, les lignes `cameroondesks`, `jobincamer`, `jobcameroun` et `reliefweb` sont
publiées. Une autre sélection peut être demandée explicitement avec une ou
plusieurs options `--source` répétées.

Après lecture du rapport, effectuer l'envoi explicite :

```bash
python3 publish_kamerjob.py --send
```

Avec `--send`, le script enchaîne aussi l'étape modérateur : chaque annonce
créée et encore `pending_review` passe au statut `published` uniquement si un
vrai email ou une vraie URL de candidature est présent. Sans ces informations,
l'annonce reste en modération. La reprise se base sur les identifiants du journal
local et ne modifie donc pas les annonces créées par d'autres utilisateurs.

`--limit N` limite le nombre de nouvelles offres traitées. Les champs absents
du CSV sont déduits prudemment ; les valeurs de repli sont le secteur
`Conseil et services aux entreprises` (21) et le contrat `Temps plein` (10),
modifiables avec `--default-sector` et `--default-job-type`. Quand l'entreprise
ne peut pas être déduite du titre, la valeur `Entreprise non précisée` est
utilisée. Une offre sans URL ni email peut être créée, mais elle n'est pas
approuvée automatiquement et reste dans la file de modération.

### Synchronisation quotidienne en une commande

La commande suivante scrape CameroonDesks, JobinCamer, JobCameroun et ReliefWeb,
remplace le CSV par les offres récentes, puis publie uniquement celles qui ne
sont pas encore sur KamerJob :

```bash
python3 sync_kamerjob.py
```

Pour tester tout le cycle sans créer d'annonce :

```bash
python3 sync_kamerjob.py --dry-run
```

La fenêtre par défaut est de 30 jours. Elle peut être modifiée avec
`--days`, par exemple `python3 sync_kamerjob.py --days 7`.

### Exécution automatique avec GitHub Actions

Le workflow `.github/workflows/kamerjob-daily.yml` lance la synchronisation
tous les jours à 12:00, heure du Cameroun, et peut aussi être déclenché
manuellement depuis l'onglet **Actions** de GitHub.

Dans **Settings > Secrets and variables > Actions**, créer ces deux secrets :

- `KAMERJOB_EMAIL`
- `KAMERJOB_PASSWORD`

Les identifiants sont lus directement depuis les secrets du runner et ne sont
jamais écrits dans le dépôt. Le workflow exécute les tests avant chaque
synchronisation et s'arrête si un secret manque.

Pour recevoir le rapport de synchronisation par email, ajouter également les
secrets suivants :

- `SMTP_HOST` : serveur SMTP, par exemple `smtp.gmail.com` ;
- `SMTP_PORT` : `587` pour STARTTLS ou `465` pour SSL ;
- `SMTP_USER` et `SMTP_PASSWORD` : identifiants SMTP (mot de passe
  d'application pour Gmail) ;
- `SMTP_FROM` : adresse d'expédition, facultative si identique à `SMTP_USER` ;
- `REPORT_EMAIL_TO` : destinataire, facultatif ; `KAMERJOB_EMAIL` est utilisé
  par défaut.

Un rapport est envoyé après chaque synchronisation, y compris lorsqu'aucune
offre n'est extraite ou que la publication échoue. Une configuration SMTP
absente n'empêche pas la synchronisation de fonctionner.

Options (identiques pour les deux scripts) :
- `--source` : `all` (défaut) ou le nom d'une source précise — limite le scraping à une seule source
  - `scraper.py` : `cameroondesks`, `jobincamer`, `jobcameroun`, `reliefweb`
  - `scraper_opportunites.py` : `cameroondesks`, `infospratiques`
- `--days` : n'inclure que les annonces publiées durant les N derniers jours (défaut : 30)
- `--max-pages` : nombre maximum de pages à parcourir par source (défaut : 20, ignoré par jobincamer qui n'a qu'une page de listing)
- `--include-expired` : inclure aussi les annonces dont la date limite est dépassée (exclues par défaut)
- `--output` : chemin du fichier CSV de sortie (défaut : `offres_emploi_cameroun.csv` / `opportunites_cameroun.csv`)

## Limites connues

- Sur CameroonDesks, certains articles "récap" (qui listent plusieurs offres en un seul post) n'ont pas de contact de candidature unique extrait automatiquement.
- Si une offre ne contient ni `mailto:` ni lien externe reconnu, `apply_email` et `apply_url` restent vides — c'est systématiquement le cas sur InfosPratiques, dont les articles ne font que citer en texte libre le nom du portail officiel de candidature, sans lien direct.
- Sur CameroonDesks, `location`, `experience`, `salary` et `work_mode` sont extraits par heuristique depuis du texte libre (pas de structure fixe d'un article à l'autre) : ils peuvent rester vides même quand l'information existe dans l'article, notamment `salary` qui n'est presque jamais précisé.
- Sur JobinCamer, `salary` et `work_mode` restent des heuristiques (le site n'a pas de champ dédié) ; `location` et `experience` en revanche sont fiables (champs structurés du site).
- Sur JobCameroun, `salary`, `work_mode` et `experience` restent des heuristiques (extraits du texte de l'annonce) ; `location` et `deadline` en revanche sont fiables (bloc JSON-LD structuré).
- `deadline` est fiable sur JobinCamer et JobCameroun (champs structurés). Sur CameroonDesks et InfosPratiques, elle est extraite par heuristique depuis du texte libre (formats de date variés, en français ou en anglais) : si aucune date n'est détectée, l'annonce est considérée valide par défaut plutôt qu'exclue à tort.
- `region`/`ville` reposent sur une liste de villes camerounaises usuelles (chefs-lieux + villes secondaires fréquentes) : les petites localités absentes de cette liste ne seront pas résolues et laisseront ces deux champs vides. Quand `location` est vide, le texte complet de l'annonce est scanné, mais uniquement si une seule ville y est mentionnée (sinon, trop ambigu, les champs restent vides plutôt que de deviner à tort).
