"""Strukturformeln (0.30, Päckchen AH, ```smiles): Lesen, Elektronenpaare, Zeichnen."""
import asyncio
import xml.etree.ElementTree as ET

import pytest
from rdkit import Chem

from app.render import service
from app.render.errors import RenderError
from app.render.smiles import (
    Molekuel, SmilesError, freie_paare, lies, render_smiles, setze, zeichne,
)


# ── Lesen ────────────────────────────────────────────────────────────────────

def test_reihe_mit_operatoren_und_namen():
    block = lies("Essigsäure: CC(=O)O + Ethanol: OCC <=> CC(=O)OCC + O")
    teile = block.reihen[0].teile
    assert [t if isinstance(t, str) else t.smiles for t in teile] == [
        "CC(=O)O", "plus", "OCC", "gleichgewicht", "CC(=O)OCC", "plus", "O"]
    assert teile[0].name == "Essigsäure" and teile[4].name is None
    assert block.darstellung == "valenzstrich", "Vorgabe seit 03.11.2026"


def test_ladung_in_klammern_ist_kein_operator():
    teile = lies("[NH3+]CC(=O)[O-]").reihen[0].teile
    assert len(teile) == 1 and teile[0].smiles == "[NH3+]CC(=O)[O-]"


def test_mesomerie_unicode_und_mehrere_reihen():
    block = lies("darstellung: skelett\n[O-]c1ccccc1 ↔ O=C1C=CC=C[CH-]1\nO → O")
    assert block.darstellung == "skelett"
    assert block.reihen[0].teile[1] == "mesomerie"
    assert block.reihen[1].teile[1] == "pfeil"


def test_name_mit_leerzeichen():
    teile = lies("Essigsäure Ethylester: CC(=O)OCC").reihen[0].teile
    assert teile[0].name == "Essigsäure Ethylester"


@pytest.mark.parametrize("quelle", [
    "",
    "darstellung: bunt\nCCO",
    "+ CCO",
    "CCO +",
    "CCO OCC",
    "Ethanol:",
    "\n".join(["C"] * 5),
    " + ".join(["C"] * 7),
    "C" * 301,
    "C" * 2001,
])
def test_ungueltige_schreibweise(quelle):
    with pytest.raises(SmilesError):
        lies(quelle)


# ── Elektronenpaare ──────────────────────────────────────────────────────────

def _paare(smiles, symbol, *, ladung=None):
    mol = Chem.MolFromSmiles(smiles)
    return [freie_paare(a) for a in mol.GetAtoms()
            if a.GetSymbol() == symbol and (ladung is None or a.GetFormalCharge() == ladung)]


@pytest.mark.parametrize("smiles,symbol,ladung,erwartet", [
    ("[O-]c1ccccc1", "O", -1, [3]),        # Phenolat
    ("O=C1C=CC=C[CH-]1", "O", 0, [2]),     # Carbonyl-O der Grenzformel
    ("O=C1C=CC=C[CH-]1", "C", -1, [1]),    # Carbanion
    ("O", "O", None, [2]),                 # Wasser
    ("N", "N", None, [1]),                 # Ammoniak
    ("[NH4+]", "N", None, [0]),            # Ammonium
    ("CCl", "Cl", None, [3]),
    ("[Cl-]", "Cl", None, [4]),
    ("[Na+]", "Na", None, [0]),
    ("[NH3+]CC(=O)[O-]", "O", -1, [3]),    # Zwitterion
    ("CC", "C", None, [0, 0]),
])
def test_freie_paare(smiles, symbol, ladung, erwartet):
    assert _paare(smiles, symbol, ladung=ladung) == erwartet


def test_skelett_zeigt_paare_nur_an_heteroatomen_und_ladungen():
    assert len(zeichne(Molekuel("CCO"), "skelett").striche) == 2          # nur am O
    assert len(zeichne(Molekuel("O=C1C=CC=C[CH-]1"), "skelett").striche) == 3  # O zwei, C⁻ eins
    assert len(zeichne(Molekuel("CC"), "skelett").striche) == 0


def test_valenzstrich_zeigt_alle():
    # NH3 in der Valenzstrichformel: ein Paar am N, keins an den H.
    assert len(zeichne(Molekuel("N"), "valenzstrich").striche) == 1


# ── Zeichnen ─────────────────────────────────────────────────────────────────

def test_ungueltiges_smiles():
    with pytest.raises(SmilesError, match="kein gültiges SMILES"):
        zeichne(Molekuel("C1CC(=O"), "skelett")


def test_zu_grosses_molekuel():
    with pytest.raises(SmilesError, match="zu groß"):
        zeichne(Molekuel("C" * 121), "skelett")


def test_svg_ist_wohlgeformt_und_beschriftet():
    svg = setze(lies("Ester <&>: CC(=O)OCC + O -> CCO <-> CCO"))
    wurzel = ET.fromstring(svg)
    assert wurzel.tag.endswith("svg")
    assert "Ester &lt;&amp;&gt;" in svg, "Namen werden maskiert"
    assert svg.count("<polyline") >= 3, "Pfeilspitzen von -> und <->"


def test_gleiche_quelle_gleiches_bild():
    """Der Cache rechnet mit dem Hash der Quelle — das Bild muss davon allein abhängen."""
    quelle = "[O-]c1ccccc1 <-> O=C1C=CC=C[CH-]1"
    assert setze(lies(quelle)) == setze(lies(quelle))


