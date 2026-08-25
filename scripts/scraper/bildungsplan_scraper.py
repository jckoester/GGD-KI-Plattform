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
    ScraperFassungError,
    ScraperKollisionError,
    ScraperParseError,
    parse_fachplan,
    pruefe_eindeutige_bp_ids,
    pruefe_geladene_fassung,
    parse_leitidee,
    parse_ik_kompetenz_list,
    parse_pk_gruppe,
    parse_pk_kompetenz_list,
    parse_leitperspektive,
    parse_leitperspektive_aspekt_list,
    parse_operator_list,
    resolve_grade_band,
)
from scripts.scraper.parsers_gen2x import (
    parse_gen2x_dokument,
    parse_gen2x_leitperspektiven,
)

logger = logging.getLogger('bildungsplan_scraper')

# Dateinamen der frueheren, datierten Ablage: `<fach>_JJJJ-MM-TT.jsonl`.
_DATIERT_RE = re.compile(r'\d{4}-\d{2}-\d{2}\.jsonl')

BASE_URL = 'https://www.bildungsplaene-bw.de/,Lde/'
LP_KUERZEL = ['BNE', 'BTV', 'PG', 'BO', 'MB', 'VB', 'LFDB']
MAX_RETRIES = 3

# Adress-Praefix der neuen Seitengeneration (ab V3).
GEN2X_PRAEFIX = 'DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_'


def gen2x_url(bp_id_basis: str, quell_version: str) -> str:
    """Adresse der neuen Seitengeneration aus altem Bezeichner + Fassungsangabe.

    ``BP2016BW_ALLG_GYM_M`` + ``V3.0`` →
    ``…/DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_GYM_M(V3.0)``

    Die Fassungsangabe steht in der Konfiguration und wird **nicht** aus dem Suffix
    abgeleitet: `.V3` und `(V3.0)` sehen nur zufaellig verwandt aus, und eine
    Folgefassung `(V3.1)` traege weiterhin das Suffix `.V3`.
    """
    teile = bp_id_basis.split('_')
    if len(teile) < 4:
        raise ValueError(
            f"Unerwarteter Aufbau von bp_id_basis: {bp_id_basis!r} "
            f"(erwartet <Praefix>_ALLG_<Schulart>_<Fach>)"
        )
    schulart, fach_code = teile[2], '_'.join(teile[3:])
    return f"{BASE_URL}{GEN2X_PRAEFIX}{schulart}_{fach_code}({quell_version})"


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


def _fach_segment_re(base_bp_id: str, kind: str) -> re.Pattern:
    """Regex, das `base_bp_id` an der Segmentgrenze matcht: optional gefolgt von einem
    Editions-Suffix (`.V2`), dann `_IK_`/`_PK_`. Verhindert die Präfix-Kollision
    `…_NWT` ⊂ `…_NWTBFO` (Substring-Match zöge NWTBFO-Links in einen NWT-Scrape; Todo B1)
    und bleibt zugleich editionskompatibel (`…_CH.V2_IK_…`)."""
    return re.compile(re.escape(base_bp_id) + r'(?:\.[A-Za-z0-9]+)?_' + kind + '_')


def _discover_all_ik_urls(soup: BeautifulSoup, base_bp_id: str) -> dict[str, str]:
    """Entdeckt alle verlinkten IK-Seiten auf der Fach-Uebersichtsseite.

    Gibt dict bp_id -> URL zurueck fuer:
    - direkt verlinkte 2-Segment-Seiten (IK_{JG}_{LI}, z.B. IK_11-12-BF_01)
    - direkt verlinkte 3-Segment-Seiten (IK_{JG}_{LI}_{NR}, z.B. IK_8-9-10_01_01)
    - abgeleitete Leitidee-Seiten (Eltern von 3-Segment-Seiten)
    """
    ik_seg = _fach_segment_re(base_bp_id, 'IK')
    result: dict[str, str] = {}
    for a in soup.find_all('a', href=True):
        href = a['href']
        if not ik_seg.search(href):
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


def _discover_operator_url(soup: BeautifulSoup, fach_bp_id: str) -> str | None:
    """Findet die verlinkte Operatoren-Anhangseite ({fach_bp_id}_OP) auf der Fachplan-Seite.

    Operatoren stehen als eigener Gliederungspunkt im Fach-BP. Kein Link → None
    (Fach ohne Operatoren-Anhang, z. B. nur als PDF veröffentlichte Fremdsprachen).
    """
    op_bp_id = f"{fach_bp_id}_OP"
    for a in soup.find_all('a', href=True):
        path_part = a['href'].split(',Lde/')[-1].split('?')[0].rstrip('/')
        if path_part == op_bp_id:
            return a['href'] if a['href'].startswith('http') else BASE_URL + path_part
    return None


