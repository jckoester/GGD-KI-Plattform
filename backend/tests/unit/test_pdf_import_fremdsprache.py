"""Unit-Tests für den Fremdsprachen-Assembler (KS-Plan C3, Schritt 3).

Prüft, dass die neutrale Struktur deterministisch in scraper-kompatible Knoten übersetzt wird
(bp_id-Schema, Parent-Ketten, Content-/Hash-Format, Bänder/Niveau, Leitperspektiven-Verweise).
Lädt die Repo-Root-``scripts/``-Module isoliert wie in test_pdf_import.py.
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _scripts_keys() -> list[str]:
    return [k for k in sys.modules if k == "scripts" or k.startswith("scripts.")]


def _load_isolated(name: str, rel_path: str, need_repo_on_path: bool = False):
    path = REPO_ROOT / rel_path
    if not need_repo_on_path:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
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


_extract = _load_isolated("_fs_extract_uut", "scripts/pdf_import/extract.py")
_fremd = _load_isolated("_fremd_uut", "scripts/pdf_import/fremdsprache.py", need_repo_on_path=True)

validate_fremdsprache_structure = _extract.validate_fremdsprache_structure
detect_fremdsprache_chunks = _extract.detect_fremdsprache_chunks
detect_operator_chunk = _extract.detect_operator_chunk
build_fremdsprache_nodes = _fremd.build_fremdsprache_nodes
build_operator_nodes = _fremd.build_operator_nodes
render_fremdsprache_report = _fremd.render_fremdsprache_report
_lp_relations = _fremd._lp_relations
_band_segment = _fremd._band_segment
_last_num = _fremd._last_num
_clean_text = _fremd._clean_text

BASE = "BP2016BW_ALLG_GYM_E1.V2"


def _structure() -> dict:
    return {
        "fach": {"titel": "Englisch als erste Fremdsprache", "leitgedanken": "Leitgedanken-Text."},
        "prozessbezogene_kompetenzbereiche": [
            {
                "nummer": "2.1", "titel": "Sprachbewusstheit",
                "kompetenzen": [
                    {"nummer": 1, "text": "sprachliche Mittel reflektieren"},
                    {"nummer": 2, "text": "über Sprache sprechen"},
                ],
            },
        ],
        "jahrgangsstufen": [
            {
                "nummer": "3.1", "titel": "Klassen 5/6", "klasse_von": 5, "klasse_bis": 6, "niveau": None,
                "kompetenzbereiche": [
                    {
                        "nummer": "3.1.1", "titel": "Funktionale kommunikative Kompetenz",
                        "beschreibung": "", "kompetenzen": [],
                        "teilbereiche": [
                            {
                                "nummer": "3.1.1.1", "titel": "Hör-/Hörsehverstehen", "beschreibung": "",
                                "kompetenzen": [
                                    {"nummer": 1, "text": "Äußerungen verstehen", "verweise": ["MB", "BNE 2"]},
                                ],
                            },
                        ],
                    },
                    {
                        "nummer": "3.1.2", "titel": "Interkulturelle Kompetenz",
                        "beschreibung": "", "teilbereiche": [],
                        "kompetenzen": [
                            {"nummer": 1, "text": "kulturelle Vielfalt wahrnehmen", "verweise": ["BTV"]},
                        ],
                    },
                ],
            },
            {
                "nummer": "3.4", "titel": "Kursstufe Leistungsfach", "klasse_von": 11, "klasse_bis": 12,
                "niveau": "leistung",
                "kompetenzbereiche": [
                    {
                        "nummer": "3.4.1", "titel": "Leseverstehen",
                        "kompetenzen": [{"nummer": 1, "text": "komplexe Texte verstehen", "verweise": []}],
                    },
                ],
            },
        ],
    }


@pytest.fixture
def nodes():
    return build_fremdsprache_nodes(
        _structure(), fach_code="E1", suffix=".V2", schulart="GYM",
        bp_basis="BP2016BW", source_url="http://x/E1.pdf",
    )


@pytest.fixture
def by_id(nodes):
    return {n["bp_id"]: n for n in nodes}


# ── Struktur / Zählung ────────────────────────────────────────────────────────

def test_node_count(nodes):
    # 1 fachplan + 1 pk_gruppe + 2 pk_kompetenz + (3.1.1 + 3.1.1.1 + 1 ik)
    # + (3.1.2 + 1 ik) + (3.4.1 + 1 ik) = 11
    assert len(nodes) == 11


def test_content_types(nodes):
    from collections import Counter
    c = Counter(n["content_type"] for n in nodes)
    assert c == {"fachplan": 1, "pk_gruppe": 1, "pk_kompetenz": 2, "leitidee": 4, "ik_kompetenz": 3}


def test_all_parents_resolvable(nodes, by_id):
    """Jeder parent_bp_id (außer Fachplan) muss auf einen erzeugten Knoten zeigen —
    sonst schlägt die part_of-Auflösung des Imports fehl."""
    roots = [n for n in nodes if n["parent_bp_id"] is None]
    assert len(roots) == 1 and roots[0]["content_type"] == "fachplan"
    for n in nodes:
        if n["parent_bp_id"] is not None:
            assert n["parent_bp_id"] in by_id, f"{n['bp_id']} → {n['parent_bp_id']} fehlt"


# ── Fachplan ──────────────────────────────────────────────────────────────────

def test_fachplan(by_id):
    fp = by_id[BASE]
    assert fp["content_type"] == "fachplan"
    assert fp["parent_bp_id"] is None
    assert fp["title"] == "Englisch als erste Fremdsprache"
    assert fp["content"] == "Leitgedanken-Text."
    assert fp["min_grade"] is None and fp["max_grade"] is None
    assert fp["niveau"] == "regulär"
    assert fp["bp_version"] == "2016.V2"
    assert fp["metadata"]["breadcrumb"] == ["Englisch als erste Fremdsprache"]


def test_fachplan_content_fallback_to_title():
    struct = _structure()
    struct["fach"]["leitgedanken"] = ""
    nodes = build_fremdsprache_nodes(struct, fach_code="E1", suffix=".V2")
    fp = next(n for n in nodes if n["content_type"] == "fachplan")
    assert fp["content"] == "Englisch als erste Fremdsprache"


# ── Prozessbezogene Kompetenzen ───────────────────────────────────────────────

def test_pk_gruppe(by_id):
    g = by_id[f"{BASE}_PK_01"]
    assert g["content_type"] == "pk_gruppe"
    assert g["parent_bp_id"] == BASE
    assert g["title"] == "2.1 Sprachbewusstheit"
    assert g["content"] == "Sprachbewusstheit"
    assert g["min_grade"] is None and g["max_grade"] is None


def test_pk_kompetenz(by_id):
    k = by_id[f"{BASE}_PK_01_01"]
    assert k["content_type"] == "pk_kompetenz"
    assert k["parent_bp_id"] == f"{BASE}_PK_01"
    assert k["title"] == "2.1.1 sprachliche Mittel reflektieren"
    assert k["content"] == "1. sprachliche Mittel reflektieren"
    assert k["metadata"]["kompetenz_nr"] == "2.1.1"
    assert k["metadata"]["standard_nr"] == 1
    assert by_id[f"{BASE}_PK_01_02"]["content"] == "2. über Sprache sprechen"


# ── Leitideen (2-/3-stufig) ───────────────────────────────────────────────────

def test_leitidee_two_and_three_segment(by_id):
    b = by_id[f"{BASE}_IK_5-6_01"]           # Kompetenzbereich 3.1.1 (2-seg)
    assert b["content_type"] == "leitidee"
    assert b["parent_bp_id"] == BASE
    assert b["title"] == "3.1.1 Funktionale kommunikative Kompetenz"
    assert (b["min_grade"], b["max_grade"]) == (5, 6)

    t = by_id[f"{BASE}_IK_5-6_01_01"]        # Teilbereich 3.1.1.1 (3-seg)
    assert t["content_type"] == "leitidee"
    assert t["parent_bp_id"] == f"{BASE}_IK_5-6_01"
    assert t["title"] == "3.1.1.1 Hör-/Hörsehverstehen"


def test_leitidee_direct_kompetenzen(by_id):
    """Ein Bereich ohne Teilbereiche wird selbst zur (2-seg-)Leitidee der IK-Knoten."""
    b = by_id[f"{BASE}_IK_5-6_02"]           # 3.1.2, direkte Kompetenzen
    assert b["content_type"] == "leitidee"
    assert b["parent_bp_id"] == BASE
    ik = by_id[f"{BASE}_IK_5-6_02_01"]
    assert ik["parent_bp_id"] == f"{BASE}_IK_5-6_02"
    assert ik["metadata"]["kompetenz_nr"] == "3.1.2(1)"


# ── Inhaltsbezogene Kompetenzen ───────────────────────────────────────────────

def test_ik_kompetenz(by_id):
    ik = by_id[f"{BASE}_IK_5-6_01_01_01"]
    assert ik["content_type"] == "ik_kompetenz"
    assert ik["parent_bp_id"] == f"{BASE}_IK_5-6_01_01"
    assert ik["content"] == "(1) Äußerungen verstehen"
    assert ik["title"] == "3.1.1.1(1) Äußerungen verstehen"
    assert ik["metadata"]["kompetenz_nr"] == "3.1.1.1(1)"
    assert ik["metadata"]["standard_nr"] == 1
    assert (ik["min_grade"], ik["max_grade"]) == (5, 6)
    assert ik["niveau"] == "regulär"


def test_ik_relations_from_verweise(by_id):
    ik = by_id[f"{BASE}_IK_5-6_01_01_01"]
    # "MB" (bloßes Kürzel) → Übersichtsknoten; "BNE 2" → Aspektknoten
    assert ik["relations"] == [
        {"target_bp_id": "BP2016BW_ALLG_LP_MB", "type": "references"},
        {"target_bp_id": "BNE_02", "type": "references"},
    ]
    assert ik["metadata"]["verweise"] == ["MB", "BNE 2"]


def test_ik_verweis_ohne_nummer_uebersicht(by_id):
    ik = by_id[f"{BASE}_IK_5-6_02_01"]       # verweise ["BTV"] → LP-Übersichtsknoten
    assert ik["relations"] == [{"target_bp_id": "BP2016BW_ALLG_LP_BTV", "type": "references"}]
    assert ik["metadata"]["verweise"] == ["BTV"]


# ── Kursstufe: Niveau + Bandsegment ───────────────────────────────────────────

def test_kursstufe_leistung_band(by_id):
    b = by_id[f"{BASE}_IK_11-12-LF_01"]
    assert b["niveau"] == "leistung"
    assert (b["min_grade"], b["max_grade"]) == (11, 12)
    ik = by_id[f"{BASE}_IK_11-12-LF_01_01"]
    assert ik["niveau"] == "leistung"
    assert ik["content"] == "(1) komplexe Texte verstehen"


# ── Hash / bp_version-Konsistenz (Idempotenz-Schlüssel) ───────────────────────

def test_content_hash_matches_content(nodes):
    for n in nodes:
        expected = "sha256:" + hashlib.sha256(n["content"].encode("utf-8")).hexdigest()
        assert n["content_hash"] == expected


def test_bp_version_everywhere(nodes):
    assert all(n["bp_version"] == "2016.V2" for n in nodes)


def test_visibility_and_type(nodes):
    assert all(n["type"] == "knowledge" and n["visibility"] == "global" for n in nodes)


# ── Helfer ────────────────────────────────────────────────────────────────────

def test_last_num():
    assert _last_num("2.1") == 1
    assert _last_num("3.1.1") == 1
    assert _last_num("3.1.10") == 10
    assert _last_num("3.4.1.2") == 2


def test_clean_text():
    assert _clean_text("Sprachen .") == "Sprachen."
    assert _clean_text("Wetter, Hobbys , Essen .") == "Wetter, Hobbys, Essen."
    assert _clean_text("z. B. Restaurantbesuch") == "z. B. Restaurantbesuch"   # Abkürzung unangetastet
    assert _clean_text("doppelte   Leerzeichen") == "doppelte Leerzeichen"
    assert _clean_text(None) == ""


def test_clean_text_applied_to_content(by_id):
    """PDF-Typografie (Leerzeichen vor Punkt) wird in content/title normalisiert."""
    ik = build_fremdsprache_nodes(
        {"fach": {"titel": "Englisch", "leitgedanken": ""},
         "prozessbezogene_kompetenzbereiche": [
             {"nummer": "2.1", "titel": "X", "kompetenzen": [{"nummer": 1, "text": "A B ."}]}],
         "jahrgangsstufen": [
             {"nummer": "3.1", "titel": "Klassen 5/6", "klasse_von": 5, "klasse_bis": 6, "niveau": None,
              "kompetenzbereiche": [{"nummer": "3.1.1", "titel": "Y",
                                     "kompetenzen": [{"nummer": 1, "text": "C D .", "verweise": []}]}]}]},
        fach_code="E1", suffix=".V2",
    )
    komp = next(n for n in ik if n["content_type"] == "ik_kompetenz")
    assert komp["content"] == "(1) C D."


def test_band_segment():
    assert _band_segment(5, 6, None) == "5-6"
    assert _band_segment(10, 10, None) == "10"
    assert _band_segment(11, 12, "basis") == "11-12-BF"
    assert _band_segment(11, 12, "leistung") == "11-12-LF"


def test_lp_relations():
    rels = _lp_relations(["BNE 2", "MB", "PG_01", "btv3", "BNE 2"])
    tokens = [r["target_bp_id"] for r in rels]
    # bloßes "MB" → Übersicht; "BNE 2"/"PG_01"/"btv3" → Aspekt; "BNE 2" dedupliziert
    assert tokens == ["BNE_02", "BP2016BW_ALLG_LP_MB", "PG_01", "BTV_03"]
    assert all(r["type"] == "references" for r in rels)


# ── Validierung ───────────────────────────────────────────────────────────────

def test_validate_ok():
    validate_fremdsprache_structure(_structure())  # darf nicht werfen


def test_validate_missing_fach():
    with pytest.raises(ValueError, match="fach.titel"):
        validate_fremdsprache_structure({"prozessbezogene_kompetenzbereiche": [], "jahrgangsstufen": []})


def test_validate_empty_pk():
    s = _structure()
    s["prozessbezogene_kompetenzbereiche"] = []
    with pytest.raises(ValueError, match="prozessbezogene"):
        validate_fremdsprache_structure(s)


def test_validate_band_non_int():
    s = _structure()
    s["jahrgangsstufen"][0]["klasse_von"] = "fünf"
    with pytest.raises(ValueError, match="klasse_von"):
        validate_fremdsprache_structure(s)


def test_validate_bereich_without_children():
    s = _structure()
    s["jahrgangsstufen"][0]["kompetenzbereiche"][1]["kompetenzen"] = []
    s["jahrgangsstufen"][0]["kompetenzbereiche"][1]["teilbereiche"] = []
    with pytest.raises(ValueError, match="weder Kompetenzen noch Teilbereiche"):
        validate_fremdsprache_structure(s)


# ── Chunking / Band-Erkennung ─────────────────────────────────────────────────

def _pdf_pages():
    dots = " . " * 25  # >60 Zeichen → TOC-Zeilen werden als Nicht-Überschrift verworfen
    return [
        "Deckblatt",
        f"2.  Prozessbezogene Kompetenzen{dots}16\nKlassen 5/6{dots}18",   # TOC
        "2.  Prozessbezogene Kompetenzen\n2.1\nSprachbewusstheit\nDie SuS reflektieren.",  # pk_start
        "2.3\nDigitale Kompetenz\nDie SuS nutzen digitale Mittel.",
        "3.\n Inhaltsbezogene Kompetenzen\n3.1\nKlassen 5/6\n3.1.1 Soziokulturelles",   # Band 3.1
        "3.1.3 Funktionale kommunikative Kompetenz",
        "Klassen 7/8\n3.2.1 Soziokulturelles",                             # Band 3.2
        "Klassen 11/12 (Leistungsfach)\n3.3.1 Soziokulturelles",           # Band mit Niveau
        "4.  Operatoren\nanalysieren",                                     # Ende Abschnitt 3
        "6.  Anhang",
    ]


def test_detect_chunks_boundaries():
    pk_text, bands = detect_fremdsprache_chunks(_pdf_pages())
    assert [b["nummer"] for b in bands] == ["3.1", "3.2", "3.3"]
    assert (bands[0]["klasse_von"], bands[0]["klasse_bis"], bands[0]["niveau"]) == (5, 6, None)
    assert (bands[1]["klasse_von"], bands[1]["klasse_bis"]) == (7, 8)
    assert (bands[2]["klasse_von"], bands[2]["klasse_bis"], bands[2]["niveau"]) == (11, 12, "leistung")


def test_detect_chunks_multigrade_band():
    """Mehrklassen-Band „Klassen 6/7/8" → von=6, bis=8 (nicht nur die ersten zwei Zahlen)."""
    pages = [
        "2.  Prozessbezogene Kompetenzen\n2.1\nSprachbewusstheit\nDie SuS.",
        "Klassen 6/7/8\n3.1.1 Soziokulturelles",
        "4.  Operatoren\nanalysieren",
    ]
    _, bands = detect_fremdsprache_chunks(pages)
    assert len(bands) == 1
    assert (bands[0]["klasse_von"], bands[0]["klasse_bis"]) == (6, 8)


