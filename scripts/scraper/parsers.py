"""Parser-Funktionen pro Bildungsplan-content_type.

Jede Funktion nimmt ein BeautifulSoup-Objekt der geparsten Seite und die Quell-URL
und gibt ein Dict im JSONL-Format zurueck.
Wirft ScraperParseError wenn die erwartete Seitenstruktur nicht gefunden wird.
"""

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup
except ImportError:
    # Der PDF-Import (scripts/pdf_import/) nutzt aus diesem Modul nur die bs4-freien Helfer
    # (_content_hash, _now_iso, extract_bp_version, expand_operator_title) und läuft auch in
    # Umgebungen ohne bs4 (z. B. dem Backend-Container). Die HTML-Parse-Funktionen brauchen
    # BeautifulSoup; sie werden dort nicht aufgerufen.
    BeautifulSoup = None  # type: ignore

from scripts.scraper.references import classify_reference, strip_soft_hyphens

_GRADE_FROM_BPID = re.compile(r'_(?:IK|PK)_(\d+)(?:-(\d+))?(?:-(\d+))?(?:-[A-Za-z]+)?_')
_NIVEAU_FROM_BPID = re.compile(r'_(?:IK|PK)_\d+(?:-\d+)*-(BF|LF)_')
_VERSION_YEAR = re.compile(r'^BP(\d{4})')
_VERSION_EDITION = re.compile(r'\.(V\d+)$')

# Boilerplate-Strings in der Inhaltsspalte (case-insensitive exact match).
# Gilt für alle Inhalts-Parser (Leitidee, PK-Gruppe, Fachplan).
# Erweiterbar wenn bildungsplaene-bw.de das Layout ändert.
_CONTENT_BOILERPLATE = frozenset([
    "download als pdf",
    "hinweis",        # alleinstehendes Service-Label — nicht der Knotentitel selbst
    "umsetzungshilfen",
])


def extract_grades_from_bp_id(bp_id: str) -> tuple[int | None, int | None]:
    """Extrahiert (min_grade, max_grade) aus bp_id, z.B. 'BP...CH_IK_7-8_01' -> (7, 8)."""
    m = _GRADE_FROM_BPID.search(bp_id)
    if not m:
        return None, None
    grades = [int(g) for g in m.groups() if g is not None]
    if not grades:
        return None, None
    return min(grades), max(grades)


# Kursstufen-Basisfächer (z. B. NWTBFO) nummerieren IK/PK mit zero-padded
# Kompetenzbereichs-Nummern (…_IK_03_02_01, …_PK_02) statt Jahrgangsbändern. Ein solches
# "03" darf NICHT als Klassenstufe 3 gelesen werden — Sek-I-Bänder sind nie zero-padded
# (…_IK_5-6_01, …_IK_8-9-10_02_01).
_KOMPETENZBEREICH_NR = re.compile(r'_(?:IK|PK)_0\d')


def _plausibles_url_band(bp_id: str, url_min: int, url_max: int) -> bool:
    """True, wenn das aus der bp_id gelesene Band echte Klassenstufen sind (5–13) und
    keine (zero-padded) Kursstufen-Kompetenzbereichs-Nummer."""
    if _KOMPETENZBEREICH_NR.search(bp_id):
        return False
    return 5 <= url_min and url_max <= 13


def resolve_grade_band(
    bp_id: str,
    url_min: int | None,
    url_max: int | None,
    cfg_min: int | None,
    cfg_max: int | None,
) -> tuple[int | None, int | None]:
    """Bestimmt das Jahrgangsband eines Knotens (Todo B1).

    - Kein URL-Band (Fachplan) → unverändert (bleibt None).
    - Plausibles URL-Band (echte Stufen 5–13, nicht zero-padded) → behalten. So bleibt der
      legitime Sek-I-Hinweisknoten …_IK_5-6_01 erhalten.
    - Sonst (Kursstufen-Kompetenzbereich, z. B. NWTBFO …_IK_03_…, → fälschlich (3,3)) →
      das Fach-Band aus der Config (subjects.yaml min_grade/max_grade) setzen.
    """
    if url_min is None:
        return url_min, url_max
    if _plausibles_url_band(bp_id, url_min, url_max):
        return url_min, url_max
    return cfg_min, cfg_max


def extract_niveau_from_bp_id(bp_id: str) -> str:
    """'…11-12-BF_…' → 'basis', '…11-12-LF_…' → 'leistung', sonst 'regulär'."""
    m = _NIVEAU_FROM_BPID.search(bp_id)
    if not m:
        return "regulär"
    return {"BF": "basis", "LF": "leistung"}[m.group(1)]


