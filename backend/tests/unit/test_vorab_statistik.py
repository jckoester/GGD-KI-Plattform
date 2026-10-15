"""Die Zeilen der Vorab-Statistik und ihre Woche (0.16, Schritt 3c) — ohne Datenbank.

Das Hochzählen gegen Postgres prüft `tests/integration/test_vorab_statistik.py`.
"""
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.context.bausteine import Kontext
from app.context.vorab_statistik import ZAEHLER, woche_von, zaehlen, zeilen


def _woche(**kw):
    return zeilen(**{"sicher": [], "angebot": [], "im_werkzeugergebnis": set(), "gesucht": False} | kw)[0]


def test_wochenzeile_zuerst_dann_knoten():
    z = zeilen(sicher=["a"], angebot=["b", "c"], im_werkzeugergebnis={"b"}, gesucht=True)
    assert [(r["node_id"], r["stufe"]) for r in z] == [
        (None, None), ("a", "sicher"), ("b", "angebot"), ("c", "angebot")]
    assert [(r["vorgelegt"], r["im_werkzeugergebnis"]) for r in z[1:]] == [(1, 0), (1, 1), (1, 0)]
    assert all(set(r) >= set(ZAEHLER) for r in z)


def test_nachgeschlagen_mit_und_ohne_sicheren_treffer():
    mit = _woche(sicher=["a"], angebot=["b"], im_werkzeugergebnis={"b"})
    assert (mit["angebot_nachgeschlagen"], mit["angebot_ohne_sicher"],
            mit["angebot_ohne_sicher_nachgeschlagen"]) == (1, 0, 0)
    ohne = _woche(angebot=["b"], im_werkzeugergebnis={"b"})
    assert (ohne["angebot_nachgeschlagen"], ohne["angebot_ohne_sicher"],
            ohne["angebot_ohne_sicher_nachgeschlagen"]) == (1, 1, 1)


def test_ein_sicherer_treffer_im_werkzeugergebnis_ist_kein_nachgeschlagenes_angebot():
    """Gegenprobe: Nur angebotene Knoten zählen als nachgeschlagen."""
    w = _woche(sicher=["a"], im_werkzeugergebnis={"a"})
    assert (w["mit_sicher"], w["mit_angebot"], w["angebot_nachgeschlagen"]) == (1, 0, 0)


def test_suche_ohne_angebot():
    assert _woche(gesucht=True)["suchen_ohne_angebot"] == 1
    assert _woche(gesucht=True, angebot=["b"])["suchen_ohne_angebot"] == 0
    assert _woche()["suchen_ohne_angebot"] == 0


def test_doppelte_kennung_zaehlt_einmal():
    """Ein Statement darf dieselbe Zeile nicht zweimal treffen (`ON CONFLICT` bricht sonst ab)."""
    assert len(zeilen(sicher=["a", "a"], angebot=[], im_werkzeugergebnis=set(), gesucht=False)) == 2


@pytest.mark.parametrize("zeitpunkt, montag", [
    (datetime(2026, 10, 18, 21, 30, tzinfo=timezone.utc), date(2026, 10, 12)),  # So 23:30 MESZ
    (datetime(2026, 10, 18, 22, 10, tzinfo=timezone.utc), date(2026, 10, 19)),  # Mo 00:10 MESZ
    (datetime(2026, 12, 27, 23, 10, tzinfo=timezone.utc), date(2026, 12, 28)),  # Mo 00:10 MEZ
])
def test_woche_in_ortszeit(zeitpunkt, montag):
    assert woche_von(zeitpunkt) == montag


@pytest.mark.asyncio
async def test_ein_fehler_beim_zaehlen_wirft_nie():
    """Die Antwort ist schon gespeichert — ein Fehler hier darf den Strom nicht abbrechen."""
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("DB weg")
    await zaehlen(db, kontext=Kontext(text=""), werkzeug_bausteine=[], gesucht=False,
                  modell="chat-standard")
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
