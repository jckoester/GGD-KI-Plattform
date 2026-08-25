"""Unit-Tests für die Bildungsplan-Editions-Auflösung (Fach-Suffix-Kaskade).

Lädt die Repo-Root-``scripts/``-Module isoliert. Hintergrund: ``backend/scripts``
(Namespace) und ``scripts`` (Repo-Root, reguläres Paket) heißen beide ``scripts``;
der Scraper macht ``from scripts.scraper.parsers import ...``. Damit andere Unit-Tests
(die aus ``backend/scripts`` importieren) unabhängig von der Lade-Reihenfolge intakt
bleiben, wird der ``scripts*``-Zustand in ``sys.modules`` um den Scraper-Import herum
exakt wiederhergestellt.
"""
import importlib.util
import logging
import shutil
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _scripts_keys() -> list[str]:
    return [k for k in sys.modules if k == "scripts" or k.startswith("scripts.")]


def _load_isolated(name: str, rel_path: str, need_repo_on_path: bool = False):
    path = REPO_ROOT / rel_path
    if not need_repo_on_path:
        # Modul ohne 'scripts.'-Importe — vollständig isolierbar.
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    # Modul mit 'from scripts.scraper...'-Importen: Repo-Root muss auf dem Pfad sein.
    # scripts*-Zustand sichern, leeren (damit Repo-Root sauber auflöst), danach
    # exakt zurückspielen — reihenfolgeunabhängig für andere Tests.
    snapshot = {k: sys.modules[k] for k in _scripts_keys()}
    for k in _scripts_keys():
        del sys.modules[k]
    sys.path.insert(0, str(REPO_ROOT))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(REPO_ROOT))
        for k in _scripts_keys():
            del sys.modules[k]
        sys.modules.update(snapshot)
    return mod


_import_bp = _load_isolated("_import_bildungsplan_uut", "scripts/import_bildungsplan.py")
_scraper = _load_isolated(
    "_bildungsplan_scraper_uut",
    "scripts/scraper/bildungsplan_scraper.py",
    need_repo_on_path=True,
)

validate_subjects_yaml = _import_bp.validate_subjects_yaml
subject_editions = _scraper.subject_editions
schedule_suffixes = _scraper.schedule_suffixes
scraper_main = _scraper.main


def _cfg(*subjects: dict) -> dict:
    return {"schulart": "GYM", "schuljahr": "2026/27", "subjects": list(subjects)}


# -- validate_subjects_yaml: neue bildungsplan_suffix-Regel ---------------------


def test_suffix_with_fach_code_is_valid():
    errors = validate_subjects_yaml(
        _cfg({"slug": "mathematik", "fach_code": "M", "bildungsplan_suffix": ".V2"})
    )
    assert errors == []


def test_suffix_without_fach_code_errors():
    errors = validate_subjects_yaml(
        _cfg({"slug": "deutsch", "bildungsplan_suffix": ".V2"})
    )
    assert any("bildungsplan_suffix" in e and "fach_code" in e for e in errors)


def test_non_string_suffix_errors():
    errors = validate_subjects_yaml(
        _cfg({"slug": "mathematik", "fach_code": "M", "bildungsplan_suffix": [".V2"]})
    )
    assert any("nicht-textuelles bildungsplan_suffix" in e for e in errors)


def test_empty_suffix_needs_no_fach_code():
    errors = validate_subjects_yaml(
        _cfg({"slug": "deutsch", "bildungsplan_suffix": ""})
    )
    assert errors == []


# -- subject_editions: Editions-Auflösung pro Fach (Fahrplan-basiert) ----------

# Geordneter Editions-Fahrplan: Basis → V2 → V3.
_SUFFIXES = ["", ".V2", ".V3"]


def test_basis_fach_nur_basis():
    fach = {"fach_code": "M"}
    assert subject_editions(fach, _SUFFIXES, default_suffix="") == [("M", "")]


def test_v2_fach_scrapt_basis_und_v2():
    # Aktuelle Edition .V2 → Basis (als Verweisziel) + V2 (Hauptdatei = fach_code).
    fach = {"fach_code": "CH", "bildungsplan_suffix": ".V2"}
    assert subject_editions(fach, _SUFFIXES, default_suffix="") == [
        ("CH_BASIS", ""),
        ("CH", ".V2"),
    ]


def test_v3_fach_scrapt_alle_bisherigen():
    # Künftig (Fach auf .V3): Basis + V2 + V3.
    fach = {"fach_code": "CH", "bildungsplan_suffix": ".V3"}
    assert subject_editions(fach, _SUFFIXES, default_suffix="") == [
        ("CH_BASIS", ""),
        ("CH_V2", ".V2"),
        ("CH", ".V3"),
    ]


def test_globaler_default_suffix_wird_geerbt():
    # Kein Fach-Suffix, aber globaler Default .V2 → Basis + V2.
    fach = {"fach_code": "M"}
    assert subject_editions(fach, _SUFFIXES, default_suffix=".V2") == [
        ("M_BASIS", ""),
        ("M", ".V2"),
    ]