def extract_bp_version(bp_id: str) -> str:
    """Leitet die BP-Versions-Kennung aus bp_id ab.

    'BP2016BW_ALLG_GYM_M.V2_IK_…' → '2016.V2'
    'BP2016BW_ALLG_GYM_M_IK_…'    → '2016'
    """
    year_m = _VERSION_YEAR.match(bp_id)
    year = year_m.group(1) if year_m else ""
    for part in bp_id.split("_"):
        ed_m = _VERSION_EDITION.search(part)
        if ed_m:
            return year + "." + ed_m.group(1)
    return year


class ScraperParseError(Exception):
    """Wird geworfen wenn ein Parser auf einer Seite die erwartete Struktur nicht findet."""
    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"Parse-Fehler bei {url}: {reason}")


def _extract_bp_id_from_url(url: str) -> str:
    """Extrahiert die BP-ID aus dem URL-Pfad.

    Beispiel: '.../,Lde/BP2016BW_ALLG_GYM_CH_IK_7-8_01' -> 'BP2016BW_ALLG_GYM_CH_IK_7-8_01'
    """
    path = urlparse(url).path
    parts = path.rstrip('/').split('/')
    for part in reversed(parts):
        if part.startswith('BP'):
            return part
    raise ScraperParseError(url, "Keine BP-ID in der URL gefunden")


def _extract_breadcrumb(soup: BeautifulSoup, url: str) -> list[str]:
    """Extrahiert den Breadcrumb-Pfad aus dem nav.breadcrumb__nav-Element."""
    nav = soup.select_one('.breadcrumb__nav') or soup.find('nav')
    if not nav:
        return []
    crumbs = []
    for li in nav.find_all('li'):
        a = li.find('a')
        if a:
            text = strip_soft_hyphens(a.get_text(separator=" ", strip=True))
        else:
            text = strip_soft_hyphens(li.get_text(separator=" ", strip=True))
        if text:
            crumbs.append(text)
    return crumbs


_JS_TEMPLATE = re.compile(r'\$\{|\$\w+\.\w+')


def _is_template_literal(text: str) -> bool:
    """Gibt True zurück wenn der Text ein ungerendertes JS-Template-Binding ist."""
    return bool(_JS_TEMPLATE.search(text))


def _find_title(soup: BeautifulSoup) -> str | None:
    """Findet den Seitentitel robust über mehrere Quellen.

    Reihenfolge:
    1. *alle* h1/h2 mit Klasse ``headline--2`` (nicht nur das erste) — überspringt
       ungerenderte JS-Template-Bindings wie ``$headline.text`` (neuere M.V2-Seiten)
       und nimmt die erste echte Überschrift.
    2. das ``og:title``-Meta-Tag — serverseitig gerendert, enthält nie ein JS-Binding.
       Steht VOR dem generischen ``<h2>``-Fallback, weil auf Seiten mit nur einem
       ``headline--2``-Platzhalter (M.V2-PK-Seiten) sonst eine ``headline--4``-
       Zwischenüberschrift fälschlich als Titel genommen würde.
    3. das erste echte ``<h2>`` (LP-/Standards-Seiten ohne ``headline--2``/``og:title``).

    Gibt None zurück, wenn nur Template-Bindings/Leeres gefunden wurden, damit
    Aufrufer zusätzlich auf den Breadcrumb-Fallback zurückfallen können.
    """
    def _clean(el) -> str:
        return strip_soft_hyphens(el.get_text(separator=" ", strip=True))

    # 1. Alle headline--2-Überschriften durchgehen (Platzhalter überspringen)
    for el in soup.find_all(['h1', 'h2'], class_=lambda c: c and 'headline--2' in c):
        text = _clean(el)
        if text and not _is_template_literal(text):
            return text

    # 2. og:title-Meta als verlässlicher serverseitiger Fallback
    og = soup.find('meta', attrs={'property': 'og:title'})
    if og and og.get('content'):
        text = strip_soft_hyphens(og['content'].strip())
        if text and not _is_template_literal(text):
            return text

    # 3. Erstes echtes h2 (letzter Ausweg)
    for el in soup.find_all('h2'):
        text = _clean(el)
        if text and not _is_template_literal(text):
            return text

    return None


