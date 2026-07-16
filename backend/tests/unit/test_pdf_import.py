"""Unit-Tests für das PDF→JSONL-Import-Gerüst (KS-Plan C3/C4, Schritt 1).

Lädt die Repo-Root-``scripts/``-Module isoliert (vgl. test_bildungsplan_editions):
``nodes.py`` importiert aus ``scripts.scraper.parsers`` → Repo-Root muss auf dem Pfad sein;
der ``scripts*``-Zustand in ``sys.modules`` wird um den Import herum wiederhergestellt.
"""
import hashlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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


_pdf_text = _load_isolated("_pdf_text_uut", "scripts/pdf_import/pdf_text.py")
_nodes = _load_isolated("_pdf_nodes_uut", "scripts/pdf_import/nodes.py", need_repo_on_path=True)

parse_page_spec = _pdf_text.parse_page_spec
load_pdf_bytes = _pdf_text.load_pdf_bytes
extract_text = _pdf_text.extract_text
build_node = _nodes.build_node


# ── parse_page_spec ───────────────────────────────────────────────────────────

def test_page_spec_none_and_empty():
    assert parse_page_spec(None) is None
    assert parse_page_spec("") is None
    assert parse_page_spec("  ") is None


def test_page_spec_single_and_range_1indexed_to_0indexed():
    assert parse_page_spec("1") == {0}
    assert parse_page_spec("3") == {2}
    assert parse_page_spec("1-5") == {0, 1, 2, 3, 4}


def test_page_spec_mixed():
    assert parse_page_spec("3-8,10") == {2, 3, 4, 5, 6, 7, 9}


def test_page_spec_invalid():
    with pytest.raises(ValueError):
        parse_page_spec("0")
    with pytest.raises(ValueError):
        parse_page_spec("5-3")


# ── load_pdf_bytes ────────────────────────────────────────────────────────────

def test_load_pdf_bytes_local(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-fake")
    assert load_pdf_bytes(str(p)) == b"%PDF-fake"


def test_load_pdf_bytes_url():
    resp = MagicMock()
    resp.content = b"%PDF-remote"
    resp.raise_for_status = MagicMock()
    with patch.object(_pdf_text.httpx, "get", return_value=resp) as mock_get:
        data = load_pdf_bytes("https://example.de/bp.pdf")
    assert data == b"%PDF-remote"
    assert mock_get.call_args.args[0] == "https://example.de/bp.pdf"


# ── extract_text ──────────────────────────────────────────────────────────────

def test_extract_text_passes_page_numbers():
    with patch.object(_pdf_text, "_pdf_extract_text", return_value="  Seitentext  ") as mock_ex:
        out = extract_text(b"%PDF", pages={2, 3})
    assert out == "Seitentext"
    assert mock_ex.call_args.kwargs["page_numbers"] == {2, 3}


def test_extract_text_empty_raises():
    with patch.object(_pdf_text, "_pdf_extract_text", return_value="   "):
        with pytest.raises(ValueError):
            extract_text(b"%PDF")


def test_extract_text_error_wrapped():
    with patch.object(_pdf_text, "_pdf_extract_text", side_effect=RuntimeError("kaputt")):
        with pytest.raises(ValueError, match="PDF konnte nicht gelesen werden"):
            extract_text(b"not a pdf")


# ── build_node ────────────────────────────────────────────────────────────────

def test_build_node_format_and_hash():
    node = build_node(
        bp_id="BP2016BW_ALLG_LP_LFDB_BAUSTEIN_01",
        content_type="lfdb_baustein",
        title="Baustein 1",
        content="Inhalt des Bausteins",
        parent_bp_id="BP2016BW_ALLG_LP_LFDB",
        source_url="https://example.de/lfdb.pdf",
        extra_metadata={"lfdb_kind": "baustein"},
    )
    assert node["content_type"] == "lfdb_baustein"
    assert node["parent_bp_id"] == "BP2016BW_ALLG_LP_LFDB"
    assert node["bp_version"] == "2016"  # aus bp_id abgeleitet
    assert node["metadata"]["lfdb_kind"] == "baustein"
    assert node["metadata"]["bp_id"] == node["bp_id"]
    # content_hash identisch zum Scraper (sha256 des content, 'sha256:'-Präfix)
    expected = "sha256:" + hashlib.sha256("Inhalt des Bausteins".encode("utf-8")).hexdigest()
    assert node["content_hash"] == expected


def test_build_node_defaults():
    node = build_node(
        bp_id="BP2016BW_ALLG_GYM_E1.V2_IK_5-6_01_01",
        content_type="ik_kompetenz",
        title="IK",
        content="x",
    )
    assert node["relations"] == []
    assert node["niveau"] == "regulär"
    assert node["visibility"] == "global"
    assert node["type"] == "knowledge"
    assert node["bp_version"] == "2016.V2"


# ── LLM-Struktur-Extraktion (Schritt 2) ──────────────────────────────────────

_extract = _load_isolated("_pdf_extract_uut", "scripts/pdf_import/extract.py")
extract_lfdb_structure = _extract.extract_lfdb_structure
validate_lfdb_structure = _extract.validate_lfdb_structure


def _valid_structure():
    return {
        "bausteine": [
            {
                "nummer": 1,
                "titel": "Identität und Pluralismus",
                "themenbloecke": [
                    {
                        "titel": "Mit Pluralismus umgehen",
                        "leitperspektiven": ["BTV", "PG"],
                        "kompetenzen": [
                            {
                                "leitfrage": "Was macht mich aus?",
                                "kompetenz": "Die SuS können Aspekte der eigenen Identität erkennen.",
                                "impulse_inhalte": "Neigungen, Interessen, …",
                            }
                        ],
                    }
                ],
            }
        ]
    }


def test_validate_ok():
    validate_lfdb_structure(_valid_structure())  # wirft nicht


def test_validate_rejects_missing_bausteine():
    with pytest.raises(ValueError):
        validate_lfdb_structure({})
    with pytest.raises(ValueError):
        validate_lfdb_structure({"bausteine": []})


def test_validate_rejects_themenblock_without_kompetenz():
    s = _valid_structure()
    s["bausteine"][0]["themenbloecke"][0]["kompetenzen"] = []
    with pytest.raises(ValueError):
        validate_lfdb_structure(s)


def _mock_llm_response(content: str):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={"choices": [{"message": {"content": content}}]})
    return resp