def test_edition_nicht_im_fahrplan_nur_diese():
    # Fach-Edition, die der Fahrplan nicht kennt → nur sie selbst.
    fach = {"fach_code": "X", "bildungsplan_suffix": ".VX"}
    assert subject_editions(fach, _SUFFIXES, default_suffix="") == [("X", ".VX")]


def test_schedule_suffixes_ordnung():
    bp_default = {
        "suffix": "",
        "editionen": [
            {"suffix": ".V3", "ab_schuljahr": "2026/27"},
            {"suffix": ""},
            {"suffix": ".V2", "ab_schuljahr": "2016/17"},
        ],
    }
    assert schedule_suffixes(bp_default) == ["", ".V2", ".V3"]


def test_schedule_suffixes_fallback_ohne_fahrplan():
    assert schedule_suffixes({"suffix": ""}) == [""]
    assert schedule_suffixes({"suffix": ".V2"}) == [".V2"]


# -- main(): Fehler pro Fach isolieren statt Batch-Abbruch (Todo A1) ------------

def _async_client_cm():
    """Async-Context-Manager-Mock für httpx.AsyncClient(...)."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=MagicMock(name="httpx_client"))
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


_MIN_SUBJECTS_YAML = """\
schulart: GYM
schuljahr: "2026/27"
bildungsplan_default:
  bp_basis: BP2016BW
  suffix: ""
subjects:
  - slug: bad
    fach_code: BAD
  - slug: good
    fach_code: GOOD