# Klassen/Tags, die niemals Inhaltsfließtext tragen. Bewusst über semantische
# Tag-Namen (nav/header/footer) statt über Substring-Klassenmatch — letzteres
# schloss fälschlich Inhalts-Container wie ``page__header`` o. Ä. aus.
def _in_noncontent_region(el) -> bool:
    """True, wenn das Element in Navigation/Kopf/Fuß/Breadcrumb liegt."""
    if el.find_parent(['nav', 'header', 'footer']):
        return True
    if el.find_parent(class_=re.compile(r'breadcrumb', re.I)):
        return True
    return False


# Beginn des Service-/Boilerplate-Blocks am Seitenende. Ab hier wird kein
# Inhaltstext mehr gesammelt (verhindert das Einsammeln von „Die Beispiel-
# curricula …" u. Ä., die nicht in der Wort-Blocklist stehen).
_SERVICE_BOUNDARY = re.compile(
    r'^(die verlinkten unterst|umsetzungshilfen|die beispielcurricula)', re.I
)


def _collect_intro_text(soup: BeautifulSoup, title: str, *, limit: int | None = None) -> str:
    """Sammelt den beschreibenden Einleitungstext einer Bildungsplan-Seite.

    Strukturunabhängig: ab der Titelüberschrift (h1/h2.headline--2 mit Text == title)
    werden in Dokumentreihenfolge alle <p>/<h3> gesammelt, bis der Service-Block
    beginnt (_SERVICE_BOUNDARY). Wird die Titelüberschrift nicht gefunden (z. B. Titel
    stammt aus og:title/Breadcrumb, weil das headline--2 ein JS-Platzhalter ist), wird
    der gesamte <main> gescannt — die headline--2-Überschrift selbst ist kein <p>/<h3>
    und fällt damit ohnehin heraus.

    Bewusst NICHT an Grid-Spalten (.grid__col--1/2) gebunden — das Layout variiert
    (grid--75-25 vs. grid--25-50-25) und der Inhalt liegt mal in col1, mal in col2.
    Bewusst KEIN Substring-Klassenmatch (schloss Container wie „itk_header" fälschlich
    aus); Navigation/Kopf/Fuß nur über semantische Tags (_in_noncontent_region).

    limit: optionale Obergrenze für die Anzahl gesammelter Absätze (Fachplan-Kurztext).
    """
    main = soup.find('main') or soup
    title_el = None
    for el in main.find_all(['h1', 'h2'], class_=lambda c: c and 'headline--2' in c):
        if strip_soft_hyphens(el.get_text(separator=" ", strip=True)) == title:
            title_el = el
            break

    candidates = title_el.find_all_next(['p', 'h3']) if title_el else main.find_all(['p', 'h3'])

    parts: list[str] = []
    for elem in candidates:
        if elem.find_parent('table'):
            continue
        if _in_noncontent_region(elem):
            continue
        text = strip_soft_hyphens(elem.get_text(separator=" ", strip=True))
        if not text:
            continue
        low = text.lower()
        if _SERVICE_BOUNDARY.match(low):
            break  # Service-Block erreicht — Rest ist Boilerplate
        if low in _CONTENT_BOILERPLATE:
            continue
        if text == title:
            continue
        parts.append(text)
        if limit is not None and len(parts) >= limit:
            break

    return '\n'.join(parts)


def _content_hash(text: str) -> str:
    return 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_fachplan(soup: BeautifulSoup, url: str) -> dict[str, Any]:
    """Parst die Fach-Uebersichtsseite (content_type='fachplan')."""
    bp_id = _extract_bp_id_from_url(url)
    breadcrumb = _extract_breadcrumb(soup, url)

    title = _find_title(soup)
    if not title:
        raise ScraperParseError(url, "Kein Titel (h1.headline--2 / h2) auf Fachplan-Seite")

    # Kurzbeschreibung strukturunabhängig erfassen (max. 3 Absätze, siehe
    # _collect_intro_text). Reine Navigationsseiten (kein Fließtext) → content = title.
    content = _collect_intro_text(soup, title, limit=3) or title

    min_grade, max_grade = extract_grades_from_bp_id(bp_id)

    return {
        'bp_id': bp_id,
        'type': 'knowledge',
        'content_type': 'fachplan',
        'title': title,
        'content': content,
        'content_hash': _content_hash(content),
        'parent_bp_id': None,
        'relations': [],
        'min_grade': min_grade,
        'max_grade': max_grade,
        'niveau': 'regulär',
        'bp_version': extract_bp_version(bp_id),
        'metadata': {
            'bp_id': bp_id,
            'breadcrumb': breadcrumb,
            'source_url': url,
            'scraped_at': _now_iso(),
        },
        'visibility': 'global',
    }