def test_extract_calls_proxy_and_returns_structure():
    import json as _json
    captured = {}

    def _post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _mock_llm_response(_json.dumps(_valid_structure()))

    with patch.object(_extract.httpx, "post", side_effect=_post):
        data = extract_lfdb_structure(
            "roher PDF-Text", model="claude-opus-4-8",
            proxy_url="http://proxy:4000/", api_key="sk-x",
        )
    assert data["bausteine"][0]["titel"] == "Identität und Pluralismus"
    assert captured["url"] == "http://proxy:4000/chat/completions"
    assert captured["json"]["model"] == "claude-opus-4-8"
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert captured["headers"]["Authorization"] == "Bearer sk-x"


def test_extract_invalid_json_raises():
    with patch.object(_extract.httpx, "post", return_value=_mock_llm_response("kein json")):
        with pytest.raises(ValueError, match="kein gültiges JSON"):
            extract_lfdb_structure("t", proxy_url="http://p", api_key="k")


def test_extract_structurally_invalid_raises():
    import json as _json
    bad = _mock_llm_response(_json.dumps({"bausteine": []}))
    with patch.object(_extract.httpx, "post", return_value=bad):
        with pytest.raises(ValueError):
            extract_lfdb_structure("t", proxy_url="http://p", api_key="k")


# ── LFDB-Assembler (Schritt 3) ───────────────────────────────────────────────

_lfdb = _load_isolated("_pdf_lfdb_uut", "scripts/pdf_import/lfdb.py", need_repo_on_path=True)
build_lfdb_nodes = _lfdb.build_lfdb_nodes
render_lfdb_report = _lfdb.render_lfdb_report


def test_build_lfdb_nodes_hierarchy_and_bpids():
    nodes = build_lfdb_nodes(_valid_structure(), source_url="https://x/lfdb.pdf")
    by_type = {}
    for n in nodes:
        by_type.setdefault(n["content_type"], []).append(n)
    assert len(by_type["lfdb_baustein"]) == 1
    assert len(by_type["lfdb_themenblock"]) == 1
    assert len(by_type["lfdb_kompetenz"]) == 1

    b = by_type["lfdb_baustein"][0]
    t = by_type["lfdb_themenblock"][0]
    k = by_type["lfdb_kompetenz"][0]
    assert b["bp_id"] == "BP2016BW_ALLG_LP_LFDB_B1"
    assert t["bp_id"] == "BP2016BW_ALLG_LP_LFDB_B1_T1"
    assert k["bp_id"] == "BP2016BW_ALLG_LP_LFDB_B1_T1_K1"
    # Parent-Kette
    assert b["parent_bp_id"] == "BP2016BW_ALLG_LP_LFDB"
    assert t["parent_bp_id"] == b["bp_id"]
    assert k["parent_bp_id"] == t["bp_id"]
    # Themenblock trägt Leitperspektiven
    assert t["metadata"]["leitperspektiven"] == ["BTV", "PG"]
    # Kompetenz: Titel = Leitfrage, content = Kompetenz + Impulse
    assert k["title"] == "Was macht mich aus?"
    assert "Die SuS können" in k["content"]
    assert "Impulse und Inhalte" in k["content"]


def test_build_lfdb_nodes_fallback_title_and_nummer():
    s = {"bausteine": [{"titel": "X", "themenbloecke": [
        {"titel": "T", "leitperspektiven": [], "kompetenzen": [
            {"leitfrage": "", "kompetenz": "Die SuS können Y.", "impulse_inhalte": ""}]}]}]}
    nodes = build_lfdb_nodes(s)
    b = next(n for n in nodes if n["content_type"] == "lfdb_baustein")
    k = next(n for n in nodes if n["content_type"] == "lfdb_kompetenz")
    assert b["bp_id"] == "BP2016BW_ALLG_LP_LFDB_B1"   # nummer aus Index
    assert k["title"] == "Die SuS können Y."           # Titel-Fallback auf Kompetenz
    assert "Impulse" not in k["content"]               # kein Impulse-Abschnitt wenn leer


def test_render_lfdb_report():
    report = render_lfdb_report(_valid_structure())
    assert "# LFDB" in report
    assert "1 Bausteine · 1 Themenblöcke · 1 Kompetenzen" in report
    assert "Mit Pluralismus umgehen" in report
    assert "Leitperspektiven: BTV, PG" in report