def _discover_pk_gruppen(soup: BeautifulSoup, base_bp_id: str) -> list[tuple[str, str]]:
    """Entdeckt verlinkte PK-Gruppen-Seiten."""
    pk_seg = _fach_segment_re(base_bp_id, 'PK')
    result = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if pk_seg.search(href):
            # Nur PK-Gruppen (haben Nummer nach _PK_): BP..._PK_01, _PK_02
            m = re.search(r'_PK_(\d+)$', href.rstrip('/'))
            if m:
                pk_id = f"{base_bp_id}_PK_{m.group(1)}"
                full_url = href if href.startswith('http') else BASE_URL + href.split(',Lde/')[-1]
                if (pk_id, full_url) not in result:
                    result.append((pk_id, full_url))
    return result


def gen2x_lp_url(quell_version: str) -> str:
    """Adresse der Leitperspektiven in der neuen Seitengeneration.

    Anders als die Fachplaene traegt sie **keine Schulart**:
    `…/DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_LP(V3.0)`. Leitperspektiven gelten
    schulartuebergreifend.
    """
    return f"{BASE_URL}{GEN2X_PRAEFIX}LP({quell_version})"


async def scrape_leitperspektiven(
    client: httpx.AsyncClient,
    quell_versionen: dict[str, str] | None = None,
) -> list[dict]:
    """Scrapt alle Leitperspektiven inkl. Aspekt-Knoten — aus **beiden** Generationen.

    Die Ergebnisse werden **vereinigt**, nicht ersetzt. Grund: Mit der Ueberarbeitung
    2026 loest „Leben und Lernen in einer digitalisierten Welt" (LDW) die Medienbildung
    (MB) ab. Solange Faecher auf alten Fassungen unterrichtet werden, verweisen deren
    Bildungsplaene weiter auf MB — ein reiner Austausch wuerde diese Verweise brechen.

    Die 37 Aspekte, die es in beiden Fassungen gibt, sind **textgleich** (geprueft am
    25.08.2026); die alte Fassung hat daher Vorrang und die neue steuert nur bei, was
    fehlt. Verweise auf Leitperspektiven tragen keine Fassung, deshalb bleiben die
    Knoten unversioniert.
    """
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

    bekannt = {n['bp_id'] for n in nodes}
    # `edition_quell_versionen` liefert {Suffix: Fassungsangabe} — gebraucht wird hier
    # die **Fassungsangabe** (`V3.0`), nicht das Suffix (`.V3`). Über das Dict zu
    # iterieren gäbe die Schlüssel und damit die Adresse `…_LP(.V3)`.
    for quell_version in sorted(set((quell_versionen or {}).values())):
        url = gen2x_lp_url(quell_version)
        try:
            soup = BeautifulSoup(await fetch(client, url), 'lxml')
            pruefe_geladene_fassung(soup, url, url.rsplit('/', 1)[-1])
            neue = [n for n in parse_gen2x_leitperspektiven(soup, url)
                    if n['bp_id'] not in bekannt]
            nodes.extend(neue)
            bekannt.update(n['bp_id'] for n in neue)
            logger.info(
                "Leitperspektiven %s: %d Knoten neu (%s)",
                quell_version, len(neue),
                ", ".join(sorted({n['metadata']['kuerzel'] for n in neue})) or "keine",
            )
        except Exception as e:
            # Kein Abbruch: Die alte Fassung steht bereits, die Faecher koennen scrapen.
            logger.error("Leitperspektiven %s (%s) nicht abrufbar: %s", quell_version, url, e)
    return nodes


