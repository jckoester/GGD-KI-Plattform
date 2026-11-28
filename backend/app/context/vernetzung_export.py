"""PDF der Vernetzung (Päckchen BE, Teil A, Schritt 7; F9, F14 a).

Die Seite baut je Stufe ein SVG mit derselben Anordnung wie die Ansicht (`frontend/src/lib/
zeitachse_svg.js`) und dazu die Liste als Text. Hier wird jedes SVG mit `pruefe_svg` geprüft —
es kommt vom Browser, also von außen — und alles mit weasyprint auf A4 hoch gesetzt, mit der
Kopfzeile der Schule wie die übrigen PDF-Exporte. Das SVG geht als Bild-Daten-URI ins HTML: So
bleibt es ein Bild und kann im Dokument nichts nachladen.
"""
from __future__ import annotations

import base64
import os
import unicodedata
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.context.svg_pruefung import pruefe_svg

TEMPLATES = os.path.join(os.path.dirname(__file__), "templates")


class Kuerzel(BaseModel):
    kuerzel: str = Field(max_length=20)
    titel: Optional[str] = Field(default=None, max_length=300)


class Seite(BaseModel):
    titel: str = Field(max_length=300)
    svg: str = Field(max_length=400_000)
    kuerzel: list[Kuerzel] = Field(default_factory=list, max_length=300)
    #: Anmerkungen zur Stufe (kein Curriculum, Fassungswechsel, kein Kalender) — Liste über der Zeichnung
    hinweise: list[str] = Field(default_factory=list, max_length=10)


class ListeKapitel(BaseModel):
    titel: str = Field(max_length=300)
    lage: str = Field(default="", max_length=300)
    zeilen: list[str] = Field(default_factory=list, max_length=200)


class ListeStufe(BaseModel):
    titel: str = Field(max_length=300)
    kapitel: list[ListeKapitel] = Field(default_factory=list, max_length=200)


class PdfAnfrage(BaseModel):
    fach: str = Field(max_length=100)
    titel: str = Field(max_length=200)
    untertitel: str = Field(default="", max_length=600)
    seiten: list[Seite] = Field(min_length=1, max_length=14)
    liste: list[ListeStufe] = Field(default_factory=list, max_length=14)
    ohne_lage: list[str] = Field(default_factory=list, max_length=300)


class UngueltigesSvg(ValueError):
    pass


def pruefen(anfrage: PdfAnfrage) -> None:
    """Jede Zeile der Liste höchstens 2.000 Zeichen; jedes SVG muss `pruefe_svg` bestehen."""
    for s in anfrage.seiten:
        if any(len(h) > 300 for h in s.hinweise):
            raise UngueltigesSvg(f"{s.titel}: eine Anmerkung ist zu lang")
    for stufe in anfrage.liste:
        for k in stufe.kapitel:
            if any(len(z) > 2000 for z in k.zeilen):
                raise UngueltigesSvg(f"{stufe.titel}: eine Zeile ist zu lang")
    for s in anfrage.seiten:
        if (grund := pruefe_svg(s.svg)) is not None:
            raise UngueltigesSvg(f"{s.titel}: Die Zeichnung {grund}.")


# Legende als kleine, feste Zeichnungen (nicht von außen)
def _linie(farbe: str, breite: float, strich: Optional[str] = None) -> str:
    strich_attr = f' stroke-dasharray="{strich}"' if strich else ""
    s = (f'<svg xmlns="http://www.w3.org/2000/svg" width="30" height="8"><path d="M1,4 L29,4" stroke="{farbe}" '
         f'stroke-width="{breite}"{strich_attr}/></svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(s.encode()).decode()


LEGENDE = [
    (_linie("#1a1a1a", 2.4), "Absprache"),
    (_linie("#b3261e", 2.4), "Absprache laut Jahresverlaufsplänen nicht eingehalten"),
    (_linie("#555555", 1.2, "5 4"), "Querverweis des Bildungsplans"),
    (_linie("#555555", 0.8, "1 3"), "über einen ganzen Bereich"),
]


def pdf_html(anfrage: PdfAnfrage, *, heute: Optional[date] = None) -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    from app.config import settings

    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    seiten = [{"titel": s.titel, "kuerzel": [k.model_dump() for k in s.kuerzel], "hinweise": s.hinweise,
               "bild": "data:image/svg+xml;base64," + base64.b64encode(s.svg.encode()).decode()}
              for s in anfrage.seiten]
    return env.get_template("vernetzung_pdf.html").render(
        schule=settings.export_school_name or "", titel=anfrage.titel, untertitel=anfrage.untertitel,
        stand=(heute or date.today()).strftime("%d.%m.%Y"), legende=LEGENDE, seiten=seiten,
        liste=[s.model_dump() for s in anfrage.liste], ohne_lage=anfrage.ohne_lage)


async def render_pdf(anfrage: PdfAnfrage) -> bytes:
    import asyncio

    import weasyprint

    html = pdf_html(anfrage)
    return await asyncio.to_thread(lambda: weasyprint.HTML(string=html, base_url=TEMPLATES).write_pdf())


_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})


def dateiname(fach: str, heute: Optional[date] = None) -> str:
    """Nur ASCII (Latin-1-Header, wie beim Jahresverlaufsplan)."""
    roh = unicodedata.normalize("NFKD", (fach or "fach").translate(_UMLAUTE))
    name = "".join(c for c in roh.encode("ascii", "ignore").decode() if c.isalnum()) or "fach"
    return f"vernetzung_{name}_{(heute or date.today()).isoformat()}.pdf"