def _ik_parent_bp_id(bp_id: str) -> str:
    """Bestimmt die parent_bp_id fuer einen IK-Knoten.

    IK_{JG}_{LI}        -> Fachplan (alles vor _IK_)
    IK_{JG}_{LI}_{NR}   -> Leitidee (letztes Segment abschneiden)
    """
    ik_suffix = re.sub(r'^.*_IK_', '', bp_id)
    segments = ik_suffix.split('_')
    if len(segments) >= 3:
        # 3-segment: IK_{JG}_{LI}_{NR} -> parent is IK_{JG}_{LI}
        return bp_id.rsplit('_', 1)[0]
    else:
        # 2-segment: IK_{JG}_{LI} -> parent is fachplan
        return re.sub(r'_IK_.*$', '', bp_id)


def parse_leitidee(soup: BeautifulSoup, url: str) -> dict[str, Any]:
    """Parst eine IK-Seite als Leitidee-Knoten (content_type='leitidee').

    Gilt fuer beide Seitentypen:
    - IK_{JG}_{LI}     : Leitidee-Uebersichtsseite (Navigationsseite)
    - IK_{JG}_{LI}_{NR}: Einzelne Kompetenzbereichsseite (hat tktable)
    """
    bp_id = _extract_bp_id_from_url(url)
    breadcrumb = _extract_breadcrumb(soup, url)

    title = _find_title(soup) or (breadcrumb[-1] if breadcrumb else None)
    if not title:
        raise ScraperParseError(url, "Kein Titel auf Leitidee-Seite")

    # Einleitungstext strukturunabhängig erfassen (siehe _collect_intro_text).
    # Kinderlose/reine Navigationsseiten liefern hier content = "".
    content = _collect_intro_text(soup, title)

    parent_bp_id = _ik_parent_bp_id(bp_id)
    min_grade, max_grade = extract_grades_from_bp_id(bp_id)

    return {
        'bp_id': bp_id,
        'type': 'knowledge',
        'content_type': 'leitidee',
        'title': title,
        'content': content,
        'content_hash': _content_hash(content),
        'parent_bp_id': parent_bp_id,
        'relations': [],
        'min_grade': min_grade,
        'max_grade': max_grade,
        'niveau': extract_niveau_from_bp_id(bp_id),
        'bp_version': extract_bp_version(bp_id),
        'metadata': {
            'bp_id': bp_id,
            'breadcrumb': breadcrumb,
            'source_url': url,
            'scraped_at': _now_iso(),
        },
        'visibility': 'global',
    }


def parse_ik_kompetenz_list(soup: BeautifulSoup, url: str, parent_bp_id: str) -> list[dict[str, Any]]:
    """Extrahiert alle nummerierten IK-Standards aus der tktable einer IK-Seite.

    Gibt leere Liste zurueck wenn kein tktable vorhanden (keine Fehlerbehandlung noetig).
    Zeilen in der tktable wechseln sich ab: Standard-Text (1), (2), ... und Referenz-Zeile.
    """
    tktable = soup.find('table', class_=lambda c: c and 'tktable' in c)
    if not tktable:
        return []

    breadcrumb = _extract_breadcrumb(soup, url)
    nodes = []
    standard_pattern = re.compile(r'^\((\d+)\)')
    rows = tktable.find_all('tr')

    # Numerisches Präfix aus dem letzten Breadcrumb-Eintrag extrahieren
    # z.B. "3.1.1 Leitidee Zahl…" → "3.1.1"  (Fallback: bp_id-Segmente)
    _heading_nr = re.compile(r'^(\d+(?:\.\d+)*)\s')
    leitidee_prefix = None
    if breadcrumb:
        m_bc = _heading_nr.match(breadcrumb[-1])
        if m_bc:
            leitidee_prefix = m_bc.group(1)
    if not leitidee_prefix:
        ik_suffix = re.sub(r'^.*_IK_', '', parent_bp_id)
        li_nrs = [int(s) for s in ik_suffix.split('_') if s and s.isdigit()]
        leitidee_prefix = '.'.join(str(n) for n in li_nrs) if li_nrs else None

    min_grade, max_grade = extract_grades_from_bp_id(parent_bp_id)

    for i, row in enumerate(rows):
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue

        first_text = strip_soft_hyphens(cells[0].get_text(separator=" ", strip=True))
        m = standard_pattern.match(first_text)
        if not m:
            continue

        nr = int(m.group(1))
        content = first_text
        # Kanonische bp_id der Quelle (data-bpid) bevorzugen statt selbst zu
        # synthetisieren — sonst fehlt bei mehrstufigen IK-Seiten die
        # Zwischenebene (z.B. Kursstufe-Basisfach: …_{Leitidee}_00_{Nr}), und
        # keine Querverweise lösen auf. Fallback: bisherige Synthese.
        sub_bp_id = cells[0].get("data-bpid") or f"{parent_bp_id}_{nr:02d}"

        # Naechste Zeile enthaelt Referenzen (falls vorhanden und keine neue Standard-Zeile)
        relations = []
        if i + 1 < len(rows):
            next_cells = rows[i + 1].find_all(['td', 'th'])
            if next_cells:
                ref_text = strip_soft_hyphens(next_cells[0].get_text(separator=" ", strip=True))
                if not standard_pattern.match(ref_text):
                    for token in re.split(r'[,\s]+', ref_text):
                        ref = classify_reference(token.strip())
                        if ref:
                            relations.append(ref)

        # Berechne hierarchische Kompetenz-Nummer, z.B. "3.1.1(2)"
        kompetenz_nr = f"{leitidee_prefix}({nr})" if leitidee_prefix else f"({nr})"

        # Titel: (n)-Präfix durch vollständige Kompetenznummer ersetzen
        title_text = re.sub(r'^\(\d+\)\s*', '', content).strip()
        title = f"{kompetenz_nr} {title_text}"

        nodes.append({
            'bp_id': sub_bp_id,
            'type': 'knowledge',
            'content_type': 'ik_kompetenz',
            'title': title[:200],
            'content': content,
            'content_hash': _content_hash(content),
            'parent_bp_id': parent_bp_id,
            'relations': relations,
            'min_grade': min_grade,
            'max_grade': max_grade,
            'niveau': extract_niveau_from_bp_id(parent_bp_id),
            'bp_version': extract_bp_version(parent_bp_id),
            'metadata': {
                'bp_id': sub_bp_id,
                'standard_nr': nr,
                'kompetenz_nr': kompetenz_nr,
                'breadcrumb': breadcrumb,
                'source_url': url,
                'scraped_at': _now_iso(),
            },
            'visibility': 'global',
        })

    return nodes