async def _sammle_klassisch(
    client: httpx.AsyncClient,
    soup: BeautifulSoup,
    fach_url: str,
    bp_id_basis: str,
    suffix: str,
    warnings: list[str],
) -> list[dict]:
    """Sammelt die Knoten der **alten** Seitengeneration: Übersichtsseite plus
    Unterseiten je Leitidee, PK-Gruppe und Operatoren-Anhang.

    Reiner Umzug aus ``scrape_fach``; unverändert bis auf die frühe Rückgabe, die
    jetzt eine leere Liste ist. Der Aufrufer entscheidet daraus, ob nichts zu
    schreiben ist.
    """
    nodes: list[dict] = []


    # Fachplan
    try:
        nodes.append(parse_fachplan(soup, fach_url))
    except ScraperParseError as e:
        warnings.append(str(e))
        logger.error(str(e))
        return []

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

    # Operatoren-Anhang entdecken (eigene Seite {fachplan}_OP, editionsspezifisch)
    fach_bp_id = bp_id_basis + suffix
    op_url = _discover_operator_url(soup, fach_bp_id)
    if op_url is None:
        logger.info(f"Kein Operatoren-Link fuer {fach_bp_id} (uebersprungen)")
    else:
        try:
            op_html = await fetch(client, op_url)
            op_soup = BeautifulSoup(op_html, 'lxml')
            operator_nodes = parse_operator_list(op_soup, op_url, fach_bp_id)
            if operator_nodes:
                nodes.extend(operator_nodes)
            else:
                warnings.append(f"Operatoren-Seite ohne Tabelle: {fach_bp_id}")
                logger.warning(f"Operatoren-Seite ohne Tabelle: {op_url}")
        except Exception as e:
            warnings.append(f"Operatoren fuer {fach_bp_id} nicht abrufbar: {e}")
            logger.error(f"Operatoren fuer {fach_bp_id} ({op_url}): {e}")


    return nodes


async def scrape_fach(
    client: httpx.AsyncClient,
    fach_code: str,
    bp_id_basis: str,
    suffix: str,
    output_dir: Path,
    existing_hashes: dict[str, str],
    warnings: list[str],
    subject_min_grade: int | None = None,
    subject_max_grade: int | None = None,
    gen2x_version: str | None = None,
) -> tuple[int, int, int]:
    """
    Scrapt ein Fach vollstaendig.
    Gibt (neu, geaendert, unveraendert) zurueck.

    ``gen2x_version`` (z. B. ``"V3.0"``) schaltet auf die neue Seitengeneration um: eine
    Seite je Fach statt Übersichtsseite plus Dutzender Unterseiten. Die Ausgabe ist in
    beiden Fällen dieselbe — ein vollstaendiger Schnappschuss im gewohnten JSONL-Schema.
    """
    fach_bp_id = bp_id_basis + suffix

    # Zwei Seitengenerationen, zwei Adressschemata. Welches gilt, sagt der Fahrplan in
    # `subjects.yaml` (`seitengeneration: gen2x`) — nicht das Suffix. Aus `.V3` auf die
    # neue Generation zu schließen wäre geraten; eine spätere `.V4` könnte das alte
    # Schema behalten, und ein `.V3` einer anderen Schulart ebenso.
    if gen2x_version:
        fach_url = gen2x_url(bp_id_basis, gen2x_version)
        erwartete_kennung = fach_url.rsplit('/', 1)[-1]
    else:
        fach_url = BASE_URL + fach_bp_id
        erwartete_kennung = fach_bp_id

    html = await fetch(client, fach_url)
    soup = BeautifulSoup(html, 'lxml')

    # Erst prüfen, dann parsen. Eine unbekannte Edition liefert kein 404, sondern die
    # Basisfassung — ohne diese Prüfung landen deren Knoten unter falschem Etikett, und
    # zwar lautlos. Der Fehler fällt bis in die Aufrufebene durch: Das Fach wird
    # übersprungen, für diese Edition wird **nichts** geschrieben.
    pruefe_geladene_fassung(soup, fach_url, erwartete_kennung)

    nodes = (
        parse_gen2x_dokument(soup, fach_url, fach_bp_id)
        if gen2x_version
        else await _sammle_klassisch(
            client, soup, fach_url, bp_id_basis, suffix, warnings
        )
    )
    if not nodes:
        return 0, 0, 0

    # Zwei Knoten mit derselben bp_id heissen: Der Parser hat den Aufbau der Seite nicht
    # verstanden. Der Import wuerde daraus lautlos einen machen — lieber gar keine Datei.
    pruefe_eindeutige_bp_ids(nodes, fach_url)

    # Jahrgangsband korrigieren (Todo B1): Kursstufen-Basisfächer (z. B. NWTBFO) tragen
    # in der IK/PK-URL keine Stufen, sondern zero-padded Kompetenzbereichs-Nummern
    # (…_IK_03_…). Für unplausible URL-Bänder das Fach-Band aus subjects.yaml setzen;
    # plausible Bänder (inkl. Sek-I-Hinweisknoten …_IK_5-6_…) bleiben unangetastet.
    for node in nodes:
        node['min_grade'], node['max_grade'] = resolve_grade_band(
            node['bp_id'], node.get('min_grade'), node.get('max_grade'),
            subject_min_grade, subject_max_grade,
        )

    # Wie viel hat sich geaendert? (nur fuer die Meldung — geschrieben wird alles)
    neu, geaendert, unveraendert = 0, 0, 0
    for node in nodes:
        old_hash = existing_hashes.get(node['bp_id'])
        if old_hash is None:
            neu += 1
        elif old_hash != node['content_hash']:
            geaendert += 1
        else:
            unveraendert += 1

    # Eine Datei je Fach/Edition, ohne Datum, mit dem **vollstaendigen** Stand.
    #
    # Frueher wurden nur die geaenderten Knoten in eine datierte Datei geschrieben. Die
    # Ablage bestand damit aus Deltas, und erst alle Dateien zusammen ergaben den ganzen
    # Plan — Physik lag vierfach im Verzeichnis, die juengste Datei mit zwei Knoten. Drei
    # Folgen, die das hatte:
    #   * Der Import liest per glob ALLE Dateien; welcher Stand gewinnt, entschied die
    #     alphabetische Sortierung (bei ISO-Datumsnamen zufaellig die richtige).
    #   * Aenderungen am Scraper schlugen nicht durch: Lag ein alter Knoten mit gleichem
    #     content_hash, aber ohne ein neu hinzugekommenes Metadatenfeld vor, blieb das
    #     Feld leer. CLAUDE.md verlangte deshalb, vorher alle alten Dateien zu loeschen.
    #   * Alte Dateien hielten entfernte Knoten am Leben (im Verzeichnis lag noch ein
    #     Fach, das es in subjects.yaml nicht mehr gibt).
    # Ein vollstaendiger Schnappschuss je Fach macht die Ablage zu dem, wofuer der Import
    # sie ohnehin haelt: dem aktuellen Stand.
    out_file = output_dir / f"{fach_code}.jsonl"
    with out_file.open('w', encoding='utf-8') as f:
        for node in nodes:
            f.write(json.dumps(node, ensure_ascii=False) + '\n')

    # Datierte Vorgaenger desselben Fachs entfernen — sonst laege der alte Delta-Stand
    # daneben und wuerde mitgelesen. Nur exakt `<fach>_JJJJ-MM-TT.jsonl`, damit
    # `CH_BASIS_…` beim Fach `CH` unberuehrt bleibt.
    for alt_datei in output_dir.glob(f"{fach_code}_*.jsonl"):
        if _DATIERT_RE.fullmatch(alt_datei.name[len(fach_code) + 1:]):
            alt_datei.unlink()
            logger.info(f"Alte Delta-Datei entfernt: {alt_datei.name}")

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