def test_render_smiles_wirft_render_error():
    with pytest.raises(RenderError):
        asyncio.run(render_smiles("C1CC(=O"))


def test_registriert():
    assert service.RENDERERS["smiles"] is render_smiles


def test_grenzformel_behaelt_ihre_doppelbindungen():
    """Ohne Aromatizitäts-Erkennung: Die Doppelbindungen stehen, wo das Modell sie schrieb."""
    from rdkit import Chem
    from app.render.smiles import zeichne
    b = zeichne(Molekuel("O=C1C=CC=C[CH-]1"), "skelett")
    # 3 Doppelbindungen (C=O und zwei im Ring) → in RDKit-SVGs je zwei Linien „bond-…“.
    assert b.striche and len(b.striche) == 3
    mol = Chem.MolFromSmiles("O=C1C=CC=C[CH-]1", sanitize=False)
    Chem.SanitizeMol(mol, Chem.SanitizeFlags.SANITIZE_ALL ^ Chem.SanitizeFlags.SANITIZE_SETAROMATICITY)
    assert not any(bd.GetIsAromatic() for bd in mol.GetBonds())


@pytest.mark.parametrize("smiles,darstellung", [
    ("OC(=O)c1ccccc1", "skelett"),      # Benzoesäure — der gemeldete Fall (03.11.2026)
    ("CCO", "skelett"),
    ("OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O", "skelett"),
    ("[O-]c1ccccc1", "skelett"),
    ("[NH3+]CC(=O)[O-]", "valenzstrich"),
    ("OC(=O)c1ccccc1", "valenzstrich"),
])
def test_kein_elektronenpaar_in_der_beschriftung(smiles, darstellung):
    """Die Mitte keines Strichs liegt in einem Zeichen der Beschriftung — weder im
    Symbol noch im angehängten H („OH“) noch im Ladungszeichen."""
    from app.render.smiles import _beschriftung
    bild = zeichne(Molekuel(smiles), darstellung)
    kaesten = [k for liste in _beschriftung(bild.inhalt).values() for k in liste]
    for x1, y1, x2, y2 in bild.striche:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        for x0, y0, x3, y3 in kaesten:
            assert not (x0 <= mx <= x3 and y0 <= my <= y3), (smiles, (mx, my), (x0, y0, x3, y3))


def test_cache_schluessel_traegt_die_fassung():
    """Ändert sich die Zeichnung, darf der Cache das alte Bild nicht mehr treffen."""
    import hashlib
    from app.render import cache
    alt = hashlib.sha256("smiles\x00CCO".encode()).hexdigest()
    assert cache.svg_hash("smiles", "CCO") != alt
    # Der Schaltplan behält seinen Schlüssel aus Phase 17; der Graph hat seit 0.36 Fassung 2.
    assert cache.svg_hash("circuit", "x") == hashlib.sha256("circuit\x00x".encode()).hexdigest()
    assert cache.svg_hash("plot", "x") != hashlib.sha256("plot\x00x".encode()).hexdigest()


def test_keine_verschachtelten_svg():
    """Ein <svg> außen, Moleküle als Gruppen — der Office- und PDF-Export verträgt das."""
    svg = setze(lies("CCO + O -> CC(=O)O"))
    assert svg.count("<svg") == 1
    assert svg.count('<g transform="translate(') == 3
    ET.fromstring(svg)


def test_stile_als_attribute():
    """weasyprint, Word und LibreOffice: Präsentation als Attribute, nicht als style='…'."""
    svg = setze(lies("CCO"))
    assert "style=" not in svg
    assert 'fill="none"' in svg and 'stroke="#000000"' in svg


def test_carbanion_behaelt_sein_ladungszeichen_in_der_valenzstrichformel():
    """Die eigene Beschriftung „C“ ersetzt RDKits ganz — ohne Ausnahme fehlte das Minus."""
    from app.render.smiles import _beschriftung
    from rdkit import Chem
    bild = zeichne(Molekuel("O=C1C=CC=C[CH-]1"), "valenzstrich")
    # AddHs hängt die H hinten an — die Nummern der schweren Atome bleiben.
    mol = Chem.MolFromSmiles("O=C1C=CC=C[CH-]1", sanitize=False)
    idx = next(a.GetIdx() for a in mol.GetAtoms() if a.GetFormalCharge() == -1)
    assert len(_beschriftung(bild.inhalt)[idx]) >= 2, "Symbol und Ladungszeichen"


def test_unmoegliches_molekuel_wird_platzhalter():
    """Messung 03.11.2026: `[O-][O-]C=O` kippte die ganze Reihe — jetzt nur sein Platz."""
    svg = setze(lies("O=C([O-])[O-] <-> [O-][O-]C=O"))
    ET.fromstring(svg)
    assert "nicht darstellbar" in svg and "[O-][O-]C=O" in svg
    assert svg.count('<g transform="translate(') == 2
    assert 'stroke-dasharray="4 3"' in svg


def test_platzhalter_maskiert_die_quelle():
    svg = setze(lies("CCO + C<&>"))
    assert "C&lt;&amp;&gt;" in svg
    ET.fromstring(svg)


def test_block_ohne_zeichenbares_molekuel_scheitert():
    with pytest.raises(SmilesError, match="kein gültiges SMILES"):
        setze(lies("C1CC(=O + [O-][O-]C=O"))