def parse_pk_gruppe(soup: BeautifulSoup, url: str) -> dict[str, Any]:
    """Parst eine PK-Gruppen-Seite (content_type='pk_gruppe')."""
    bp_id = _extract_bp_id_from_url(url)
    breadcrumb = _extract_breadcrumb(soup, url)

    title = _find_title(soup) or (breadcrumb[-1] if breadcrumb else None)
    if not title:
        raise ScraperParseError(url, "Kein Titel auf PK-Gruppen-Seite")

    # Einleitungstext strukturunabhängig erfassen (siehe _collect_intro_text).
    # Fängt zusätzlich das frühere Mitschleppen von Titel-Duplikat und dem
    # JS-Platzhalter ``$headline.text`` im content ab.
    content = _collect_intro_text(soup, title) or title

    parent_bp_id = re.sub(r'_PK_.*$', '', bp_id)
    min_grade, max_grade = extract_grades_from_bp_id(bp_id)

    return {
        'bp_id': bp_id,
        'type': 'knowledge',
        'content_type': 'pk_gruppe',
        'title': title,
        'content': content,
        'content_hash': _content_hash(content),
        'parent_bp_id': parent_bp_id,
        'relations': [],
        'min_grade': min_grade,
        'max_grade': max_grade,
        'niveau': extract_niveau_from_bp_id(bp_id),
        'bp_version': extract_bp_version(bp_id),
        'metadata': {
            'bp_id': bp_id,
            'breadcrumb': breadcrumb,
            'source_url': url,
            'scraped_at': _now_iso(),
        },
        'visibility': 'global',
    }