def edition_quell_versionen(bp_default: dict) -> dict[str, str]:
    """Suffix → Fassungsangabe für Editionen der **neuen** Seitengeneration.

    Nur Fahrplan-Einträge mit ``seitengeneration: gen2x`` erscheinen; alle anderen
    werden weiterhin über das alte Adressschema geholt. Fehlt bei einem gen2x-Eintrag
    die ``quell_version``, ist das ein Konfigurationsfehler und kein Grund zum Raten —
    ohne sie lässt sich die Adresse nicht bilden.
    """
    versionen: dict[str, str] = {}
    for eintrag in bp_default.get('editionen') or []:
        if str(eintrag.get('seitengeneration') or '').lower() != 'gen2x':
            continue
        suffix = eintrag.get('suffix', '')
        quell_version = eintrag.get('quell_version')
        if not quell_version:
            raise ValueError(
                f"Edition '{suffix or 'Basis'}' ist als seitengeneration: gen2x "
                f"konfiguriert, aber ohne quell_version (z. B. 'V3.0')."
            )
        versionen[suffix] = str(quell_version)
    return versionen


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


async def main(subjects_path: str, output_dir: str, fach_filter: str | None = None, leitperspektiven_only: bool = False) -> list[tuple[str, str]]:
    """Scrapt alle (bzw. das gefilterte) Fächer. Gibt die Liste übersprungener Fächer
    (slug, Fehlergrund) zurück — leer, wenn alles durchlief."""
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
    quell_versionen = edition_quell_versionen(bp_default)
    if quell_versionen:
        logger.info(
            "Neue Seitengeneration (GEN2X) konfiguriert für Edition(en): %s",
            ", ".join(f"{s or 'Basis'} → {v}" for s, v in sorted(quell_versionen.items())),
        )

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
    skipped: list[tuple[str, str]] = []  # (fach-slug, Fehlergrund) — pro Fach isoliert
    total_neu = total_geaendert = total_unveraendert = 0

    async with httpx.AsyncClient(
        headers={'User-Agent': 'GGD-KI-Plattform-Scraper/1.0'},
        timeout=30,
    ) as client:
        # Leitperspektiven zuerst (werden von IK-Standards referenziert)
        lp_nodes = await scrape_leitperspektiven(client, quell_versionen)
        if lp_nodes:
            lp_file = output / "leitperspektiven.jsonl"
            with lp_file.open('w', encoding='utf-8') as f:
                for node in lp_nodes:
                    f.write(json.dumps(node, ensure_ascii=False) + '\n')
            for alt_datei in output.glob("leitperspektiven_*.jsonl"):
                if _DATIERT_RE.fullmatch(alt_datei.name[len("leitperspektiven_"):]):
                    alt_datei.unlink()
                    logger.info(f"Alte Delta-Datei entfernt: {alt_datei.name}")
            logger.info(f"Leitperspektiven: {len(lp_nodes)} Knoten geschrieben")

        if leitperspektiven_only:
            return skipped

        # Faeccher
        for fach in cfg['subjects']:
            fach_code = fach.get('fach_code')
            if not fach_code:
                continue
            # PDF-only-Fächer (Fremdsprachen) haben keine HTML-Fassung → der HTML-Scraper
            # kann sie nicht ziehen. Sie werden über scripts/pdf_import/ eingespielt und
            # hier bewusst übersprungen (sonst nur erfolglose HTTP-Versuche + Skip-Warnung).
            if fach.get('bildungsplan_pdf_url'):
                logger.info(
                    "%s (fach_code=%s): nur als PDF veröffentlicht — HTML-Scrape übersprungen "
                    "(Import via scripts/pdf_import/)",
                    fach.get('slug', fach_code), fach_code,
                )
                continue
            if fach_filter and fach_code.upper() != fach_filter.upper():
                continue

            slug = fach.get('slug', fach_code)
            # Fehler pro Fach isolieren: ein einzelnes Fach (z. B. ungültiges Suffix/URL)
            # darf NICHT den ganzen Batch abbrechen — sonst würde jedes danach folgende Fach
            # stillschweigend nie gescrapt (reihenfolge-abhängige Kaskade). Fehler überspringen,
            # prominent loggen und weitermachen; Zusammenfassung am Ende.
            try:
                bp_id_basis = f"{bp_basis_prefix}_ALLG_{schulart}_{fach_code}"

                # Alle Editionen des Fachs: Fach-Default-Edition + Zusatz-Editionen aus
                # den Jahrgangsband-Overrides.
                neu = geaendert = unveraendert = 0
                for label, edition_suffix in subject_editions(fach, ordered_suffixes, default_suffix):
                    if label == fach_code:
                        logger.info(
                            f"Starte Scrape: {slug} "
                            f"(bp_id_basis={bp_id_basis}, edition='{edition_suffix or 'Basis'}')"
                        )
                    else:
                        logger.info(
                            f"  Zusatz-Edition '{edition_suffix or 'Basis'}' ({label})"
                        )
                    try:
                        n, g, u = await scrape_fach(
                            client, label, bp_id_basis, edition_suffix, output,
                            existing_hashes, warnings,
                            subject_min_grade=fach.get('min_grade'),
                            subject_max_grade=fach.get('max_grade'),
                            gen2x_version=quell_versionen.get(edition_suffix),
                        )
                    except ScraperFassungError:
                        # **Nicht jedes Fach hat jede Zwischenedition.** Der Fahrplan
                        # kennt Basis → V2 → V3; Ethik, Geschichte, Musik und andere sind
                        # aber von der Basisfassung direkt auf V3 gegangen. Ihre
                        # `.V2`-Adresse liefert die Basisfassung — richtig abgewiesen,
                        # aber kein Grund, das Fach fallenzulassen: Seine **eigene**
                        # Edition ist ja da.
                        #
                        # Ohne diese Unterscheidung riss eine fehlende Zwischenedition
                        # 11 von 17 Fächern mitsamt ihrem V3-Plan mit.
                        if label == fach_code:
                            raise
                        logger.warning(
                            "  %s: Edition '%s' gibt es für dieses Fach nicht "
                            "(Adresse liefert eine andere Fassung) — übersprungen",
                            slug, edition_suffix or 'Basis',
                        )
                        warnings.append(
                            f"{slug}: Zwischenedition '{edition_suffix or 'Basis'}' "
                            f"nicht vorhanden"
                        )
                        continue
                    neu += n; geaendert += g; unveraendert += u
            except ScraperKollisionError as exc:
                # Eigener Zweig wie bei der Fassung: Die Quelle hat geantwortet, der
                # Parser hat sie nur falsch gelesen. Der Hinweis spart die Suche.
                logger.error(
                    "!!! Fach '%s' (fach_code=%s) ÜBERSPRUNGEN — %s\n"
                    "    Der Parser bildet fuer verschiedene Knoten denselben Bezeichner. "
                    "Meist fuehrt das Fach mehrere Jahrgangsbaender mit gleichen Stufen "
                    "und gleichem Niveau (Physik: zwei Basisfaecher in 12/13).",
                    slug, fach_code, exc,
                )
                skipped.append((slug, f"{type(exc).__name__}: {exc}"))
                continue
            except ScraperFassungError as exc:
                # Eigener Zweig, weil die Ursache eine andere ist als bei sonstigen
                # Ausfällen: Die Quelle hat geantwortet, nur eben mit der falschen
                # Fassung. Ohne den Hinweis sucht man den Fehler im Scraper statt in
                # der Konfiguration.
                logger.error(
                    "!!! Fach '%s' (fach_code=%s) ÜBERSPRUNGEN — falsche Fassung: %s\n"
                    "    Mögliche Ursachen: Edition noch nicht veröffentlicht, oder sie "
                    "liegt unter dem neuen Adressschema (GEN2X). Konfiguriertes "
                    "bildungsplan_suffix prüfen.",
                    slug, fach_code, exc,
                )
                skipped.append((slug, f"{type(exc).__name__}: {exc}"))
                continue
            except Exception as exc:
                logger.error(
                    "!!! Fach '%s' (fach_code=%s) ÜBERSPRUNGEN — %s: %s",
                    slug, fach_code, type(exc).__name__, exc,
                )
                skipped.append((slug, f"{type(exc).__name__}: {exc}"))
                continue

            logger.info(
                f"{slug}: {neu} neu, {geaendert} geaendert, "
                f"{unveraendert} unveraendert"
            )
            total_neu += neu
            total_geaendert += geaendert
            total_unveraendert += unveraendert

    logger.info(
        f"Gesamt: {total_neu} neu, {total_geaendert} geaendert, "
        f"{total_unveraendert} unveraendert, {len(warnings)} Warnungen, "
        f"{len(skipped)} Fach/Fächer übersprungen"
    )
    if warnings:
        warn_file = output / f"scrape_warnings_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"
        with warn_file.open('w', encoding='utf-8') as f:
            f.write('\n'.join(warnings) + '\n')

    if skipped:
        # Prominente Zusammenfassung, damit ausgefallene Fächer nicht untergehen.
        logger.error("=" * 60)
        logger.error("%d Fach/Fächer wegen Fehlern ÜBERSPRUNGEN (nicht gescrapt):", len(skipped))
        for slug, reason in skipped:
            logger.error("  - %s — %s", slug, reason)
        logger.error("=" * 60)
        skip_file = output / f"scrape_skipped_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"
        with skip_file.open('w', encoding='utf-8') as f:
            f.write('\n'.join(f"{slug}\t{reason}" for slug, reason in skipped) + '\n')

    return skipped


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Bildungsplan-Scraper')
    parser.add_argument('--subjects', default='config/subjects.yaml')
    parser.add_argument('--output', default='scripts/scraper/output')
    parser.add_argument('--fach', default=None, help='Nur dieses Fach scrapen (z.B. CH)')
    parser.add_argument('--leitperspektiven-only', action='store_true',
                        help='Nur Leitperspektiven scrapen, keine Fächer')
    args = parser.parse_args()
    _skipped = asyncio.run(main(args.subjects, args.output, args.fach, args.leitperspektiven_only))
    if _skipped:
        # Non-zero Exit-Code, damit der Ausfall in CI/Skripten nicht untergeht.
        sys.exit(1)
