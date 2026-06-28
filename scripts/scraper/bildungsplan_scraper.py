"""Bildungsplan-Scraper — Hauptmodul.

Aufruf:
  python -m scripts.scraper.bildungsplan_scraper \
    --subjects config/subjects.yaml \
    --output scripts/scraper/output \
    [--fach CH]          # nur ein Fach; ohne Flag: alle Faecher mit fach_code

Rate-Limiting: <= 2 Requests/Sekunde (asyncio.sleep(0.5) nach jedem Fetch).
"""

import asyncio
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup

from scripts.scraper.parsers import (
    ScraperParseError,
    parse_fachplan,
    parse_leitidee,
    parse_ik_kompetenz_list,
    parse_pk_gruppe,
    parse_pk_kompetenz_list,
    parse_leitperspektive,
    parse_leitperspektive_aspekt_list,
)

logger = logging.getLogger('bildungsplan_scraper')

BASE_URL = 'https://www.bildungsplaene-bw.de/,Lde/'
LP_KUERZEL = ['BNE', 'BTV', 'PG', 'BO', 'MB', 'VB', 'LFDB']
MAX_RETRIES = 3


async def fetch(client: httpx.AsyncClient, url: str) -> str:
    """Fetcht eine URL mit Retry-Backoff bei 429/503."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.get(url, follow_redirects=True, timeout=30)
            if resp.status_code == 429:
                wait = 2 ** attempt * 2
                logger.warning(f"429 auf {url}, warte {wait}s")
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            await asyncio.sleep(0.5)  # Rate-Limiting: <= 2 req/s
            return resp.text
        except httpx.HTTPStatusError as e:
            if attempt == MAX_RETRIES - 1:
                raise
            logger.warning(f"HTTP {e.response.status_code} auf {url}, Versuch {attempt + 1}")
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"Alle {MAX_RETRIES} Versuche fuer {url} fehlgeschlagen")


def _discover_all_ik_urls(soup: BeautifulSoup, base_bp_id: str) -> dict[str, str]:
    """Entdeckt alle verlinkten IK-Seiten auf der Fach-Uebersichtsseite.

    Gibt dict bp_id -> URL zurueck fuer:
    - direkt verlinkte 2-Segment-Seiten (IK_{JG}_{LI}, z.B. IK_11-12-BF_01)
    - direkt verlinkte 3-Segment-Seiten (IK_{JG}_{LI}_{NR}, z.B. IK_8-9-10_01_01)
    - abgeleitete Leitidee-Seiten (Eltern von 3-Segment-Seiten)
    """
    result: dict[str, str] = {}
    for a in soup.find_all('a', href=True):
        href = a['href']
        if base_bp_id not in href or '_IK_' not in href:
            continue
        # BP-ID ist der Pfad-Teil nach ',Lde/'
        path_part = href.split(',Lde/')[-1].split('?')[0].rstrip('/')
        if not path_part.startswith('BP') or '_IK_' not in path_part:
            continue
        full_url = href if href.startswith('http') else BASE_URL + path_part
        if path_part not in result:
            result[path_part] = full_url
        # Fuer 3-Segment-Links: abgeleitete Leitidee-Eltern-Seite ergaenzen
        ik_suffix = re.sub(r'^.*_IK_', '', path_part)
        if len(ik_suffix.split('_')) >= 3:
            parent_bp_id = path_part.rsplit('_', 1)[0]
            if parent_bp_id not in result:
                result[parent_bp_id] = full_url.rsplit('_', 1)[0]
    return result


def _discover_pk_gruppen(soup: BeautifulSoup, base_bp_id: str) -> list[tuple[str, str]]:
    """Entdeckt verlinkte PK-Gruppen-Seiten."""
    result = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if base_bp_id in href and '_PK_' in href:
            # Nur PK-Gruppen (haben Nummer nach _PK_): BP..._PK_01, _PK_02
            m = re.search(r'_PK_(\d+)$', href.rstrip('/'))
            if m:
                pk_id = f"{base_bp_id}_PK_{m.group(1)}"
                full_url = href if href.startswith('http') else BASE_URL + href.split(',Lde/')[-1]
                if (pk_id, full_url) not in result:
                    result.append((pk_id, full_url))
    return result


async def scrape_leitperspektiven(
    client: httpx.AsyncClient,
) -> list[dict]:
    """Scrapt alle 7 Leitperspektiven inkl. Aspekt-Knoten."""
    nodes = []
    for kuerzel in LP_KUERZEL:
        url = BASE_URL + f"BP2016BW_ALLG_LP_{kuerzel}"
        try:
            html = await fetch(client, url)
            soup = BeautifulSoup(html, 'lxml')
            nodes.append(parse_leitperspektive(soup, url, kuerzel))
            nodes.extend(parse_leitperspektive_aspekt_list(soup, url, kuerzel))
            logger.debug(f"LP {kuerzel}: gescrapt")
        except ScraperParseError as e:
            logger.error(f"Parse-Fehler LP {kuerzel}: {e}")
        except Exception as e:
            logger.error(f"Fehler bei LP {kuerzel} ({url}): {e}")
    return nodes


async def scrape_fach(
    client: httpx.AsyncClient,
    fach_code: str,
    bp_id_basis: str,
    suffix: str,
    output_dir: Path,
    existing_hashes: dict[str, str],
    warnings: list[str],
) -> tuple[int, int, int]:
    """
    Scrapt ein Fach vollstaendig.
    Gibt (neu, geaendert, unveraendert) zurueck.
    """
    fach_url = BASE_URL + bp_id_basis + suffix
    html = await fetch(client, fach_url)
    soup = BeautifulSoup(html, 'lxml')
    nodes = []

    # Fachplan
    try:
        nodes.append(parse_fachplan(soup, fach_url))
    except ScraperParseError as e:
        warnings.append(str(e))
        logger.error(str(e))
        return 0, 0, 0

    # IK-Seiten entdecken (Leitideen + Standard-Seiten)
    ik_urls = _discover_all_ik_urls(soup, bp_id_basis)
    if not ik_urls:
        warnings.append(f"Keine IK-Seiten fuer {bp_id_basis} entdeckt")
        logger.warning(f"Keine IK-Seiten fuer {bp_id_basis}")

    for ik_bp_id, ik_url in ik_urls.items():
        try:
            ik_html = await fetch(client, ik_url)
            ik_soup = BeautifulSoup(ik_html, 'lxml')
            leitidee_node = parse_leitidee(ik_soup, ik_url)
            nodes.append(leitidee_node)
            # tktable-Seiten liefern ik_kompetenz-Knoten; andere geben [] zurueck
            ik_kompetenz_nodes = parse_ik_kompetenz_list(ik_soup, ik_url, leitidee_node['bp_id'])
            nodes.extend(ik_kompetenz_nodes)
        except ScraperParseError as e:
            warnings.append(str(e))
            logger.error(str(e))

    # PK-Gruppen entdecken
    pk_gruppen = _discover_pk_gruppen(soup, bp_id_basis)
    for pk_bp_id, pk_url in pk_gruppen:
        try:
            pk_html = await fetch(client, pk_url)
            pk_soup = BeautifulSoup(pk_html, 'lxml')
            pk_gruppe_node = parse_pk_gruppe(pk_soup, pk_url)
            nodes.append(pk_gruppe_node)
            pk_kompetenzen = parse_pk_kompetenz_list(pk_soup, pk_url, pk_gruppe_node['bp_id'])
            nodes.extend(pk_kompetenzen)
        except ScraperParseError as e:
            warnings.append(str(e))
            logger.error(str(e))

    # Idempotenz-Filter: nur neue/geaenderte Knoten schreiben
    neu, geaendert, unveraendert = 0, 0, 0
    filtered = []
    for node in nodes:
        bp_id = node['bp_id']
        new_hash = node['content_hash']
        old_hash = existing_hashes.get(bp_id)
        if old_hash is None:
            neu += 1
            filtered.append(node)
        elif old_hash != new_hash:
            geaendert += 1
            filtered.append(node)
        else:
            unveraendert += 1

    if filtered:
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        out_file = output_dir / f"{fach_code}_{date_str}.jsonl"
        with out_file.open('w', encoding='utf-8') as f:
            for node in filtered:
                f.write(json.dumps(node, ensure_ascii=False) + '\n')

    return neu, geaendert, unveraendert


def schedule_suffixes(bp_default: dict) -> list[str]:
    """Geordnete Editions-Suffixe aus dem Fahrplan (``bildungsplan_default.editionen``):
    Basis ("") zuerst, danach nach ``ab_schuljahr`` aufsteigend.

    Fallback (kein Fahrplan): nur die globale ``suffix``-Basis.
    """
    editionen = bp_default.get('editionen')
    if not editionen:
        return [bp_default.get('suffix', '')]

    def _start(entry: dict) -> tuple[int, int]:
        ab = entry.get('ab_schuljahr')
        if not ab:
            return (0, 0)  # Basis/ohne ab_schuljahr zuerst
        m = re.match(r'\s*(\d{4})', str(ab))
        return (1, int(m.group(1)) if m else 0)

    return [e.get('suffix', '') for e in sorted(editionen, key=_start)]


def subject_editions(
    fach: dict, ordered_suffixes: list[str], default_suffix: str
) -> list[tuple[str, str]]:
    """Liefert die zu scrapenden Editionen eines Fachs als (label, suffix)-Paare.

    Ein Fach trägt während des Editionsübergangs **mehrere** Editionen gleichzeitig:
    die Basis plus alle Fahrplan-Editionen bis einschließlich der aktuellen
    Fach-Edition (``bildungsplan_suffix``). Die ältere(n) bleiben als (später
    archivierte) Verweisziele erhalten, die aktuelle ist das gelebte Curriculum.

    Datei-Label: die **aktuelle** Edition bekommt ``fach_code`` (Hauptdatei), die
    übrigen ein qualifiziertes Label (z. B. ``CH_BASIS``, ``CH_V2``).
    """
    fach_code = fach['fach_code']
    current = fach.get('bildungsplan_suffix', default_suffix)
    if current in ordered_suffixes:
        wanted = ordered_suffixes[: ordered_suffixes.index(current) + 1]
    else:
        # Fahrplan kennt die Fach-Edition nicht → nur diese scrapen.
        wanted = [current]

    editions: list[tuple[str, str]] = []
    for suf in wanted:
        if suf == current:
            label = fach_code
        else:
            label = f"{fach_code}_{suf.lstrip('.') or 'BASIS'}"
        editions.append((label, suf))
    return editions


async def main(subjects_path: str, output_dir: str, fach_filter: str | None = None, leitperspektiven_only: bool = False) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    with open(subjects_path, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    schulart = cfg['schulart']
    bp_default = cfg.get('bildungsplan_default', {})
    bp_basis_prefix = bp_default.get('bp_basis', 'BP2016BW')
    default_suffix = bp_default.get('suffix', '')
    ordered_suffixes = schedule_suffixes(bp_default)

    # Bestehendes JSONL fuer Hash-Vergleich einlesen
    existing_hashes: dict[str, str] = {}
    for jsonl_file in output.glob('*.jsonl'):
        with jsonl_file.open(encoding='utf-8') as f:
            for line in f:
                try:
                    node = json.loads(line)
                    bp_id = node.get('bp_id')
                    ch = node.get('content_hash') or node.get('metadata', {}).get('content_hash')
                    if bp_id and ch:
                        existing_hashes[bp_id] = ch
                except json.JSONDecodeError:
                    pass

    warnings: list[str] = []
    total_neu = total_geaendert = total_unveraendert = 0

    async with httpx.AsyncClient(
        headers={'User-Agent': 'GGD-KI-Plattform-Scraper/1.0'},
        timeout=30,
    ) as client:
        # Leitperspektiven zuerst (werden von IK-Standards referenziert)
        lp_nodes = await scrape_leitperspektiven(client)
        if lp_nodes:
            date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            lp_file = output / f"leitperspektiven_{date_str}.jsonl"
            with lp_file.open('w', encoding='utf-8') as f:
                for node in lp_nodes:
                    f.write(json.dumps(node, ensure_ascii=False) + '\n')
            logger.info(f"Leitperspektiven: {len(lp_nodes)} Knoten geschrieben")

        if leitperspektiven_only:
            return

        # Faeccher
        for fach in cfg['subjects']:
            fach_code = fach.get('fach_code')
            if not fach_code:
                continue
            if fach_filter and fach_code.upper() != fach_filter.upper():
                continue

            bp_id_basis = f"{bp_basis_prefix}_ALLG_{schulart}_{fach_code}"

            # Alle Editionen des Fachs: Fach-Default-Edition + Zusatz-Editionen aus
            # den Jahrgangsband-Overrides.
            neu = geaendert = unveraendert = 0
            for label, edition_suffix in subject_editions(fach, ordered_suffixes, default_suffix):
                if label == fach_code:
                    logger.info(
                        f"Starte Scrape: {fach['slug']} "
                        f"(bp_id_basis={bp_id_basis}, edition='{edition_suffix or 'Basis'}')"
                    )
                else:
                    logger.info(
                        f"  Zusatz-Edition '{edition_suffix or 'Basis'}' ({label})"
                    )
                n, g, u = await scrape_fach(
                    client, label, bp_id_basis, edition_suffix, output,
                    existing_hashes, warnings,
                )
                neu += n; geaendert += g; unveraendert += u

            logger.info(
                f"{fach['slug']}: {neu} neu, {geaendert} geaendert, "
                f"{unveraendert} unveraendert"
            )
            total_neu += neu
            total_geaendert += geaendert
            total_unveraendert += unveraendert

    logger.info(
        f"Gesamt: {total_neu} neu, {total_geaendert} geaendert, "
        f"{total_unveraendert} unveraendert, {len(warnings)} Warnungen"
    )
    if warnings:
        warn_file = output / f"scrape_warnings_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"
        with warn_file.open('w', encoding='utf-8') as f:
            f.write('\n'.join(warnings) + '\n')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Bildungsplan-Scraper')
    parser.add_argument('--subjects', default='config/subjects.yaml')
    parser.add_argument('--output', default='scripts/scraper/output')
    parser.add_argument('--fach', default=None, help='Nur dieses Fach scrapen (z.B. CH)')
    parser.add_argument('--leitperspektiven-only', action='store_true',
                        help='Nur Leitperspektiven scrapen, keine Fächer')
    args = parser.parse_args()
    asyncio.run(main(args.subjects, args.output, args.fach, args.leitperspektiven_only))