def parse_pk_kompetenz_list(soup: BeautifulSoup, url: str, parent_bp_id: str) -> list[dict[str, Any]]:
    """Extrahiert alle nummerierten PK-Sub-Standards aus der Tabelle einer PK-Gruppen-Seite.

    Standards sind mit '1.', '2.', ... nummeriert.
    Optional: thematische Zwischengruppe als metadata.thematische_gruppe.
    """
    table = soup.find('table')
    if not table:
        raise ScraperParseError(url, "Keine <table> auf PK-Gruppen-Seite gefunden")

    breadcrumb = _extract_breadcrumb(soup, url)
    nodes = []
    current_gruppe = None
    nr_pattern = re.compile(r'^(\d+)\.')

    # Numerisches Präfix aus letztem Breadcrumb-Eintrag, z.B. "2.1 Erkenntnisgewinnung" → "2.1"
    _heading_nr = re.compile(r'^(\d+(?:\.\d+)*)\s')
    pk_prefix = None
    if breadcrumb:
        m_bc = _heading_nr.match(breadcrumb[-1])
        if m_bc:
            pk_prefix = m_bc.group(1)

    min_grade, max_grade = extract_grades_from_bp_id(parent_bp_id)

    for row in table.find_all('tr'):
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue

        first_text = strip_soft_hyphens(cells[0].get_text(separator=" ", strip=True))

        # Thematische Zwischengruppe (unnummerierte Zeile, kursiv oder colspan)
        if len(cells) == 1 and not nr_pattern.match(first_text):
            current_gruppe = first_text if first_text else current_gruppe
            continue

        m = nr_pattern.match(first_text)
        if not m:
            continue

        nr = int(m.group(1))
        content = first_text
        # Kanonische bp_id der Quelle (data-bpid) bevorzugen statt selbst zu
        # synthetisieren (siehe parse_ik_kompetenz_list). Fallback: Synthese.
        sub_bp_id = cells[0].get("data-bpid") or f"{parent_bp_id}_{nr:02d}"

        # Berechne hierarchische Kompetenz-Nummer, z.B. "2.1.1"
        if pk_prefix:
            kompetenz_nr = f"{pk_prefix}.{nr}"
        elif current_gruppe:
            try:
                gruppe_nr_match = re.search(r'(\d+)', current_gruppe)
                kompetenz_nr = f"{gruppe_nr_match.group(1)}.{nr}" if gruppe_nr_match else f"{nr}"
            except (ValueError, TypeError):
                kompetenz_nr = f"{nr}"
        else:
            kompetenz_nr = f"{nr}"

        # Titel: "1. Text…" → "2.1.1 Text…"
        title_text = re.sub(r'^\d+\.\s*', '', content).strip()
        title = f"{kompetenz_nr} {title_text}"

        meta: dict[str, Any] = {
            'bp_id': sub_bp_id,
            'standard_nr': nr,
            'kompetenz_nr': kompetenz_nr,
            'breadcrumb': breadcrumb,
            'source_url': url,
            'scraped_at': _now_iso(),
        }
        if current_gruppe:
            meta['thematische_gruppe'] = current_gruppe

        nodes.append({
            'bp_id': sub_bp_id,
            'type': 'knowledge',
            'content_type': 'pk_kompetenz',
            'title': title[:200],
            'content': content,
            'content_hash': _content_hash(content),
            'parent_bp_id': parent_bp_id,
            'relations': [],
            'min_grade': min_grade,
            'max_grade': max_grade,
            'niveau': extract_niveau_from_bp_id(parent_bp_id),
            'bp_version': extract_bp_version(parent_bp_id),
            'metadata': meta,
            'visibility': 'global',
        })

    if not nodes:
        raise ScraperParseError(url, "Keine nummerierten PK-Standards (1., 2., ...) in Tabelle")
    return nodes


def parse_leitperspektive(soup: BeautifulSoup, url: str, kuerzel: str) -> dict[str, Any]:
    """Parst eine Leitperspektive-Uebersichtsseite (content_type='leitperspektive')."""
    bp_id = f"BP2016BW_ALLG_LP_{kuerzel}"
    breadcrumb = _extract_breadcrumb(soup, url)

    title = _find_title(soup)
    if not title:
        raise ScraperParseError(url, "Kein Titel auf LP-Seite")

    content_parts = []
    main = soup.find('main') or soup
    for elem in main.find_all(['p', 'h2']):
        if elem.find_parent(class_=re.compile('breadcrumb|nav|header|footer')):
            continue
        text = strip_soft_hyphens(elem.get_text(separator=" ", strip=True))
        if text:
            content_parts.append(text)
    content = '\n'.join(content_parts[:5]) if content_parts else title

    metadata = {
        'bp_id': bp_id,
        'kuerzel': kuerzel,
        'breadcrumb': breadcrumb,
        'source_url': url,
        'scraped_at': _now_iso(),
    }

    # (Früher: LFDB-Sonderfall mit import_hinweis, da die Inhalte nur als PDF vorlagen.
    #  Seit dem PDF-Import [KS-Plan C4] werden Baustein/Themenblock/Kompetenz importiert →
    #  Hinweis entfernt, Übersichtsknoten bleibt hinweisfrei.)

    return {
        'bp_id': bp_id,
        'type': 'knowledge',
        'content_type': 'leitperspektive',
        'title': title,
        'content': content,
        'content_hash': _content_hash(content),
        'parent_bp_id': None,
        'relations': [],
        'min_grade': None,
        'max_grade': None,
        'metadata': metadata,
        'visibility': 'global',
    }


