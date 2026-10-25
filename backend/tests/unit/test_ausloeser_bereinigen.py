"""`ausloeser.bereinige` (Päckchen C1, Schritt 3): Reihenfolge, Dubletten, Grenzen."""
import pytest

from app.assistants import ausloeser
from app.assistants.ausloeser import AusloeserFehler, bereinige


def test_rand_leer_und_dubletten_weg_reihenfolge_bleibt():
    assert bereinige(["  b ", "", "a", "b", "   ", "c"], ausloeser.BEISPIEL) == ["b", "a", "c"]


def test_none_ist_leer():
    assert bereinige(None, ausloeser.GEGENBEISPIEL) == []


def test_grosschreibung_ist_ein_anderer_text():
    # Die Datenbank prüft genau (`uq_trigger_example_text`) — hier dieselbe Regel.
    assert bereinige(["Mol", "mol"], ausloeser.BEISPIEL) == ["Mol", "mol"]


def test_zu_viele():
    texte = [f"t{i}" for i in range(ausloeser.MAX_EINTRAEGE + 1)]
    with pytest.raises(AusloeserFehler, match="höchstens"):
        bereinige(texte, ausloeser.BEISPIEL)
    assert len(bereinige(texte[:-1], ausloeser.BEISPIEL)) == ausloeser.MAX_EINTRAEGE


def test_zu_lang_nennt_die_liste():
    with pytest.raises(AusloeserFehler, match="Gegenbeispiele"):
        bereinige(["x" * (ausloeser.MAX_ZEICHEN + 1)], ausloeser.GEGENBEISPIEL)


def test_grenzen_im_editor_gleich():
    """`frontend/src/lib/ausloeser_editor.js` spiegelt die Grenzen — Wächter gegen Auseinanderlaufen."""
    import re
    from pathlib import Path

    js = (Path(__file__).resolve().parents[3] / "frontend/src/lib/ausloeser_editor.js").read_text()
    assert int(re.search(r"MAX_EINTRAEGE = (\d+)", js).group(1)) == ausloeser.MAX_EINTRAEGE
    assert int(re.search(r"MAX_ZEICHEN = (\d+)", js).group(1)) == ausloeser.MAX_ZEICHEN
