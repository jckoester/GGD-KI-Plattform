"""Export eines Jahresverlaufsplans (BD Teil B, Schritt 7): Aufbereitung, PDF und DOCX."""
import io
import zipfile
from datetime import date

import pytest

from app.context.verlaufsplan import kompakt
from app.context.verlaufsplan_export import aufbereiten, dateiname, render_office, render_pdf
from app.export import pandoc

from tests.unit.test_verlaufsplan_kompakt import _voll


def _k(**kw):
    return kompakt(_voll(**kw), titel_alt={"sX": "Alte Sequenz"}, kapitel_alt={"sX": "Altes Kapitel"})


def test_aufbereiten():
    p = aufbereiten(_k(), heute=date(2026, 11, 26))
    assert p["stand"] == "Entwurf, Stand 26.11.2026" and p["entwurf"]
    assert p["meta"] == "Mathematik · Klasse 9 · Schuljahr 2025/26 · 4 Wochenstunden · sequenzgenau"
    assert p["summe"] == "37 Unterrichtswochen, 3 verplant (davon 1 Puffer), 34 frei"
    assert p["bilanz_hinweise"] == []
    a, puffer = p["zeilen"]
    assert a == {"nr": 1, "thema": "Strahlen", "puffer": False, "wochen": 2, "woche": "Woche 1–2", "tage": "15.09.–26.09.", "zeitraum": "Woche 1–2, 15.09.–26.09.",
                 "bezug": "Strahlensätze (Ähnlichkeit); Alte Sequenz (Altes Kapitel) – nicht mehr im Curriculum",
                 "hinweise": "", "notiz": "GeoGebra"}
    assert (puffer["bezug"], puffer["hinweise"], puffer["puffer"]) == ("Puffer", "endet vor den Herbstferien", True)
    assert p["bilanz"] == [{"titel": "Ähnlichkeit", "fremd": False, "soll": "12", "geplant": "8", "wochen": "2"}]
    assert p["kapitel_ohne_abschnitt"] == ["Pythagoras"]


def test_beschlossen_ohne_kalender_und_dateiname():
    k = _k(status="active", beschlossen_am="2025-10-03", lage=None, planungsart="kapitel",
           abschnitte=[{"titel": "", "wochen": 8, "kapitel_ids": ["k2"]}])
    p = aufbereiten(k)
    assert p["stand"] == "Beschlossen am 03.10.2025" and p["summe"] is None and "Kalender" in p["hinweis"]
    assert p["zeilen"][0]["zeitraum"] == "" and p["zeilen"][0]["thema"] == "ohne Thema"
    assert p["zeilen"][0]["hinweise"] == "länger als 6 Wochen"
    assert dateiname(k, "pdf") == "jahresverlaufsplan_Mathematik_9_2025-26.pdf"
    # Nur ASCII im Header (Latin-1): Umlaute umschreiben, Fremdes zerlegen
    assert dateiname({**k, "fach": "Ökonomie/Wirtschaft"}, "pdf") == "jahresverlaufsplan_OekonomieWirtschaft_9_2025-26.pdf"
    assert dateiname({**k, "fach": "Čeština"}, "docx").startswith("jahresverlaufsplan_Cestina_")


def test_ohne_titel_steht_der_vermerk_nur_einmal():
    k = kompakt(_voll())                                   # sX ohne alten Titel
    p = aufbereiten(k)
    assert p["zeilen"][0]["bezug"] == "Strahlensätze (Ähnlichkeit); nicht mehr im Curriculum"
    v = _voll()
    v["lage"]["kapitel"].append({"kapitel_id": "kWeg", "titel": None, "soll": None, "geplant": 4.0, "wochen": 1.0})
    v["planungsart"] = "kapitel"
    b = aufbereiten(kompakt(v))["bilanz"][1]
    assert (b["titel"], b["fremd"]) == ("nicht mehr im Curriculum", False)


def test_hinweise_zur_bilanz():
    v = _voll(wochenstunden=None)
    v["curricula"] = [{**v["curricula"][0], "band": True}]
    assert aufbereiten(kompakt(v))["bilanz_hinweise"] == [
        "Das Curriculum gilt für mehrere Stufen; „Soll“ ist die Stundenzahl für das ganze Band.",
        "Ohne Wochenstunden im Curriculum zählt die Bilanz nur Wochen."]


async def test_pdf():
    pdf = await render_pdf(_k())
    assert pdf.startswith(b"%PDF")


@pytest.mark.skipif(not pandoc.pandoc_available(), reason="pandoc nicht installiert")
async def test_docx_quer_mit_tabellen():
    from app.export.templates import vorlage

    daten = await render_office(None, _k(), "docx", reference_doc=vorlage("docx"))
    xml = zipfile.ZipFile(io.BytesIO(daten)).read("word/document.xml").decode()
    assert 'w:orient="landscape"' in xml
    assert "Strahlensätze (Ähnlichkeit)" in xml and "Stunden je Kapitel" in xml and "GeoGebra" in xml
    assert xml.count("<w:tbl>") == 2


@pytest.mark.skipif(not pandoc.pandoc_available(), reason="pandoc nicht installiert")
async def test_docx_notiz_als_klartext():
    """Die Notiz ist ein einzeiliges Feld: kein Markdown, nichts verschwindet."""
    v = _voll()
    v["abschnitte"][0]["notiz"] = "# Wichtig: <Name> fragen, $x^2$"
    daten = await render_office(None, kompakt(v), "docx")
    xml = zipfile.ZipFile(io.BytesIO(daten)).read("word/document.xml").decode()
    assert "# Wichtig: &lt;Name&gt; fragen, $x^2$" in xml and "Heading1" not in xml.split("Strahlen")[1]


def test_bilanz_auf_eigener_seite_pdf():
    import weasyprint

    from app.context.verlaufsplan_export import TEMPLATES, pdf_html

    seiten = weasyprint.HTML(string=pdf_html(_k()), base_url=TEMPLATES).render().pages
    assert len(seiten) == 2


@pytest.mark.skipif(not pandoc.pandoc_available(), reason="pandoc nicht installiert")
async def test_bilanz_auf_eigener_seite_docx_und_odt():
    docx = zipfile.ZipFile(io.BytesIO(await render_office(None, _k(), "docx"))).read("word/document.xml").decode()
    assert docx.index('w:br w:type="page"') < docx.index("Stunden je Kapitel")
    odt = zipfile.ZipFile(io.BytesIO(await render_office(None, _k(), "odt"))).read("content.xml").decode()
    # Pandoc nennt die Vorlage nur; definiert wird sie in der Nachbearbeitung
    assert 'style:name="Pagebreak"' in odt and 'fo:break-after="page"' in odt
    assert odt.index('text:style-name="Pagebreak"') < odt.index("Stunden je Kapitel")
