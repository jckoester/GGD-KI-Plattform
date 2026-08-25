"""Unit-Tests für den GEN2X-Parser (Bildungsplan V3, neue Seitengeneration).

Die Fixture ist ein **gekürzter Ausschnitt der echten Seite**
`DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_GYM_M(V3.0)` (abgerufen 25.08.2026): Kopfbereich,
die PK-Gruppe 2.1 sowie die Bänder „Klassen 5/6", „Klasse 11" und „Klassen 12/13
(Leistungsfach)". Gerade die letzten beiden sind der Grund für den Ausschnitt — sie
kommen in V2 nicht vor. Erfundenes Markup würde hier nichts beweisen.

Zum Modul-Laden siehe CLAUDE.md: `backend/scripts` und `scripts` (Repo-Wurzel) heißen
beide `scripts`; der Zustand in `sys.modules` wird um den Import herum wiederhergestellt.
"""
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).parent / "fixtures" / "bildungsplan_gen2x_gym_m_v3.html"
QUELL_URL = (
    "https://www.bildungsplaene-bw.de/,Lde/"
    "DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_GYM_M(V3.0)"
)
BP_ID_FACH = "BP2016BW_ALLG_GYM_M.V3"


def _scripts_keys() -> list[str]:
    return [k for k in sys.modules if k == "scripts" or k.startswith("scripts.")]


def _load(name: str, rel_path: str):
    snapshot = {k: sys.modules[k] for k in _scripts_keys()}
    for k in _scripts_keys():
        del sys.modules[k]
    sys.path.insert(0, str(REPO_ROOT))
    try:
        spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(REPO_ROOT))
        for k in _scripts_keys():
            del sys.modules[k]
        sys.modules.update(snapshot)
    return mod


_gen2x = _load("_parsers_gen2x_uut", "scripts/scraper/parsers_gen2x.py")
_parsers = _load("_parsers_fuer_gen2x_uut", "scripts/scraper/parsers.py")

parse_gen2x_dokument = _gen2x.parse_gen2x_dokument
band_aus_ueberschrift = _gen2x.band_aus_ueberschrift


@pytest.fixture(scope="module")
def knoten() -> list[dict]:
    soup = BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "lxml")
    return parse_gen2x_dokument(soup, QUELL_URL, BP_ID_FACH)


def _eines(knoten: list[dict], bp_id: str) -> dict:
    treffer = [k for k in knoten if k["bp_id"] == bp_id]
    assert len(treffer) == 1, f"{bp_id}: {len(treffer)} Treffer statt 1"
    return treffer[0]


# ── Struktur ────────────────────────────────────────────────────────────────


def test_knotenzahl_je_typ(knoten):
    """Der Ausschnitt enthält genau eine PK-Gruppe und drei Leitideen."""
    aus_fixture = {}
    for k in knoten:
        aus_fixture[k["content_type"]] = aus_fixture.get(k["content_type"], 0) + 1
    assert aus_fixture == {
        "fachplan": 1,
        "pk_gruppe": 1,
        "pk_kompetenz": 13,
        "leitidee": 3,
        "ik_kompetenz": 44,
    }


def test_fachplan_traegt_gen2x_kennung(knoten):
    """Der Bezeichner folgt E1 dem alten Schema — die Herkunft bleibt in den Metadaten."""
    fp = _eines(knoten, BP_ID_FACH)
    assert fp["content_type"] == "fachplan"
    assert fp["parent_bp_id"] is None
    assert fp["bp_version"] == "2016.V3"
    assert fp["metadata"]["gen2x_id"] == "DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_GYM_M(V3.0)"


def test_ik_kompetenz_feldweise(knoten):
    """Ein inhaltsbezogener Standard vollständig — Schema wie in der alten Generation."""
    k = _eines(knoten, "BP2016BW_ALLG_GYM_M.V3_IK_5-6_01_00_01")
    assert k["content_type"] == "ik_kompetenz"
    assert k["title"] == (
        "3.1.1(1) die Prinzipien des dezimalen Stellenwertsystems im Vergleich "
        "zu einem anderen Zahlensystem beschreiben"
    )
    assert k["content"].startswith("(1) die Prinzipien des dezimalen")
    assert k["parent_bp_id"] == "BP2016BW_ALLG_GYM_M.V3_IK_5-6_01"
    assert (k["min_grade"], k["max_grade"], k["niveau"]) == (5, 6, "regulär")
    assert k["metadata"]["kompetenz_nr"] == "3.1.1(1)"
    assert k["metadata"]["standard_nr"] == 1
    assert k["metadata"]["thematische_gruppe"] == "Zahlbereiche erkunden"