def parse_leitperspektive_aspekt_list(
    soup: BeautifulSoup, url: str, kuerzel: str
) -> list[dict[str, Any]]:
    """Extrahiert alle Aspekt-Knoten aus der Konkretisierungs-Liste einer LP-Seite.

    Aspekte sind Bullet-Punkte (li-Elemente) in der LP-Seite.
    Synthetische bp_id: {KUERZEL}_{NR:02d}, z.B. BNE_01, MB_05.

    Falls keine Liste vorhanden -> leere Liste (LFDB-Sonderfall).
    """
    nodes = []
    main = soup.find('main') or soup

    def _is_content_list(candidate) -> bool:
        return not candidate.find_parent(re.compile(r'^nav$')) and \
            not candidate.find_parent(class_=re.compile(r'breadcrumb|nav|header|footer'))

    # Die Konkretisierungsliste folgt dem Einleitungssatz
    # „… durch folgende Begriffe konkretisiert:". Manche LP-Seiten (z. B. PG)
    # haben davor eine andere Liste („Zentrale Lern- und Handlungsfelder"),
    # daher zuerst nach dem Anker-Satz suchen und die erste Inhaltsliste
    # dahinter nehmen.
    ul = None
    for el in main.find_all(['p', 'h2', 'h3', 'h4']):
        if 'durch folgende Begriffe konkretisiert' in \
                strip_soft_hyphens(el.get_text(separator=" ", strip=True)):
            candidate = el.find_next(['ul', 'ol'])
            while candidate is not None and not _is_content_list(candidate):
                candidate = candidate.find_next(['ul', 'ol'])
            ul = candidate
            break

    # Fallback (z. B. LFDB ohne Anker-Satz): erste Inhaltsliste der Seite
    if ul is None:
        for candidate in main.find_all(['ul', 'ol']):
            if _is_content_list(candidate):
                ul = candidate
                break

    if not ul:
        return nodes

    parent_bp_id = f"BP2016BW_ALLG_LP_{kuerzel}"

    for idx, li in enumerate(ul.find_all('li', recursive=False), start=1):
        content = strip_soft_hyphens(li.get_text(separator=" ", strip=True))
        if not content:
            continue
        sub_bp_id = f"{kuerzel}_{idx:02d}"
        nodes.append({
            'bp_id': sub_bp_id,
            'type': 'knowledge',
            'content_type': 'leitperspektive_aspekt',
            'title': content[:200],
            'content': content,
            'content_hash': _content_hash(content),
            'parent_bp_id': parent_bp_id,
            'relations': [],
            'min_grade': None,
            'max_grade': None,
            'metadata': {
                'bp_id': sub_bp_id,
                'kuerzel': kuerzel,
                'aspekt_nr': idx,
                'source_url': url,
                'scraped_at': _now_iso(),
            },
            'visibility': 'global',
        })

    return nodes


# ── Operatoren (handlungsleitende Verben) ────────────────────────────────────

# Trennbare/untrennbare Verbpräfixe (längste zuerst) — für die Stamm-Extraktion
# beim Ergänzungsstrich ("ein-, zuordnen" → Stamm "ordnen" → "einordnen").
_VERB_PREFIXES = sorted(
    [
        'zusammen', 'zurück', 'voraus', 'wieder', 'hervor', 'heraus', 'herein',
        'hinaus', 'hinein', 'durch', 'unter', 'über', 'nach', 'fort', 'fest',
        'dar', 'weg', 'weiter', 'her', 'hin', 'los', 'ab', 'an', 'auf', 'aus',
        'be', 'bei', 'ein', 'ent', 'er', 'ge', 'mit', 'um', 'ver', 'vor', 'zer', 'zu',
    ],
    key=len, reverse=True,
)
_ERGAENZUNGSSTRICH = re.compile(r'^(\w+)-\s*[,/]\s*(\w+)\b')
_KLAMMER_PRAEFIX = re.compile(r'\((\w+)-\)(\w+)')


def _verb_stem(full: str) -> str | None:
    """Stamm eines präfigierten Verbs ('zuordnen' → 'ordnen'); None falls kein Präfix passt."""
    for p in _VERB_PREFIXES:
        if full.startswith(p) and len(full) > len(p) + 2:
            return full[len(p):]
    return None


def _split_top_level(text: str, seps: str) -> list[str]:
    """Splittet an Trennzeichen außerhalb von Klammern (...)."""
    out, buf, depth = [], '', 0
    for ch in text:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(0, depth - 1)
        if ch in seps and depth == 0:
            out.append(buf)
            buf = ''
        else:
            buf += ch
    out.append(buf)
    return [x.strip() for x in out if x.strip()]


