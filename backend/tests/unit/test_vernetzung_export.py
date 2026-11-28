"""PDF der Vernetzung (BE, Teil A, Schritt 7): Prüfung der SVGs aus dem Browser, HTML, Endpunkt.

`fixtures/vernetzung_zeitachse.svg` stammt aus `frontend/src/lib/zeitachse_svg.js` (eine Stufe
Mathematik mit drei Spuren) — so prüft der Test, was die Seite tatsächlich schickt.
"""
import os
from datetime import date
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.context import vernetzung_export as ex
from app.context.vernetzung_router import router

SVG = (Path(__file__).parent / "fixtures" / "vernetzung_zeitachse.svg").read_text()
LEHRKRAFT = JwtPayload(sub="be-lk", roles=["teacher"], grade=None, jti="j", iat=0, exp=9999999999)
SCHUELER = JwtPayload(sub="be-s", roles=["student"], grade="8", jti="j", iat=0, exp=9999999999)


def _anfrage(**extra):
    return {
        "fach": "Mathematik", "titel": "Vernetzung der Fächer: Mathematik", "untertitel": "Schuljahr 2026/27",
        "seiten": [{"titel": "Klasse 8 · 2026/27", "svg": SVG, "kuerzel": [{"kuerzel": "PH 1", "titel": "Dichte"}]}],
        "liste": [{"titel": "Klasse 8", "kapitel": [
            {"titel": "Lineare Funktionen", "lage": "Kl. 8, KW 37–45", "zeilen": ["Absprache — Physik: Bewegungen <b>"]}]}],
        "ohne_lage": ["Körper"], **extra,
    }


def test_svg_aus_dem_browser_besteht_die_pruefung():
    ex.pruefen(ex.PdfAnfrage.model_validate(_anfrage()))


@pytest.mark.parametrize("svg, teil", [
    ('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "<script>"),
    ('<svg xmlns="http://www.w3.org/2000/svg"><image href="https://x.example/a.png"/></svg>', "nach außen"),
    ("<svg><rect/></svg>", "xmlns"),
])
def test_fremdes_svg_wird_abgewiesen(svg, teil):
    a = ex.PdfAnfrage.model_validate(_anfrage(seiten=[{"titel": "Klasse 8", "svg": svg}]))
    with pytest.raises(ex.UngueltigesSvg, match="Klasse 8"):
        ex.pruefen(a)
    try:
        ex.pruefen(a)
    except ex.UngueltigesSvg as e:
        assert teil in str(e)


def test_html_bild_als_daten_uri_und_text_maskiert():
    html = ex.pdf_html(ex.PdfAnfrage.model_validate(_anfrage()), heute=date(2026, 11, 28))
    assert 'src="data:image/svg+xml;base64,' in html
    assert "<svg" not in html.split("<body>", 1)[1].split('class="legende"')[0]   # kein eingebettetes SVG-Markup
    assert "Bewegungen &lt;b&gt;" in html and "Stand 28.11.2026" in html
    assert "<b>PH 1</b> Dichte" in html and "Nicht im Jahresverlaufsplan" in html
    assert ex.dateiname("Ästhetik/Kunst", date(2026, 11, 28)) == "vernetzung_AesthetikKunst_2026-11-28.pdf"


def _client(user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_endpunkt_pdf_und_abweisungen():
    c = _client(LEHRKRAFT)
    r = c.post("/context/vernetzung/pdf", json=_anfrage())
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert 'filename="vernetzung_Mathematik_' in r.headers["content-disposition"]
    r = c.post("/context/vernetzung/pdf", json=_anfrage(seiten=[{"titel": "Klasse 8", "svg": "<svg/>"}]))
    assert r.status_code == 422 and "Klasse 8" in r.json()["detail"]
    assert c.post("/context/vernetzung/pdf", json=_anfrage(seiten=[])).status_code == 422
    assert _client(SCHUELER).post("/context/vernetzung/pdf", json=_anfrage()).status_code == 403
