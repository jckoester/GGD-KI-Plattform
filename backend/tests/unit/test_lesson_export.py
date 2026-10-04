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
                sozialform="Partnerarbeit",
                methode="Fishbowl",
                material=["Folie 1"],
            ),
            ExportPhase(
                name="Erarbeitung",
                dauer_min=30,
                beschreibung="",
                prio="kern",
                sozialform="",
                methode="",
                material=[],
            ),
            ExportPhase(
                name="Sicherung",
                dauer_min=15,
                beschreibung="",
                prio="uebung",
                sozialform="Gruppenarbeit",
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
    assert "**Methode:** Fishbowl" in md
    assert "**Methode:** Tafelbild" in md


def test_markdown_sozialform_included():
    md = export_markdown(_make_export())
    assert "**Sozialform:** Partnerarbeit" in md
    assert "**Sozialform:** Gruppenarbeit" in md


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


class TestFormelnImStundenPdf:
    """Kompetenztitel koennen Formeln tragen (`… die Zahl \\(\\pi\\) …`).

    Angezeigt wird sonst `r.code`; faellt die Anzeige auf den Titel zurueck, stuende
    ohne Prärendern die TeX-Quelle im PDF.
    """

    async def _pdf_html(self, export) -> str:
        """Erzeugt das PDF und gibt die HTML zurueck, die weasyprint bekommen haette."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.planning.lesson_export import export_pdf

        gefangen = {}

        def _html(string=None, base_url=None):
            gefangen["html"] = string
            doc = MagicMock()
            doc.write_pdf = MagicMock(return_value=b"%PDF-fake")
            return doc

        with patch("weasyprint.HTML", new=_html), patch(
            "app.render.sidecar.render_math",
            new=AsyncMock(return_value='<svg class="mj"><path d="M0"/></svg>'),
        ):
            await export_pdf(export)
        return gefangen["html"]

    @pytest.mark.asyncio
    async def test_titel_mit_formel_wird_gerendert(self):
        html = await self._pdf_html(_make_export(refs=[
            # Ohne `code` faellt die Anzeige auf den Titel zurueck — der reale Fall.
            {"typ": "ik", "code": "", "titel": r"3.1.2(10) die Zahl \(\pi\) erklären",
             "partiell": False},
        ]))
        assert '<svg class="mj">' in html
        assert "\\(" not in html
        assert "erklären" in html

    @pytest.mark.asyncio
    async def test_code_hat_weiterhin_vorrang(self):
        html = await self._pdf_html(_make_export(refs=[
            {"typ": "ik", "code": "3.1.2", "titel": "Langer Titel", "partiell": False},
        ]))
        assert "3.1.2" in html
        assert "Langer Titel" not in html

    @pytest.mark.asyncio
    async def test_partiell_marker_bleibt(self):
        html = await self._pdf_html(_make_export(refs=[
            {"typ": "pk", "code": "K1", "titel": "Kommunikation", "partiell": True},
        ]))
        assert "[…]" in html

    @pytest.mark.asyncio
    async def test_titel_wird_escapet(self):
        """Das Template gibt mit `| safe` aus."""
        html = await self._pdf_html(_make_export(refs=[
            {"typ": "ik", "code": "", "titel": "<script>alert(1)</script>", "partiell": False},
        ]))
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    @pytest.mark.asyncio
    async def test_ohne_kompetenzen_kein_block(self):
        html = await self._pdf_html(_make_export(refs=[]))
        assert "Kompetenzen:" not in html


# ── Phasen ohne Dauer (0.13, P1) ──────────────────────────────────────────────

def _mit_skizze(**overrides):
    """Die Beispielstunde, deren Erarbeitung noch keine Minuten hat."""
    export = _make_export(**overrides)
    export.phasen[1].dauer_min = None
    return export


def test_markdown_phase_ohne_dauer_nur_mit_prio():
    md = export_markdown(_mit_skizze())
    assert "## Erarbeitung (Kern)" in md
    assert "None" not in md and "0′ ·" not in md


def test_markdown_zeitbudget_zaehlt_nur_gesetzte_dauern_und_nennt_den_rest():
    md = export_markdown(_mit_skizze())
    # 15 + 15, die Erarbeitung zählt nicht als 0 still mit
    assert "30′ geplant / 90′ verfügbar · 1 Phase ohne Dauer" in md


def test_markdown_ohne_fehlende_dauer_kein_zusatz():
    assert "ohne Dauer" not in export_markdown(_make_export())


def test_docx_mit_phase_ohne_dauer():
    import io

    from docx import Document

    from app.planning.lesson_export import export_docx

    doc = Document(io.BytesIO(export_docx(_mit_skizze())))
    zeiten = [zeile.cells[0].text for zeile in doc.tables[0].rows[1:]]
    # Die Skizze beginnt bei 15. Danach steht die Uhr: Wann die Sicherung beginnt, weiß
    # niemand. Bis 03.10.2026 stand hier „15–30′" — die fehlende Dauer als 0 gezählt.
    assert zeiten == ["0–15′", "ab 15′", "–"]
    budget = next(p.text for p in doc.paragraphs if p.text.startswith("Zeitbudget"))
    assert "30′ / 90′ verfügbar · 1 Phase ohne Dauer" in budget


@pytest.mark.asyncio
async def test_pdf_mit_phase_ohne_dauer():
    """Bis 0.13.0 rechnete `lesson.html` selbst und brach mit `int + None` ab (0.13.1)."""
    pytest.importorskip("weasyprint")
    from app.planning.lesson_export import export_pdf

    assert (await export_pdf(_mit_skizze()))[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_pdf_zeitspalte_und_budget_ohne_dauer():
    import re

    html = await TestFormelnImStundenPdf()._pdf_html(_mit_skizze())
    zellen = re.findall(r"<tr>\s*<td>([^<]*)</td>", html)
    # Dieselbe Regel wie im DOCX: nach der Skizze steht die Uhr.
    assert zellen == ["0–15′", "ab 15′", "–"]
    assert re.search(r"30′ geplant / 90′ verfügbar\s+· 1 Phase ohne Dauer", html)