def expand_operator_title(raw: str) -> tuple[str, list[str]]:
    """Zerlegt eine Operator-Titelzelle in (Titel, Aliase).

    Behandelt die realen Schreibweisen der BW-Operatorenlisten:
    - Ergänzungsstrich: 'ein-, zuordnen' / 'ein-/zuordnen' → 'einordnen' + ['zuordnen']
    - Klammer-Präfix:   '(be-)nennen' → 'nennen' + ['benennen']
    - Synonyme (Komma/Semikolon/einwortiger Slash): 'beurteilen, bewerten' →
      Titel 'beurteilen', Alias 'bewerten'
    - beschreibende Phrasen (' und ') und Klammer-Inhalte bleiben unzerlegt.
    """
    title = re.sub(r'\s+', ' ', strip_soft_hyphens(raw).replace('*', '')).strip()
    if not title:
        return '', []
    # Beschreibende Phrase → verbatim, keine Aliase
    if ' und ' in f' {title} ':
        return title, []
    # Klammer-Präfix: (be-)nennen → nennen + benennen
    m = _KLAMMER_PRAEFIX.fullmatch(title)
    if m:
        pre, base = m.group(1), m.group(2)
        return base, [pre + base]
    forms: list[str] = []
    rest = title
    # Ergänzungsstrich am Anfang: 'ein-, zuordnen' / 'an-/verwenden'
    m = _ERGAENZUNGSSTRICH.match(title)
    if m:
        pre, full = m.group(1), m.group(2)
        stem = _verb_stem(full)
        forms += [pre + stem, full] if stem else [full]
        rest = title[m.end():]
    # Restliche Synonyme: , ; (klammer-bewusst) + einwortige /
    for frag in _split_top_level(rest, ';,'):
        if '/' in frag and ' ' not in frag and '(' not in frag:
            forms += [f.strip() for f in frag.split('/') if f.strip()]
        else:
            forms.append(frag)
    # dedup, Reihenfolge wahren
    seen, out = set(), []
    for f in forms:
        if f and f not in seen:
            seen.add(f)
            out.append(f)
    if not out:
        return title, []
    return out[0], out[1:]


def parse_operator_list(
    soup: BeautifulSoup, url: str, parent_bp_id: str
) -> list[dict[str, Any]]:
    """Extrahiert Operator-Knoten aus der Operatoren-Anhangseite (content_type='operator').

    Quelle: eine ``<table border="1">`` mit Spalten Operator | Beschreibung | AFB.
    Synthetische bp_id: ``{op_page_bp_id}_{NR:02d}``. AFB als Liste (komma-getrennt,
    Mehrfachzuordnung möglich). Titel-Synonyme → ``metadata.aliase`` via
    ``expand_operator_title``. Keine Tabelle → leere Liste (Fach ohne Operatoren-Anhang).
    """
    op_page_bp_id = _extract_bp_id_from_url(url)
    tbl = soup.find('table', attrs={'border': '1'})
    if tbl is None:
        return []

    nodes: list[dict[str, Any]] = []
    nr = 0
    for row in tbl.find_all('tr'):
        cells = row.find_all('td')  # Header-Zeile (<th>) wird so übersprungen
        if len(cells) < 3:
            continue
        title, aliase = expand_operator_title(cells[0].get_text(separator=" ", strip=True))
        content = strip_soft_hyphens(cells[1].get_text(separator=" ", strip=True))
        afb = [s.strip() for s in
               strip_soft_hyphens(cells[2].get_text(separator=" ", strip=True)).split(',')
               if s.strip()]
        if not title or not content:
            continue
        nr += 1
        bp_id = f"{op_page_bp_id}_{nr:02d}"
        hash_input = f"{title}|{content}|{','.join(afb)}|{','.join(aliase)}"
        nodes.append({
            'bp_id': bp_id,
            'type': 'knowledge',
            'content_type': 'operator',
            'title': title,
            'content': content,
            'content_hash': _content_hash(hash_input),
            'parent_bp_id': parent_bp_id,
            'relations': [],
            'min_grade': None,
            'max_grade': None,
            'niveau': 'regulär',
            'bp_version': extract_bp_version(bp_id),
            'metadata': {
                'bp_id': bp_id,
                'afb': afb,
                'aliase': aliase,
                'operator_nr': nr,
                'source_url': url,
                'scraped_at': _now_iso(),
            },
            'visibility': 'global',
        })

    return nodes
