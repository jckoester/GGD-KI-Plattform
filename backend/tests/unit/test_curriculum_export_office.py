"""Unit-Tests: Curriculum als DOCX/ODT (0.39, Päckchen K, Plan F4). Nur mit Pandoc."""
import io
import json
import subprocess
import zipfile

import pytest

from app.context.curriculum_export import render_curriculum_office
from app.export import pandoc
from app.export.templates import vorlage

pytestmark = pytest.mark.skipif(not pandoc.pandoc_available(), reason="pandoc nicht installiert")

_U = "11111111-1111-1111-1111-111111111111"


def _baum(eintraege=None) -> dict:
    if eintraege is None:
        eintraege = [{
            "ik": [{"node_id": "ik1", "nr": "3.1.1", "partiell": True}],
            "pk": [{"node_id": "pk1", "pk_id": "PK_1"}],
            "konkretisierung": "- Zahlenstrahl\n- Formel $\\frac{a}{b}$",
            "hinweise": f"Siehe @[BNE](lp:{_U}) und #[3.1.2](ik:{_U})",
            "material": f"AB @[Bruchstreifen](node:{_U})",
        }]
    return {
        "title": "Mathematik Klasse 7",
        "metadata": {"schulart": "Gymnasium", "jahrgangsstufe": "7", "bp_version": "2016"},
        "kapitel": [{"title": "Rationale Zahlen", "metadata": {"std": "12"}, "lernsequenzen": [{
            "title": "Brüche vergleichen", "metadata": {"std": "4", "eintraege": eintraege},
            "ik_refs": [{"node_id": "ik1", "title": "3.1.1 die Zahl \\(\\pi\\) als Verhältnis"}],
            "pk_refs": [{"node_id": "pk1", "title": "2.1 Begründen"}],
        }]}],
    }


async def _docx(baum) -> bytes:
    return await render_curriculum_office(None, baum, "docx", reference_doc=vorlage("docx"))


def _klartext(data: bytes) -> str:
    return subprocess.run(["pandoc", "-f", "docx", "-t", "plain", "--wrap=none"], input=data,
                          capture_output=True, check=True).stdout.decode()


@pytest.mark.parametrize("fmt", ["docx", "odt"])
async def test_liefert_datei(fmt):
    data = await render_curriculum_office(None, _baum(), fmt, reference_doc=vorlage(fmt))
    assert data[:2] == b"PK"


async def test_aufbau_wie_im_pdf():
    text = _klartext(await _docx(_baum()))
    for erwartet in ("Mathematik Klasse 7", "Gymnasium | Kl. 7 | BP 2016", "Rationale Zahlen (12 Std.)",
                     "Brüche vergleichen (4 Std.)", "Konkretisierung", "Hinweise & Material",
                     "2.1 Begründen", "(T)", "Zahlenstrahl", "BNE", "3.1.2", "Bruchstreifen"):
        assert erwartet in text, erwartet
    assert "lp:" not in text and "node:" not in text, "Verweise erscheinen mit Beschriftung, ohne Kennung"


async def test_formeln_aus_titel_und_konkretisierung_als_word_formel():
    xml = zipfile.ZipFile(io.BytesIO(await _docx(_baum()))).read("word/document.xml").decode()
    assert xml.count("<m:oMath>") == 2   # \(\pi\) im IK-Titel, \frac in der Konkretisierung


async def test_lernsequenz_ohne_eintraege():
    assert "(keine Einträge)" in _klartext(await _docx(_baum(eintraege=[])))


async def test_spaltenbreiten_wie_im_pdf():
    ast = json.loads(subprocess.run(["pandoc", "-f", "docx", "-t", "json"], input=await _docx(_baum()),
                                    capture_output=True, check=True).stdout)
    t = next(b for b in ast["blocks"] if b["t"] == "Table")
    breiten = [s[1]["c"] for s in t["c"][2]]
    assert [round(b / sum(breiten), 2) for b in breiten] == [0.24, 0.28, 0.26, 0.22]