def test_pk_kompetenz_hat_neue_nummernform(knoten):
    """Die prozessbezogenen Kompetenzen sind in V3 **neu nummeriert**.

    V2: `2.1.1` · V3: `2.1(1)`. Das ist kein Parserfehler, sondern eine Änderung der
    Quelle — und der Grund, warum PK-Nummern zwischen den Fassungen nicht mehr
    kollidieren können.
    """
    k = _eines(knoten, "BP2016BW_ALLG_GYM_M.V3_PK_01_01")
    assert k["content_type"] == "pk_kompetenz"
    assert k["metadata"]["kompetenz_nr"] == "2.1(1)"
    assert k["title"].startswith("2.1(1) in mathematischen Zusammenhängen")
    assert (k["min_grade"], k["max_grade"]) == (None, None), "PK tragen keine Klassenstufe"
    assert k["metadata"]["thematische_gruppe"]


def test_leitidee_traegt_einleitungstext(knoten):
    li = _eines(knoten, "BP2016BW_ALLG_GYM_M.V3_IK_5-6_01")
    assert li["title"] == "3.1.1 Leitidee Zahl – Variable – Operation"
    assert li["content"].startswith("Die Schülerinnen und Schüler entwickeln tragfähige")
    assert li["parent_bp_id"] == BP_ID_FACH


# ── Jahrgangsbänder ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ueberschrift,erwartet",
    [
        ("3.1 Klassen 5/6", ("5-6", 5, 6, "regulär")),
        ("3.2 Klassen 7/8", ("7-8", 7, 8, "regulär")),
        ("3.3 Klassen 9/10", ("9-10", 9, 10, "regulär")),
        ("3.4 Klasse 11", ("11", 11, 11, "regulär")),
        ("3.5 Klassen 12/13 (Leistungsfach)", ("12-13-LF", 12, 13, "leistung")),
        ("3.6 Klassen 12/13 (Basisfach)", ("12-13-BF", 12, 13, "basis")),
    ],
)
def test_band_aus_ueberschrift(ueberschrift, erwartet):
    """Alle sechs Bänder der V3-Mathematik. V2 kannte 5-6, 7-8, 9-10 und 11-12 (BF/LF)."""
    assert band_aus_ueberschrift(ueberschrift) == erwartet


def test_einzelstufe_bekommt_gleiche_unter_und_obergrenze(knoten):
    """„Klasse 11" ist ein Band aus einer Stufe — sonst stünde sie ohne Jahrgang da."""
    li = _eines(knoten, "BP2016BW_ALLG_GYM_M.V3_IK_11_01")
    assert (li["min_grade"], li["max_grade"]) == (11, 11)


def test_niveau_aus_bandueberschrift(knoten):
    """Leistungs-/Basisfach steht in V3 in der Überschrift, nicht mehr in der URL."""
    li = _eines(knoten, "BP2016BW_ALLG_GYM_M.V3_IK_12-13-LF_01")
    assert (li["min_grade"], li["max_grade"], li["niveau"]) == (12, 13, "leistung")


def test_band_ohne_klassenangabe_wirft():
    with pytest.raises(ValueError, match="Keine Klassenstufen"):
        band_aus_ueberschrift("3.7 Anhang")


# ── Verträglichkeit mit dem Bestand (Entscheidung E1) ───────────────────────


def test_erzeugte_bp_ids_werden_von_bestandshelfern_gelesen(knoten):
    """Das Versprechen aus E1: Import, Fahrplan und Archivierung bleiben unberührt.

    Die vorhandenen Helfer lesen Stufen, Niveau und Fassung aus der bp_id — auch aus
    den **neuen** Bandformen `11` und `12-13-LF`, die es in V2 nicht gab. Wäre das
    nicht so, zöge jeder V3-Knoten Folgeänderungen im Import nach sich.
    """
    for k in knoten:
        if k["content_type"] not in ("ik_kompetenz", "leitidee"):
            continue
        assert _parsers.extract_grades_from_bp_id(k["bp_id"]) == (
            k["min_grade"],
            k["max_grade"],
        )
        assert _parsers.extract_niveau_from_bp_id(k["bp_id"]) == k["niveau"]
        assert _parsers.extract_bp_version(k["bp_id"]) == "2016.V3"


