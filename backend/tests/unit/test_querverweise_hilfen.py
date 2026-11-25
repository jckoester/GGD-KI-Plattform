"""Hilfsfunktionen der Querverweise (Päckchen AY Teil 1): Band, Stufen, Kurztitel."""
from app.context.querverweise import band, kurztitel, stufen
from app.db.models import ContextNode


def test_band_und_stufen_aus_der_kennung():
    k = ContextNode(title="3.4.3 Schwingungen",
                    metadata_={"bp_id": "BP2016BW_ALLG_GYM_PH.V2_IK_11-12-BF-QUANTEN_03"})
    assert band(k) == "11-12-BF-QUANTEN"
    assert stufen(k) == (11, 12)


def test_stufen_aus_den_spalten_vor_dem_band():
    k = ContextNode(title="x", min_grade=7, max_grade=8,
                    metadata_={"bp_id": "BP2016BW_ALLG_GYM_PH.V2_IK_11-12_03"})
    assert stufen(k) == (7, 8)


def test_ohne_kennung():
    k = ContextNode(title="x", metadata_={})
    assert band(k) is None and stufen(k) == (None, None)


def test_kurztitel():
    assert kurztitel("3.2.1(3) die Funktion") == "die Funktion"
    assert kurztitel("3.2.3 Energie") == "Energie"
    assert kurztitel("2.2.35 essayistisch schreiben") == "essayistisch schreiben"
    assert kurztitel("3.3.1.2(11) die Struktur") == "die Struktur"
    assert kurztitel("Ohne Nummer") == "Ohne Nummer"
