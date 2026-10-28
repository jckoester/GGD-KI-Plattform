"""Hinweise auf Neuerungen (0.17, Plan „Fachbegriffe der Stunde", Schritt 6).

Der Lader weist kaputte Dateien ab; `sichtbar` entscheidet an einer Stelle, wer was sieht.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from app.neuigkeiten.quelle import DATEI, LAUFZEIT, Neuigkeit, lade, sichtbar
from app.ui.levels import UiLevels

BEISPIEL = Path(__file__).resolve().parents[3] / "config" / "ui_levels.example.yaml"
STUFEN = UiLevels.model_validate(yaml.safe_load(BEISPIEL.read_text(encoding="utf-8")))
HEUTE = date(2026, 10, 20)


def _n(**kw) -> Neuigkeit:
    daten = {"id": "x", "version": "0.17.0", "datum": date(2026, 10, 17), "rollen": ["teacher"],
             "titel": "T", "text": "Text"} | kw
    return Neuigkeit.model_validate(daten)


def _sicht(n, rollen=("teacher",), gelesen=(), konto_seit=None, stufe=None, heute=HEUTE):
    return [x.id for x in sichtbar([n], rollen=list(rollen), gelesen=set(gelesen),
                                   konto_seit=konto_seit, stufe=stufe, stufen=STUFEN, heute=heute)]


# ── Lader ────────────────────────────────────────────────────────────────────


def _datei(tmp_path, eintraege):
    p = tmp_path / "neuigkeiten.yaml"
    p.write_text(yaml.safe_dump(eintraege, allow_unicode=True), encoding="utf-8")
    return p


GUT = {"id": "a", "version": "0.17.0", "datum": "2026-10-17", "rollen": ["teacher"],
       "titel": "T", "text": "Text"}


def test_lader_liest_gueltige_datei(tmp_path):
    assert [n.id for n in lade(_datei(tmp_path, [GUT]))] == ["a"]


@pytest.mark.parametrize("eintraege, meldung", [
    ([GUT, GUT], "doppelte id"),
    ([GUT | {"rollen": ["lehrer"]}], "unbekannte Rolle"),
    ([GUT | {"datum": "2026-13-40"}], "date"),
    ([GUT | {"eintrag": "planer"}], "unbekannter Navigationseintrag"),
    ([GUT | {"link": "https://example.org"}], "link"),
    ([GUT | {"rollen": []}], "rollen"),
])
def test_lader_weist_kaputtes_ab(tmp_path, eintraege, meldung):
    with pytest.raises(ValueError, match=meldung):
        lade(_datei(tmp_path, eintraege))


def test_ausgelieferte_datei_ist_gueltig():
    """Jeder `eintrag` steht in der eingecheckten Beispielkonfiguration — sonst verschwände
    der Hinweis bei keiner Schule, die ihn nicht eigens nachträgt, aber er prüfte auch
    nichts."""
    liste = lade(DATEI)
    assert liste
    bekannt = {e for r in STUFEN.rollen.values() for s in r.stufen for e in s.eintraege}
    assert all(n.eintrag in bekannt for n in liste if n.eintrag)
    assert all(n.link is None or n.link.startswith("/help/") for n in liste)


# ── Wer was sieht ────────────────────────────────────────────────────────────


def test_rolle_muss_passen():
    assert _sicht(_n(), rollen=["student"]) == []
    assert _sicht(_n(rollen=["student", "teacher"]), rollen=["student"]) == ["x"]


def test_admin_sieht_hinweise_fuer_lehrkraefte():
    assert _sicht(_n(), rollen=["admin"]) == ["x"]


def test_weggeklickt():
    assert _sicht(_n(), gelesen={"x"}) == []


def test_aelter_als_das_konto():
    neu = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)
    assert _sicht(_n(), konto_seit=neu) == []
    assert _sicht(_n(datum=date(2026, 10, 18)), konto_seit=neu) == ["x"]   # am selben Tag
    assert _sicht(_n(), konto_seit=None) == ["x"]                           # kein Eintrag


def test_abgelaufen():
    assert _sicht(_n(bis=date(2026, 10, 19))) == []
    assert _sicht(_n(bis=HEUTE)) == ["x"]


def test_ohne_bis_endet_der_hinweis_nach_der_laufzeit():
    start = date(2026, 10, 17)
    assert _sicht(_n(datum=start), heute=start + LAUFZEIT) == ["x"]                # letzter Tag
    assert _sicht(_n(datum=start), heute=start + LAUFZEIT + timedelta(days=1)) == []


def test_bis_geht_der_laufzeit_vor():
    start = date(2026, 10, 17)
    spaeter = start + LAUFZEIT + timedelta(days=10)
    assert _sicht(_n(datum=start, bis=spaeter), heute=spaeter) == ["x"]
    assert _sicht(_n(datum=start, bis=start), heute=start + timedelta(days=1)) == []


def test_eintrag_ueber_der_eigenen_stufe():
    """`planner` liegt bei Lehrkräften auf Stufe 3 (Beispielkonfiguration)."""
    assert _sicht(_n(eintrag="planner"), stufe=2) == []
    assert _sicht(_n(eintrag="planner"), stufe=3) == ["x"]
    assert _sicht(_n(eintrag="planner"), stufe=None) == ["x"]               # keine Stufen


def test_eintrag_ohne_platz_in_der_konfiguration_zeigt_trotzdem():
    """Schüler:innen haben `planner` in keiner Stufe — die Regel verschluckt dann nichts."""
    assert _sicht(_n(rollen=["student"], eintrag="planner"), rollen=["student"], stufe=1) == ["x"]


def test_neueste_zuerst():
    alt, neu = _n(id="alt", datum=date(2026, 9, 20)), _n(id="neu", datum=date(2026, 10, 1))
    assert [n.id for n in sichtbar([alt, neu], rollen=["teacher"], gelesen=set(), konto_seit=None,
                                   stufe=None, stufen=STUFEN, heute=HEUTE)] == ["neu", "alt"]