def test_keine_weichen_trennstriche(knoten):
    """GEN2X setzt U+00AD im gesamten Fließtext — unsichtbar, aber verheerend.

    Bliebe er stehen, wäre „Leit\xadge\xaddan\xadken" ein anderer String als
    „Leitgedanken": Suche fände nichts, und der Content-Hash schlüge bei jedem Lauf an.
    """
    for k in knoten:
        assert "\xad" not in k["title"], k["bp_id"]
        assert "\xad" not in (k["content"] or ""), k["bp_id"]


def test_alle_bp_ids_eindeutig(knoten):
    ids = [k["bp_id"] for k in knoten]
    assert len(ids) == len(set(ids))


# ── Verdrahtung im Scraper (Schritt 3) ──────────────────────────────────────

_scraper = _load("_scraper_fuer_gen2x_uut", "scripts/scraper/bildungsplan_scraper.py")


def test_gen2x_url_aus_altem_bezeichner():
    assert _scraper.gen2x_url("BP2016BW_ALLG_GYM_M", "V3.0") == (
        "https://www.bildungsplaene-bw.de/,Lde/"
        "DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_GYM_M(V3.0)"
    )


def test_gen2x_url_uebernimmt_schulart_und_fach():
    """Schulart und Fachkürzel stammen aus dem Bezeichner, nicht aus einer zweiten Quelle."""
    assert _scraper.gen2x_url("BP2016BW_ALLG_RS_INFWFO", "V3.1").endswith(
        "GEN2X_BPBW_ALLG_RS_INFWFO(V3.1)"
    )


def test_gen2x_url_bei_unerwartetem_bezeichner():
    with pytest.raises(ValueError, match="Unerwarteter Aufbau"):
        _scraper.gen2x_url("kaputt", "V3.0")


def test_quell_versionen_nur_fuer_gen2x_editionen():
    """Nur ausdrücklich markierte Editionen wechseln das Adressschema."""
    fahrplan = {
        "editionen": [
            {"suffix": ""},
            {"suffix": ".V2", "ab_schuljahr": "2016/17"},
            {"suffix": ".V3", "seitengeneration": "gen2x", "quell_version": "V3.0"},
        ]
    }
    assert _scraper.edition_quell_versionen(fahrplan) == {".V3": "V3.0"}


def test_quell_version_fehlt_ist_konfigurationsfehler():
    """Aus `.V3` auf `(V3.0)` zu schließen wäre geraten — eine V3.1 trüge dasselbe Suffix."""
    fahrplan = {"editionen": [{"suffix": ".V3", "seitengeneration": "gen2x"}]}
    with pytest.raises(ValueError, match="quell_version"):
        _scraper.edition_quell_versionen(fahrplan)


def _fake_fetch(gesehen: list[str], antwort: str):
    async def fetch(client, url):
        gesehen.append(url)
        return antwort
    return fetch


@pytest.mark.asyncio
async def test_scrape_fach_gen2x_holt_genau_eine_seite(tmp_path):
    """Der eigentliche Gewinn der neuen Generation: ein Abruf statt Dutzender.

    Die alte Generation lud die Übersichtsseite und danach je Leitidee, PK-Gruppe und
    Operatoren-Anhang eine eigene Unterseite.
    """
    gesehen: list[str] = []
    with patch.object(_scraper, "fetch", _fake_fetch(gesehen, FIXTURE.read_text(encoding="utf-8"))):
        neu, geaendert, unveraendert = await _scraper.scrape_fach(
            MagicMock(), "M", "BP2016BW_ALLG_GYM_M", ".V3",
            tmp_path, {}, [], gen2x_version="V3.0",
        )

    assert gesehen == [
        "https://www.bildungsplaene-bw.de/,Lde/"
        "DE_BW_BILDUNGSPLAENE_GEN2X_BPBW_ALLG_GYM_M(V3.0)"
    ]
    assert (neu, geaendert, unveraendert) == (62, 0, 0)

    zeilen = (tmp_path / "M.jsonl").read_text(encoding="utf-8").strip().split("\n")
    knoten = [json.loads(z) for z in zeilen]
    assert len(knoten) == 62
    assert {k["bp_version"] for k in knoten} == {"2016.V3"}