"""


def _write_cfg(tmp_path) -> str:
    p = tmp_path / "subjects.yaml"
    p.write_text(_MIN_SUBJECTS_YAML, encoding="utf-8")
    return str(p)


@pytest.mark.asyncio
async def test_main_isolates_failing_fach_and_continues(tmp_path):
    """Ein Fach, das wirft, wird übersprungen; nachfolgende Fächer laufen weiter."""
    def _sf(client, label, *a, **k):
        if label == "BAD":
            raise RuntimeError("ungültige Quell-URL")
        return (1, 0, 0)

    fake_scrape_fach = AsyncMock(side_effect=_sf)
    with patch.object(_scraper, "scrape_leitperspektiven", AsyncMock(return_value=[])), \
         patch.object(_scraper, "scrape_fach", fake_scrape_fach), \
         patch.object(_scraper.httpx, "AsyncClient", return_value=_async_client_cm()):
        skipped = await scraper_main(_write_cfg(tmp_path), str(tmp_path))

    # BAD übersprungen, GOOD trotzdem gescrapt (Reihenfolge-unabhängig).
    assert [slug for slug, _ in skipped] == ["bad"]
    assert "RuntimeError" in skipped[0][1]
    called_labels = {c.args[1] for c in fake_scrape_fach.call_args_list}
    assert called_labels == {"BAD", "GOOD"}


@pytest.mark.asyncio
async def test_main_writes_skip_summary_file(tmp_path):
    """Übersprungene Fächer werden in eine scrape_skipped-Datei geschrieben."""
    fake_scrape_fach = AsyncMock(side_effect=RuntimeError("kaputt"))
    with patch.object(_scraper, "scrape_leitperspektiven", AsyncMock(return_value=[])), \
         patch.object(_scraper, "scrape_fach", fake_scrape_fach), \
         patch.object(_scraper.httpx, "AsyncClient", return_value=_async_client_cm()):
        skipped = await scraper_main(_write_cfg(tmp_path), str(tmp_path))

    assert {slug for slug, _ in skipped} == {"bad", "good"}
    skip_files = list(tmp_path.glob("scrape_skipped_*.log"))
    assert len(skip_files) == 1
    body = skip_files[0].read_text(encoding="utf-8")
    assert "bad" in body and "good" in body


@pytest.mark.asyncio
async def test_main_no_skips_returns_empty(tmp_path):
    """Läuft alles durch, ist die skipped-Liste leer und keine Datei entsteht."""
    with patch.object(_scraper, "scrape_leitperspektiven", AsyncMock(return_value=[])), \
         patch.object(_scraper, "scrape_fach", AsyncMock(return_value=(1, 0, 0))), \
         patch.object(_scraper.httpx, "AsyncClient", return_value=_async_client_cm()):
        skipped = await scraper_main(_write_cfg(tmp_path), str(tmp_path))

    assert skipped == []
    assert list(tmp_path.glob("scrape_skipped_*.log")) == []


# -- Jahrgangsband-Auflösung: Kursstufen-Basisfächer (Todo B1) ------------------

resolve_grade_band = _scraper.resolve_grade_band
_discover_all_ik_urls = _scraper._discover_all_ik_urls
_discover_pk_gruppen = _scraper._discover_pk_gruppen
_BS = _scraper.BeautifulSoup


def test_band_sek1_mehrstufig_bleibt():
    # …_IK_8-9-10_… (echte Stufen) → unverändert.
    assert resolve_grade_band("BP2016BW_ALLG_GYM_NWT_IK_8-9-10_02_01", 8, 10, 11, 12) == (8, 10)


def test_band_sek1_hinweisknoten_5_6_bleibt():
    # Der legitime 5–6-Hinweisknoten darf NICHT plattgebügelt werden.
    assert resolve_grade_band("BP2016BW_ALLG_GYM_NWT_IK_5-6_01", 5, 6, 11, 12) == (5, 6)


def test_band_kursstufe_kompetenzbereich_nutzt_config():
    # …_IK_03_… (zero-padded Kompetenzbereich, fälschlich als (3,3) gelesen) → Fach-Band.
    assert resolve_grade_band("BP2016BW_ALLG_GYM_NWTBFO_IK_03_02_01", 3, 3, 11, 12) == (11, 12)


def test_band_kursstufe_leitidee_nutzt_config():
    # 2-Segment-Leitidee der Kursstufe …_IK_03_02 → ebenfalls Fach-Band.
    assert resolve_grade_band("BP2016BW_ALLG_GYM_NWTBFO_IK_03_02", 3, 3, 11, 12) == (11, 12)


def test_band_zero_padded_in_range_nutzt_config():
    # 07 ist zwar in [5,13], aber zero-padded (Kompetenzbereich) → Config.
    assert resolve_grade_band("BP2016BW_ALLG_GYM_X_IK_07_02_01", 7, 7, 11, 12) == (11, 12)


def test_band_kein_url_band_bleibt_none():
    # Fachplan (kein _IK_/_PK_) → unverändert None.
    assert resolve_grade_band("BP2016BW_ALLG_GYM_NWTBFO", None, None, 11, 12) == (None, None)


def test_band_implausibel_ohne_config_bleibt_none():
    assert resolve_grade_band("BP2016BW_ALLG_GYM_X_IK_03_01", 3, 3, None, None) == (None, None)


# -- Discovery-Filter: Präfix-Kollision NWT ⊂ NWTBFO (Todo B1) ------------------

def _soup(*hrefs: str):
    body = "".join(f'<a href="{h}">x</a>' for h in hrefs)
    return _BS(f"<html><body>{body}</body></html>", "lxml")


_NWT_IK = "https://x/,Lde/BP2016BW_ALLG_GYM_NWT_IK_8-9-10_02_01"
_NWTBFO_IK = "https://x/,Lde/BP2016BW_ALLG_GYM_NWTBFO_IK_03_02_01"
_NWT_PK = "https://x/,Lde/BP2016BW_ALLG_GYM_NWT_PK_01"
_NWTBFO_PK = "https://x/,Lde/BP2016BW_ALLG_GYM_NWTBFO_PK_02"
_CH_V2_IK = "https://x/,Lde/BP2016BW_ALLG_GYM_CH.V2_IK_7-8_01"


def test_ik_discovery_nwt_ignoriert_nwtbfo():
    got = _discover_all_ik_urls(_soup(_NWT_IK, _NWTBFO_IK), "BP2016BW_ALLG_GYM_NWT")
    assert any("_NWT_IK_" in k for k in got)
    assert not any("NWTBFO" in k for k in got)


def test_ik_discovery_nwtbfo_nur_eigene():
    got = _discover_all_ik_urls(_soup(_NWT_IK, _NWTBFO_IK), "BP2016BW_ALLG_GYM_NWTBFO")
    assert all("NWTBFO" in k for k in got)


def test_ik_discovery_edition_suffix_kompatibel():
    # …_CH.V2_IK_… muss trotz Segmentgrenze weiter gefunden werden.
    got = _discover_all_ik_urls(_soup(_CH_V2_IK), "BP2016BW_ALLG_GYM_CH")
    assert any("_CH.V2_IK_" in k for k in got)


def test_pk_discovery_nwt_ignoriert_nwtbfo():
    got = _discover_pk_gruppen(_soup(_NWT_PK, _NWTBFO_PK), "BP2016BW_ALLG_GYM_NWT")
    ids = [pk_id for pk_id, _ in got]
    assert ids == ["BP2016BW_ALLG_GYM_NWT_PK_01"]


# -- upsert_node: Scraper-Grade-Korrektur schlägt bei gleichem Hash durch (Todo B1) --

upsert_node = _import_bp.upsert_node


class _FakeCursor:
    """Minimaler psycopg2-Cursor-Ersatz: erste execute = Existenzprüfung."""
    def __init__(self, existing_row):
        self._existing_row = existing_row
        self.calls = []  # (sql, params)
        self._fetch_next = None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        # Nur der erste (SELECT) liefert eine Zeile für fetchone().
        self._fetch_next = self._existing_row if len(self.calls) == 1 else None

    def fetchone(self):
        return self._fetch_next


def _ik_node(min_grade, max_grade, content_hash="HASH"):
    return {
        "bp_id": "BP2016BW_ALLG_GYM_NWTBFO_IK_03_02_01",
        "content_type": "ik_kompetenz",
        "type": "knowledge",
        "title": "IK 3.3.2.1",
        "content": "Inhalt",
        "content_hash": content_hash,
        "min_grade": min_grade,
        "max_grade": max_grade,
        "niveau": "regulär",
        "bp_version": "2016",
    }


def test_upsert_unchanged_hash_corrects_grade():
    # DB hat noch (3,3); Scrape liefert bei gleichem content_hash jetzt (11,12) → muss überschreiben.
    cur = _FakeCursor(("00000000-0000-0000-0000-000000000001", "HASH"))
    status, _ = upsert_node(cur, _ik_node(11, 12, "HASH"), dry_run=False, subject_id_lookup={})
    assert status == "skipped"  # Hash unverändert → 'skipped', aber Grade wird aktualisiert
    update_sql, params = cur.calls[1]
    assert "COALESCE(%s, min_grade)" in update_sql
    assert "COALESCE(%s, max_grade)" in update_sql
    # Der NEUE Wert (11/12) wird als Parameter übergeben (gewinnt in COALESCE).
    assert 11 in params and 12 in params


def test_upsert_unchanged_hash_null_grade_keeps_existing():
    # Scrape liefert NULL → vorhandener DB-Wert darf NICHT überschrieben werden.
    cur = _FakeCursor(("00000000-0000-0000-0000-000000000002", "HASH"))
    status, _ = upsert_node(cur, _ik_node(None, None, "HASH"), dry_run=False, subject_id_lookup={})
    assert status == "skipped"
    update_sql = cur.calls[1][0]
    # COALESCE(neu, alt): neu=NULL → alter DB-Wert bleibt.
    assert "COALESCE(%s, min_grade)" in update_sql


def test_upsert_unchanged_hash_title_guarded_by_lock():
    # Bei gleichem Hash schützt der Import den Titel per CASE WHEN title_locked (C1).
    cur = _FakeCursor(("00000000-0000-0000-0000-000000000003", "HASH"))
    upsert_node(cur, _ik_node(11, 12, "HASH"), dry_run=False, subject_id_lookup={})
    update_sql = cur.calls[1][0]
    assert "CASE WHEN title_locked THEN title ELSE %s END" in update_sql


def test_upsert_changed_hash_title_guarded_by_lock():
    # Auch im Hash-geändert-Zweig bleibt der gesperrte Titel geschützt.
    cur = _FakeCursor(("00000000-0000-0000-0000-000000000004", "OLDHASH"))
    upsert_node(cur, _ik_node(11, 12, "NEWHASH"), dry_run=False, subject_id_lookup={})
    update_sql = cur.calls[1][0]
    assert "CASE WHEN title_locked THEN title ELSE %s END" in update_sql


def test_upsert_reactivates_archived_node_unchanged_hash():
    # Ein wieder importierter (zuvor archivierter) Knoten wird bei gleichem Hash reaktiviert.
    cur = _FakeCursor(("00000000-0000-0000-0000-000000000005", "HASH"))
    upsert_node(cur, _ik_node(11, 12, "HASH"), dry_run=False, subject_id_lookup={})
    sql = cur.calls[1][0]
    assert "status      = 'active'" in sql and "archived_at = NULL" in sql


def test_upsert_reactivates_archived_node_changed_hash():
    cur = _FakeCursor(("00000000-0000-0000-0000-000000000006", "OLD"))
    upsert_node(cur, _ik_node(11, 12, "NEW"), dry_run=False, subject_id_lookup={})
    sql = cur.calls[1][0]
    assert "status = 'active'" in sql and "archived_at = NULL" in sql


# ── Archivierung: Reichweite eingrenzen (2026-08-08) ─────────────────────────
#
# Auslöser: Ein Voll-Import über das Scraper-Verzeichnis legte Englisch und Französisch
# vollständig still — 959 Knoten. Beide werden aus PDFs importiert und liegen in einem
# anderen Ausgabeverzeichnis; für den Import sahen sie aus wie entfernte Knoten.

archive_removed_nodes = _import_bp.archive_removed_nodes
stillgelegte_faecher = _import_bp.stillgelegte_faecher


class _ArchivCursor:
    """Cursor-Ersatz, der die abgesetzten Abfragen mitschreibt."""

    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows


def test_archivierung_ist_auf_die_importierten_faecher_begrenzt():
    """Der Kern des Fixes: Fächer außerhalb des Imports dürfen nicht erfasst werden."""
    cur = _ArchivCursor()
    archive_removed_nodes(
        cur, {"BP_A", "BP_B"}, dry_run=True, subject_ids={2, 7}, mit_fachlosen=False
    )
    sql, params = cur.calls[0]
    assert "subject_id = ANY(%s)" in sql
    fachlisten = [
        p for p in params if isinstance(p, list) and p and isinstance(p[0], int)
    ]
    assert fachlisten == [[2, 7]] or fachlisten == [[7, 2]], fachlisten


def test_fachlose_knoten_werden_nur_bei_bedarf_erfasst():
    """Leitperspektiven hängen an keinem Fach.

    Eine reine Fach-Einschränkung erwischte sie nie — enthält der Import aber
    Leitperspektiven, sollen veraltete darunter sehr wohl archiviert werden.
    """
    for flag in (True, False):
        cur = _ArchivCursor()
        archive_removed_nodes(
            cur, {"BP_A"}, dry_run=True, subject_ids={2}, mit_fachlosen=flag
        )
        sql, params = cur.calls[0]
        assert "subject_id IS NULL AND %s" in sql
        assert flag in params


def test_ohne_fachliste_wird_nichts_fremdes_archiviert():
    """Vorgabe ist die leere Menge — im Zweifel lieber zu wenig als zu viel."""
    cur = _ArchivCursor()
    archive_removed_nodes(cur, {"BP_A"}, dry_run=True)
    _, params = cur.calls[0]
    assert [] in params


# ── Fach fällt aus subjects.yaml: melden, nur auf Ansage archivieren ─────────

_CFG = {"subjects": [{"slug": "mathematik", "fach_code": "M"}]}


def test_fehlendes_fach_wird_gemeldet_aber_nicht_archiviert():
    """Ohne `--prune-subjects` passiert nichts — es wird nur berichtet.

    `config/subjects.yaml` ist gitignored (kein Diff, kein `git blame`) und `--subjects`
    ist ein Pfadparameter: Ein Fehlgriff auf `subjects.example.yaml` (2 statt 27 Fächer)
    sähe aus wie „25 Fächer abgeschafft". Deshalb ist das Fehlen ein Signal, kein Befehl.
    """
    cur = _ArchivCursor(rows=[("L2", "Latein", 291)])
    anzahl, betroffen = stillgelegte_faecher(cur, _CFG, prune=False, dry_run=False)
    assert anzahl == 0
    assert betroffen == [("L2", "Latein", 291)]
    assert len(cur.calls) == 1, "Ohne prune darf kein UPDATE abgesetzt werden"


def test_mit_prune_wird_archiviert():
    cur = _ArchivCursor(rows=[("L2", "Latein", 291)])
    cur.rowcount = 291
    anzahl, _ = stillgelegte_faecher(cur, _CFG, prune=True, dry_run=False)
    assert anzahl == 291
    assert any("SET status = 'archived'" in sql for sql, _ in cur.calls)


def test_prune_schreibt_im_dry_run_nicht():
    cur = _ArchivCursor(rows=[("L2", "Latein", 291)])
    anzahl, _ = stillgelegte_faecher(cur, _CFG, prune=True, dry_run=True)
    assert anzahl == 291                      # gemeldet …
    assert len(cur.calls) == 1                # … aber kein UPDATE


def test_leere_konfiguration_legt_nichts_still():
    """„Datei kaputt oder leer" darf nicht heißen „alle Fächer abgeschafft"."""
    cur = _ArchivCursor(rows=[("L2", "Latein", 291)])
    anzahl, betroffen = stillgelegte_faecher(cur, {"subjects": []}, prune=True, dry_run=False)
    assert (anzahl, betroffen) == (0, [])
    assert cur.calls == []


# ── Warnungs-Log: fester Pfad statt arbeitsverzeichnis-relativ (2026-08-08) ───


def test_log_pfad_haengt_nicht_am_arbeitsverzeichnis():
    """`Path("data/import_logs")` erzeugte zwei gleichnamige Dateien.

    Lief `pytest` in `backend/`, landeten Testfixtures (`GYM_TST`, `DOES_NOT_EXIST`) in
    `backend/data/import_logs/`; echte Importe schrieben an die Repo-Wurzel. Nutzer und
    Assistent haben beim Auswerten **verschiedene Dateien** angesehen und aneinander
    vorbeigeredet — deshalb ist der Pfad jetzt an der Projektwurzel verankert.
    """
    wurzel = _import_bp.PROJEKT_WURZEL

    # Nicht den Quelltext auf eine Schreibweise absuchen — der Kommentar dort zitiert
    # den alten Pfad und ließe eine solche Prüfung fälschlich anschlagen. Geprüft wird
    # die Substanz: ein absoluter Pfad, verankert an der Projektwurzel.
    assert wurzel.is_absolute()
    assert wurzel.name != "scripts", "zeigt auf scripts/ statt auf die Projektwurzel"
    assert (wurzel / "scripts").is_dir() and (wurzel / "config").is_dir()

    vorgabe = wurzel / "data" / "import_logs"
    assert vorgabe.is_absolute(), (
        "Ein relativer Vorgabepfad erzeugt je Arbeitsverzeichnis eine eigene Logdatei."
    )


def test_log_verzeichnis_ist_ueberschreibbar():
    """`--log-dir` — im Container muss das Log auf ein gemountetes Volume können.

    Ohne das waren die Warnungen nach einem `--rm`-Lauf schlicht weg.
    """
    import inspect

    assert "log_dir" in inspect.signature(_import_bp.run_import).parameters


# ── Scraper-Ablage: vollständige Schnappschüsse statt Deltas (2026-08-08) ─────


def _knoten(bp_id: str, content_hash: str) -> dict:
    return {
        "bp_id": bp_id, "content_hash": content_hash, "content_type": "ik_kompetenz",
        "title": bp_id, "content": "x", "min_grade": 5, "max_grade": 6, "metadata": {},
    }


def _schreibe(tmp_path, label: str, knoten: list[dict], vorhandene_hashes: dict):
    """Ruft den Schreibteil von `scrape_fach` nach — ohne Netzzugriff."""
    import json

    neu = geaendert = unveraendert = 0
    for n in knoten:
        alt = vorhandene_hashes.get(n["bp_id"])
        if alt is None:
            neu += 1
        elif alt != n["content_hash"]:
            geaendert += 1
        else:
            unveraendert += 1
    out = tmp_path / f"{label}.jsonl"
    out.write_text(
        "".join(json.dumps(n, ensure_ascii=False) + "\n" for n in knoten), encoding="utf-8"
    )
    for alt_datei in tmp_path.glob(f"{label}_*.jsonl"):
        if _scraper._DATIERT_RE.fullmatch(alt_datei.name[len(label) + 1:]):
            alt_datei.unlink()
    return neu, geaendert, unveraendert


def test_datierte_vorgaenger_werden_entfernt(tmp_path):
    """Der Kern der Umstellung.

    Vorher enthielt jede datierte Datei nur die **geänderten** Knoten; erst alle
    zusammen ergaben den Plan (Physik lag vierfach im Verzeichnis, die jüngste Datei mit
    zwei Knoten). Jetzt ist eine Datei je Fach der vollständige Stand — die alten Deltas
    müssen also weg, sonst würden sie mitgelesen.
    """
    (tmp_path / "CH_2026-06-27.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "CH_2026-08-24.jsonl").write_text("{}\n", encoding="utf-8")

    _schreibe(tmp_path, "CH", [_knoten("A", "h1"), _knoten("B", "h2")], {})

    assert (tmp_path / "CH.jsonl").exists()
    assert not list(tmp_path.glob("CH_2026-*.jsonl"))


def test_fremdes_fach_mit_gleichem_praefix_bleibt(tmp_path):
    """`CH_BASIS_2026-08-24.jsonl` darf beim Fach `CH` nicht mitgelöscht werden.

    Ein reiner Präfixvergleich (`CH_*`) träfe es — deshalb muss auf das Datumsmuster
    geprüft werden, nicht auf den Präfix allein.
    """
    (tmp_path / "CH_BASIS_2026-08-24.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "CH_2026-08-24.jsonl").write_text("{}\n", encoding="utf-8")

    _schreibe(tmp_path, "CH", [_knoten("A", "h1")], {})

    assert (tmp_path / "CH_BASIS_2026-08-24.jsonl").exists()
    assert not (tmp_path / "CH_2026-08-24.jsonl").exists()


def test_datei_enthaelt_alle_knoten_nicht_nur_geaenderte(tmp_path):
    """Auch unveränderte Knoten stehen in der Datei — sie ist der ganze Stand.

    Genau hier lag der alte Fehler: Bei einem Re-Scrape mit einer Änderung entstand eine
    Datei mit **einem** Knoten. Wer sie für den Plan hielt, hatte 169 Knoten zu wenig.
    """
    import json

    vorhanden = {"A": "h1", "B": "h2"}
    neu, geaendert, unveraendert = _schreibe(
        tmp_path, "CH", [_knoten("A", "h1"), _knoten("B", "NEU")], vorhanden
    )

    zeilen = (tmp_path / "CH.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(zeilen) == 2, "Auch der unveränderte Knoten muss in der Datei stehen"
    assert {json.loads(z)["bp_id"] for z in zeilen} == {"A", "B"}
    # Die Meldung unterscheidet weiterhin — nur die Ablage tut es nicht mehr.
    assert (neu, geaendert, unveraendert) == (0, 1, 1)


# ---------------------------------------------------------------------------
# Wo liegt das `app`-Paket? (Produktions-Absturz vom 25.08.2026)
# ---------------------------------------------------------------------------


def _lade_kopie(basis: Path, skript_rel: str, app_rel: str | None, name: str):
    """Kopiert ``import_bildungsplan.py`` in einen nachgebauten Baum und lädt es dort.

    Nur so ist die Pfad-Auflösung prüfbar: Sie hängt an ``__file__`` und läuft beim
    Import — es gibt keine Funktion, die man mit einem anderen Pfad aufrufen könnte.

    ``app_rel`` ist relativ zu ``basis`` (``""`` = ``basis`` selbst); ``None`` legt gar
    kein ``app``-Paket an.
    """
    skript_dir = basis / skript_rel
    skript_dir.mkdir(parents=True)
    skript = skript_dir / "import_bildungsplan.py"
    shutil.copy(REPO_ROOT / "scripts" / "import_bildungsplan.py", skript)

    if app_rel is not None:
        wurzel = basis / app_rel if app_rel else basis
        editions = wurzel / "app" / "context" / "editions.py"
        editions.parent.mkdir(parents=True, exist_ok=True)
        editions.write_text("", encoding="utf-8")

    pfad_vorher = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location(name, skript)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        # Das Skript trägt seine gefundene Wurzel selbst in sys.path ein.
        sys.path[:] = pfad_vorher
    return mod


def test_backend_wurzel_repo_layout(tmp_path):
    """Entwicklung: `scripts/` und `backend/` liegen nebeneinander."""
    mod = _lade_kopie(tmp_path, "scripts", "backend", "_bp_repo_layout")

    assert mod.BACKEND_WURZEL == tmp_path / "backend"


def test_backend_wurzel_container_layout(tmp_path):
    """Produktion: `scripts/` ist nach `/app/import-scripts` gemountet.

    Genau hier brach der Import am 25.08.2026 ab — **nach** dem Schreiben aller
    Knoten, mit `ModuleNotFoundError: No module named 'app'`. Im Image gibt es kein
    `backend/`; WORKDIR ist `/app` und das Paket liegt direkt darunter (`/app/app`).
    Beide Layouts haben dieselbe `PROJEKT_WURZEL`, brauchen aber verschiedene Pfade —
    Raten reicht nicht, es muss nachgesehen werden.
    """
    basis = tmp_path / "app"
    mod = _lade_kopie(basis, "import-scripts", "", "_bp_container_layout")

    assert mod.BACKEND_WURZEL == basis


def test_backend_wurzel_fehlt_bricht_import_nicht_ab(tmp_path):
    """Kein `app`-Paket auffindbar → `None`, aber das Modul lädt.

    Das Skript muss ohne Backend benutzbar bleiben; nur die Editions-Archivierung
    hängt daran.
    """
    mod = _lade_kopie(tmp_path, "scripts", None, "_bp_ohne_app")

    assert mod.BACKEND_WURZEL is None


class _AppBlocker:
    """Meta-Path-Finder, der jeden `app`-Import scheitern lässt.

    Simuliert den Container, in dem das Paket nicht gefunden wird — `sys.modules`
    allein genügt nicht, weil `app` im Testprozess längst geladen ist.
    """

    def find_spec(self, name, path=None, target=None):
        if name == "app" or name.startswith("app."):
            raise ModuleNotFoundError(f"No module named '{name}'")
        return None


def test_archivierung_uebersprungen_statt_abbruch_ohne_app_paket(caplog):
    """Ohne `app` wird die Editions-Archivierung übersprungen, nicht abgebrochen.

    Sie ist der **letzte** Schritt vor dem Commit: Eine Ausnahme verwirft den
    vollständigen, gültigen Import. Nicht zu archivieren lässt dagegen nur überholte
    Knoten aktiv — das verliert nichts und ist jederzeit nachholbar.
    """
    cfg = {
        "subjects": [
            {"slug": "mathematik", "fach_code": "M", "bildungsplan_suffix": ".V2"}
        ]
    }

    entfernt = {
        k: sys.modules.pop(k)
        for k in list(sys.modules)
        if k == "app" or k.startswith("app.")
    }
    blocker = _AppBlocker()
    sys.meta_path.insert(0, blocker)
    try:
        with caplog.at_level(logging.ERROR):
            # cur=None: Der Ausstieg erfolgt, bevor die Datenbank angefasst wird.
            archiviert = _import_bp.archive_superseded_nodes(
                None, cfg, {"mathematik": 1}, dry_run=False
            )
    finally:
        sys.meta_path.remove(blocker)
        sys.modules.update(entfernt)

    assert archiviert == 0
    assert "UEBERSPRUNGEN" in caplog.text, "Der Ausfall muss im Log stehen"


# ---------------------------------------------------------------------------
# Fassungsprüfung: Liefert die Quelle wirklich die angeforderte Fassung?
# (Fehlscrape vom 24.08.2026)
# ---------------------------------------------------------------------------

_parsers = _load_isolated(
    "_bildungsplan_parsers_uut", "scripts/scraper/parsers.py", need_repo_on_path=True
)
pruefe_geladene_fassung = _parsers.pruefe_geladene_fassung
fassungsmarke = _parsers.fassungsmarke
ScraperFassungError = _parsers.ScraperFassungError
ScraperParseError = _parsers.ScraperParseError


def _seite(titel: str, canonical: str | None = None):
    """Minimalseite mit den Kopfangaben, auf die die Prüfung schaut.

    Die Titel sind **wörtlich** von bildungsplaene-bw.de übernommen (abgerufen
    25.08.2026) — erfundene Titel würden hier nichts beweisen.
    """
    from bs4 import BeautifulSoup

    link = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    return BeautifulSoup(
        f"<html><head><title>{titel}</title>{link}</head><body></body></html>", "lxml"
    )


_TITEL_V2 = "Mathematik vom 23. März 2016 in der Fassung vom 29. Februar 2024 (V2) - Bildungsplan"
_TITEL_BASIS = "Mathematik - Bildungsplan"
_TITEL_V3 = "BPBW-ALLG-GYM-M(V3.0) - Bildungsplan"
_BASIS_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_M"


def test_fassung_korrekt_kein_fehler():
    """V2 angefordert, V2 geliefert. Die richtige Seite trägt kein canonical."""
    pruefe_geladene_fassung(_seite(_TITEL_V2), "…", "BP2016BW_ALLG_GYM_M.V2")


def test_fassung_unbekannte_edition_liefert_basisfassung():
    """Der Fehlerfall vom 24.08.2026 — und der Grund für diese ganze Prüfung.

    Die Adresse mit `.V3` antwortet **nicht** mit 404, sondern mit HTTP 200 und der
    Seite von 2016. Der Scraper holte so 409 Basis-Knoten und legte sie unter
    V3-Etikett ab; aufgefallen wäre es erst 2026/27 an einem leeren Bildungsplan.
    Die Seite verrät sich über ihren canonical-Link.
    """
    with pytest.raises(ScraperFassungError) as exc:
        pruefe_geladene_fassung(
            _seite(_TITEL_BASIS, canonical=_BASIS_URL), "…", "BP2016BW_ALLG_GYM_M.V3"
        )
    # Die Meldung muss beide Seiten nennen, sonst ist sie nicht handlungsleitend.
    assert "BP2016BW_ALLG_GYM_M.V3" in str(exc.value)
    assert "BP2016BW_ALLG_GYM_M" in str(exc.value)


def test_fassung_basis_angefordert_basis_geliefert():
    """Basisfassung ist ein gültiger Wunsch — canonical zeigt dann korrekt auf sie."""
    pruefe_geladene_fassung(
        _seite(_TITEL_BASIS, canonical=_BASIS_URL), "…", "BP2016BW_ALLG_GYM_M"
    )


def test_fassung_basis_angefordert_edition_geliefert():
    """Auch die Gegenrichtung wird erkannt — hier über den Titel, kein canonical da."""
    with pytest.raises(ScraperFassungError) as exc:
        pruefe_geladene_fassung(_seite(_TITEL_V2), "…", "BP2016BW_ALLG_GYM_M")
    assert "Basisfassung" in str(exc.value) and "V2" in str(exc.value)


def test_fassung_gen2x_korrekt():
    """Neue Seitengeneration: Marke steht im Bezeichner *und* im Titel."""
    pruefe_geladene_fassung(
        _seite(_TITEL_V3), "…", "DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_GYM_M(V3.0)"
    )


def test_fassung_gen2x_angefordert_alte_seite_geliefert():
    """V3 (GEN2X) angefordert, alte Seite geliefert → Ausfall."""
    with pytest.raises(ScraperFassungError):
        pruefe_geladene_fassung(
            _seite(_TITEL_V2), "…", "DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_GYM_M(V3.0)"
        )


@pytest.mark.parametrize(
    "bezeichner,erwartet",
    [
        ("BP2016BW_ALLG_GYM_M.V2", "V2"),
        ("BP2016BW_ALLG_GYM_M", None),
        ("DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_GYM_M(V3.0)", "V3.0"),
    ],
)
def test_fassungsmarke_beide_generationen(bezeichner, erwartet):
    assert fassungsmarke(bezeichner) == erwartet


def test_fassungsfehler_ist_kein_parsefehler():
    """Bewusste Trennung — dieser Test hält sie fest.

    Wäre `ScraperFassungError` eine Unterklasse von `ScraperParseError`, würden die
    bestehenden `except ScraperParseError`-Zweige im Scraper sie schlucken: Warnung
    protokollieren, weitermachen, falsche Knoten schreiben. Genau das soll nicht
    passieren — das Fach muss ausfallen.
    """
    assert not issubclass(ScraperFassungError, ScraperParseError)


@pytest.mark.asyncio
async def test_scrape_fach_schreibt_bei_falscher_fassung_nichts(tmp_path):
    """Die Verdrahtung, nicht nur die Prüffunktion: kein JSONL bei falscher Fassung.

    Der Ausfall muss **vor** dem Parsen greifen und bis zur Aufrufebene durchfallen —
    dort isoliert `main()` je Fach. Bliebe eine halb geschriebene Datei liegen, wäre
    der Schaden derselbe wie ohne Prüfung.
    """
    seite = (
        f"<html><head><title>{_TITEL_BASIS}</title>"
        f'<link rel="canonical" href="{_BASIS_URL}"></head><body></body></html>'
    )
    with patch.object(_scraper, "fetch", AsyncMock(return_value=seite)):
        with pytest.raises(_scraper.ScraperFassungError):
            await _scraper.scrape_fach(
                MagicMock(), "M", "BP2016BW_ALLG_GYM_M", ".V3",
                tmp_path, {}, [],
            )

    assert list(tmp_path.glob("*.jsonl")) == [], "Bei falscher Fassung darf nichts entstehen"