def test_detect_chunks_text_separation():
    pk_text, bands = detect_fremdsprache_chunks(_pdf_pages())
    assert "Sprachbewusstheit" in pk_text and "Klassen" not in pk_text     # TOC + Bänder ausgeschlossen
    assert "Klassen 5/6" in bands[0]["text"] and "Klassen 7/8" not in bands[0]["text"]
    assert "Operatoren" not in bands[2]["text"]                            # Abschnitt 4 abgeschnitten


def test_detect_chunks_raises_without_section2():
    with pytest.raises(ValueError, match="nicht erkannt"):
        detect_fremdsprache_chunks(["nur Fließtext", "ohne Struktur"])


def test_detect_operator_chunk():
    chunk = detect_operator_chunk(_pdf_pages())
    assert chunk is not None
    assert "Operatoren" in chunk and "analysieren" in chunk
    assert "Anhang" not in chunk                          # gegen Abschnitt 6 abgegrenzt


def test_detect_operator_chunk_none():
    assert detect_operator_chunk(["kein", "operator", "abschnitt"]) is None


# ── Operatoren (Abschnitt 4) ──────────────────────────────────────────────────

def test_build_operator_nodes():
    ops = [
        {"operator": "(be-)nennen", "beschreibung": "Sachverhalte bezeichnen .", "afb": []},
        {"operator": "beschreiben, darstellen", "beschreibung": "Sachverhalte darstellen", "afb": ["I", "II"]},
        {"operator": "", "beschreibung": "leer", "afb": []},   # kein Titel → übersprungen
    ]
    nodes = build_operator_nodes(ops, base_bp_id=BASE, source_url="http://x")
    assert [n["bp_id"] for n in nodes] == [f"{BASE}_OP_01", f"{BASE}_OP_02"]

    n1 = nodes[0]
    assert n1["content_type"] == "operator" and n1["parent_bp_id"] == BASE
    assert n1["title"] == "nennen"                        # (be-)nennen → nennen
    assert n1["metadata"]["aliase"] == ["benennen"]
    assert n1["content"] == "Sachverhalte bezeichnen."    # _clean_text angewandt
    assert n1["metadata"]["afb"] == [] and n1["metadata"]["operator_nr"] == 1
    # composite content_hash: title|content|afb|aliase
    exp = "sha256:" + hashlib.sha256(
        "nennen|Sachverhalte bezeichnen.||benennen".encode("utf-8")).hexdigest()
    assert n1["content_hash"] == exp

    n2 = nodes[1]
    assert n2["title"] == "beschreiben" and n2["metadata"]["aliase"] == ["darstellen"]
    assert n2["metadata"]["afb"] == ["I", "II"]
    assert n2["bp_version"] == "2016.V2"


def test_operatoren_integrated_in_build():
    struct = _structure()
    struct["operatoren"] = [{"operator": "nennen", "beschreibung": "X", "afb": ["I"]}]
    nodes = build_fremdsprache_nodes(struct, fach_code="E1", suffix=".V2")
    ops = [n for n in nodes if n["content_type"] == "operator"]
    assert len(ops) == 1
    assert ops[0]["bp_id"] == f"{BASE}_OP_01" and ops[0]["parent_bp_id"] == BASE


def test_strip_json_fence():
    strip = _extract._strip_json_fence
    assert strip('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip('```\n{"a": 1}\n```') == '{"a": 1}'
    assert strip('{"a": 1}') == '{"a": 1}'
    assert strip('  {"a": 1}  ') == '{"a": 1}'


# ── Report ────────────────────────────────────────────────────────────────────

def test_report_counts_and_tree():
    report = render_fremdsprache_report(_structure())
    assert "Englisch als erste Fremdsprache — Extraktions-Review" in report
    assert "1 PK-Bereiche · 2 PK-Kompetenzen · 2 Jahrgangsstufen · 4 Leitideen/Bereiche · 3 IK-Kompetenzen" in report
    assert "3.1.1.1 Hör-/Hörsehverstehen" in report
    assert "Niveau: leistung" in report