@pytest.mark.asyncio
async def test_scrape_fach_ohne_gen2x_nutzt_altes_schema(tmp_path):
    """Regressionsschutz: Ohne Fassungsangabe bleibt alles beim Alten.

    Die Fixture ist hier bewusst leer bis auf den Titel — geprüft wird die **Adresse**,
    nicht das Ergebnis.
    """
    titel = (
        "Mathematik vom 23. März 2016 in der Fassung vom 29. Februar 2024 (V2) "
        "- Bildungsplan"
    )
    gesehen: list[str] = []
    seite = f"<html><head><title>{titel}</title></head><body></body></html>"
    with patch.object(_scraper, "fetch", _fake_fetch(gesehen, seite)):
        ergebnis = await _scraper.scrape_fach(
            MagicMock(), "M", "BP2016BW_ALLG_GYM_M", ".V2", tmp_path, {}, [],
        )

    assert gesehen == ["https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_M.V2"]
    assert ergebnis == (0, 0, 0)
    assert list(tmp_path.glob("*.jsonl")) == []


@pytest.mark.asyncio
async def test_fassungspruefung_gilt_auch_fuer_gen2x(tmp_path):
    """Schritt 1 greift auch auf dem neuen Weg — sonst wäre die Falle nur halb zu."""
    seite = (
        "<html><head><title>Mathematik - Bildungsplan</title>"
        '<link rel="canonical" href="https://www.bildungsplaene-bw.de/,Lde/'
        'BP2016BW_ALLG_GYM_M"></head><body></body></html>'
    )
    with patch.object(_scraper, "fetch", _fake_fetch([], seite)):
        with pytest.raises(_scraper.ScraperFassungError):
            await _scraper.scrape_fach(
                MagicMock(), "M", "BP2016BW_ALLG_GYM_M", ".V3",
                tmp_path, {}, [], gen2x_version="V3.0",
            )
    assert list(tmp_path.glob("*.jsonl")) == []


_SUBJECTS_MIT_GEN2X = """\
schulart: GYM
bildungsplan_default:
  bp_basis: BP2016BW
  suffix: ""
  editionen:
    - suffix: ""
    - suffix: ".V2"
      ab_schuljahr: "2016/17"
    - suffix: ".V3"
      ab_schuljahr: "2026/27"
      seitengeneration: gen2x
      quell_version: "V3.0"
subjects:
  - slug: mathematik
    fach_code: M
    bildungsplan_suffix: ".V3"
"""


@pytest.mark.asyncio
async def test_main_reicht_fassungsangabe_aus_dem_fahrplan_durch(tmp_path):
    """Die Angabe aus `subjects.yaml` muss bis in `scrape_fach` ankommen.

    Ohne diesen Test bleibt die Verdrahtung ungeprüft: Die übrigen Tests rufen
    `scrape_fach` direkt auf und würden auch dann grün bleiben, wenn `main()` die
    Fassungsangabe gar nicht weiterreicht — das Fach liefe dann stillschweigend über
    das alte Adressschema und fiele erst an der Fassungsprüfung auf.
    """
    cfg = tmp_path / "subjects.yaml"
    cfg.write_text(_SUBJECTS_MIT_GEN2X, encoding="utf-8")

    fake = AsyncMock(return_value=(0, 0, 0))
    with patch.object(_scraper, "scrape_leitperspektiven", AsyncMock(return_value=[])), \
         patch.object(_scraper, "scrape_fach", fake), \
         patch.object(_scraper.httpx, "AsyncClient", return_value=_async_cm()):
        await _scraper.main(str(cfg), str(tmp_path / "out"))

    # Ein Aufruf je Edition; nur die V3-Edition trägt die Fassungsangabe.
    nach_suffix = {c.args[3]: c.kwargs.get("gen2x_version") for c in fake.call_args_list}
    assert nach_suffix == {"": None, ".V2": None, ".V3": "V3.0"}


def _async_cm():
    """Async-Context-Manager-Mock für httpx.AsyncClient(...)."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=MagicMock(name="httpx_client"))
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm
