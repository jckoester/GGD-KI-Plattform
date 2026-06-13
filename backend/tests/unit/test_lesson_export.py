"""Tests für lesson_export.py: export_markdown (golden), PDF/DOCX (smoke)."""

import pytest
from app.planning.lesson_export import ExportPhase, LessonExport, export_markdown, _slugify


def _make_export(**overrides) -> LessonExport:
    defaults = dict(
        titel="Einführung in die Fotosynthese",
        titel_slug="einfuehrung-in-die-fotosynthese",
        stundenziel="SuS können die Grundgleichung der Fotosynthese erklären.",
        gruppe="10b",
        gruppe_slug="10b",
        datum="2026-09-15",
        start_period=3,
        periods=2,
        verfuegbare_min=90,
        ue_titel="Stoffwechsel",
        phasen=[
            ExportPhase(
                name="Einstieg",
                dauer_min=15,
                beschreibung="Aktivierung Vorwissen",
                prio="kern",
                methode="Fishbowl",
                material=["Folie 1"],
            ),
            ExportPhase(
                name="Erarbeitung",
                dauer_min=30,
                beschreibung="",
                prio="kern",
                methode="",
                material=[],
            ),
            ExportPhase(
                name="Sicherung",
                dauer_min=15,
                beschreibung="",
                prio="uebung",
                methode="Tafelbild",
                material=["AB 1", "AB 2"],
            ),
        ],
        refs=[
            {"typ": "ik", "code": "3.1.2", "titel": "Fotosynthese verstehen", "partiell": False},
            {"typ": "pk", "code": "K1", "titel": "Kommunikation", "partiell": True},
        ],
    )
    defaults.update(overrides)
    return LessonExport(**defaults)


# ── Slugify ───────────────────────────────────────────────────────────────────


def test_slugify_basic():
    assert _slugify("Einstieg") == "einstieg"


def test_slugify_umlauts():
    assert _slugify("Übungsaufgaben") == "uebungsaufgaben"
    assert _slugify("Käfig & Öl") == "kaefig-oel"


def test_slugify_special_chars():
    assert _slugify("Test: Aufgabe 1!") == "test-aufgabe-1"


def test_slugify_empty():
    assert _slugify("") == "stunde"


def test_slugify_long():
    s = "a" * 100
    assert len(_slugify(s)) <= 60


# ── Markdown-Golden-File ──────────────────────────────────────────────────────


EXPECTED_MD_FRONTMATTER = """\
---
titel: Einführung in die Fotosynthese
datum: 2026-09-15
gruppe: 10b
ue: Stoffwechsel
verfuegbar_min: 90
kompetenzen: [3.1.2, K1[…]]
---"""


def test_markdown_frontmatter():
    md = export_markdown(_make_export())
    for line in EXPECTED_MD_FRONTMATTER.splitlines():
        assert line in md, f"Erwartete Zeile nicht gefunden: {line!r}"


def test_markdown_stundenziel():
    md = export_markdown(_make_export())
    assert "**Stundenziel:**" in md
    assert "SuS können die Grundgleichung" in md


def test_markdown_phase_headers():
    md = export_markdown(_make_export())
    assert "## Einstieg (15′ · Kern)" in md
    assert "## Erarbeitung (30′ · Kern)" in md
    assert "## Sicherung (15′ · Übung)" in md


def test_markdown_zeitbudget_no_ueberhang():
    md = export_markdown(_make_export())
    assert "60′ geplant / 90′ verfügbar" in md
    assert "Überhang" not in md


def test_markdown_zeitbudget_with_ueberhang():
    export = _make_export(verfuegbare_min=50)
    md = export_markdown(export)
    assert "Überhang" in md
    assert "+10′" in md


def test_markdown_methode_included():
    md = export_markdown(_make_export())
    assert "**Methode/Sozialform:** Fishbowl" in md
    assert "**Methode/Sozialform:** Tafelbild" in md


def test_markdown_material_included():
    md = export_markdown(_make_export())
    assert "**Material:** Folie 1" in md
    assert "**Material:** AB 1" in md
    assert "**Material:** AB 2" in md


def test_markdown_empty_phase_no_methode():
    md = export_markdown(_make_export())
    # "Erarbeitung" hat keine Methode → kein Material-/Methode-Block für diese Phase
    lines = md.splitlines()
    erarbeitung_idx = next(i for i, l in enumerate(lines) if "Erarbeitung" in l)
    sicherung_idx = next(i for i, l in enumerate(lines) if "## Sicherung" in l)
    between = lines[erarbeitung_idx + 1 : sicherung_idx]
    assert not any("**Methode" in l or "**Material" in l for l in between)


def test_markdown_no_refs_no_kompetenzen_key():
    export = _make_export(refs=[])
    md = export_markdown(export)
    assert "kompetenzen:" not in md


def test_markdown_partiell_suffix():
    md = export_markdown(_make_export())
    assert "K1[…]" in md


# ── DOCX smoke ────────────────────────────────────────────────────────────────


def test_export_docx_returns_bytes():
    pytest.importorskip("docx")
    from app.planning.lesson_export import export_docx

    result = export_docx(_make_export())
    assert isinstance(result, bytes)
    assert len(result) > 1000  # non-trivial docx
    # DOCX magic bytes (PK zip header)
    assert result[:2] == b"PK"


def test_export_docx_empty_phasen():
    pytest.importorskip("docx")
    from app.planning.lesson_export import export_docx

    export = _make_export(phasen=[])
    result = export_docx(export)
    assert isinstance(result, bytes)
    assert result[:2] == b"PK"


# ── PDF smoke ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_pdf_returns_bytes():
    pytest.importorskip("weasyprint")
    from app.planning.lesson_export import export_pdf

    result = await export_pdf(_make_export())
    assert isinstance(result, bytes)
    assert result[:4] == b"%PDF"
