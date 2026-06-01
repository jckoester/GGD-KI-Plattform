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

from bs4 import BeautifulSoup

from scripts.scraper.references import classify_reference, strip_soft_hyphens

_GRADE_FROM_BPID = re.compile(r'_(?:IK|PK)_(\d+)(?:-(\d+))?(?:-[A-Za-z]+)?_')


def extract_grades_from_bp_id(bp_id: str) -> tuple[int | None, int | None]:
    """Extrahiert (min_grade, max_grade) aus bp_id, z.B. 'BP...CH_IK_7-8_01' -> (7, 8)."""  
    m = _GRADE_FROM_BPID.search(bp_id)
    if not m:
        return None, None
    grades = [int(g) for g in m.groups() if g is not None]
    if not grades:
        return None, None
    return min(grades), max(grades)


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


def _find_title(soup: BeautifulSoup) -> str | None:
    """Findet den Seitentitel: h1.headline--2 (Fachplan/Leitidee) oder h2 (LP/Standards)."""
    # Fachplan and Leitidee overview pages use h1 with class headline--2
    h1 = soup.find('h1', class_=lambda c: c and 'headline--2' in c)
    if h1:
        return strip_soft_hyphens(h1.get_text(separator=" ", strip=True))
    h2 = soup.find('h2')
    if h2:
        return strip_soft_hyphens(h2.get_text(separator=" ", strip=True))
    return None


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

    content_parts = []
    main = soup.find('main') or soup
    for elem in main.find_all(['p', 'h2'], limit=10):
        if elem.find_parent(class_=re.compile('breadcrumb|nav|header|footer')):
            continue
        text = strip_soft_hyphens(elem.get_text(separator=" ", strip=True))
        if text:
            content_parts.append(text)
            if len(content_parts) >= 3:
                break
    content = '\n'.join(content_parts) if content_parts else title

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

    title = _find_title(soup)
    if not title:
        raise ScraperParseError(url, "Kein Titel auf Leitidee-Seite")

    # Einfuehrungstext: Paragraphen ausserhalb von Tabellen und Navigation
    content_parts = []
    main = soup.find('main') or soup
    for elem in main.find_all(['p', 'h2', 'h3']):
        if elem.find_parent('table'):
            continue
        if elem.find_parent(class_=re.compile('breadcrumb|nav|header|footer')):
            continue
        text = strip_soft_hyphens(elem.get_text(separator=" ", strip=True))
        if text:
            content_parts.append(text)
    content = '\n'.join(content_parts) if content_parts else title

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

    # Extrahiere Leitideen-Nummer aus parent_bp_id für kompetenz_nr
    ik_suffix = re.sub(r'^.*_IK_', '', parent_bp_id)
    li_segments = ik_suffix.split('_')
    li_nr = None
    for seg in reversed(li_segments):
        if seg and seg.isdigit():
            li_nr = seg
            break

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
        sub_bp_id = f"{parent_bp_id}_{nr:02d}"

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

        # Berechne hierarchische Kompetenz-Nummer
        try:
            kompetenz_nr = f"{int(li_nr)}.{nr}" if li_nr else f"{nr}"
        except (ValueError, TypeError):
            kompetenz_nr = f"{nr}"

        nodes.append({
            'bp_id': sub_bp_id,
            'type': 'knowledge',
            'content_type': 'ik_kompetenz',
            'title': content[:200],
            'content': content,
            'content_hash': _content_hash(content),
            'parent_bp_id': parent_bp_id,
            'relations': relations,
            'min_grade': min_grade,
            'max_grade': max_grade,
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

    title = _find_title(soup)
    if not title:
        raise ScraperParseError(url, "Kein Titel auf PK-Gruppen-Seite")

    content_parts = []
    main = soup.find('main') or soup
    for elem in main.find_all(['p', 'h2', 'h3']):
        if elem.find_parent('table'):
            continue
        if elem.find_parent(class_=re.compile('breadcrumb|nav|header|footer')):
            continue
        text = strip_soft_hyphens(elem.get_text(separator=" ", strip=True))
        if text:
            content_parts.append(text)
    content = '\n'.join(content_parts) if content_parts else title

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
        sub_bp_id = f"{parent_bp_id}_{nr:02d}"

        # Berechne hierarchische Kompetenz-Nummer
        kompetenz_nr = f"{nr}"
        if current_gruppe:
            try:
                gruppe_nr_match = re.search(r'(\d+)', current_gruppe)
                if gruppe_nr_match:
                    kompetenz_nr = f"{gruppe_nr_match.group(1)}.{nr}"
            except (ValueError, TypeError):
                pass

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
            'title': content[:200],
            'content': content,
            'content_hash': _content_hash(content),
            'parent_bp_id': parent_bp_id,
            'relations': [],
            'min_grade': min_grade,
            'max_grade': max_grade,
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
        'metadata': {
            'bp_id': bp_id,
            'kuerzel': kuerzel,
            'breadcrumb': breadcrumb,
            'source_url': url,
            'scraped_at': _now_iso(),
        },
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
    # Aspekt-Liste steht im main-Content, nicht im Breadcrumb
    main = soup.find('main') or soup
    ul = main.find(['ul', 'ol'])
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
