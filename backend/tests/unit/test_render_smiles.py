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
    assert block.darstellung == "skelett"


def test_ladung_in_klammern_ist_kein_operator():
    teile = lies("[NH3+]CC(=O)[O-]").reihen[0].teile
    assert len(teile) == 1 and teile[0].smiles == "[NH3+]CC(=O)[O-]"


def test_mesomerie_unicode_und_mehrere_reihen():
    block = lies("darstellung: valenzstrich\n[O-]c1ccccc1 ↔ O=C1C=CC=C[CH-]1\nO → O")
    assert block.darstellung == "valenzstrich"
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
