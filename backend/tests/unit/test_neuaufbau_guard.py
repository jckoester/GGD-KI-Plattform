"""`--neuaufbau` darf sich nicht wiederholen lassen.

Der Schalter ist der einmalige Umstellungsschritt vom Monats- aufs Wochenmodell. Er
verwirft die bestehende Obergrenze absichtlich und setzt sie auf „Verbrauch + ein
Wochenbetrag". Ein zweiter Lauf tut dasselbe noch einmal — und nimmt damit den angesparten
Vorsprung weg, ohne dass etwas fehlschlägt. Am 30.08.2026 hat genau diese Möglichkeit eine
Fehlersuche in die falsche Richtung geschickt.

Erkannt wird die bereits gelaufene Umstellung am Merkposten `budget_accrual`, den
`merke()` je Nutzerin mit dem Schuljahr schreibt.
"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SKRIPT = Path(__file__).resolve().parents[2] / "scripts" / "weekly_budget_accrual.py"


def _laden():
    """Über den Dateipfad laden — `backend/scripts/` ist bewusst kein Paket."""
    spec = importlib.util.spec_from_file_location("weekly_budget_accrual", SKRIPT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture
def modul():
    return _laden()


def _db_mit_treffer(treffer):
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=treffer)
    sitzung = MagicMock()
    sitzung.__aenter__ = AsyncMock(return_value=db)
    sitzung.__aexit__ = AsyncMock(return_value=False)
    return sitzung


@pytest.mark.asyncio
async def test_merkposten_des_laufenden_schuljahres_gilt_als_umgestellt(modul):
    with patch.object(modul, "AsyncSessionLocal", return_value=_db_mit_treffer("pseudo-1")), \
         patch.object(modul, "load_school_year",
                      return_value=SimpleNamespace(schuljahr="2026/27")):
        assert await modul._umstellung_bereits_gelaufen() is True


@pytest.mark.asyncio
async def test_ohne_merkposten_ist_die_umstellung_offen(modul):
    """Auch der Fall „Merkposten nur aus dem Vorjahr" — die Abfrage filtert aufs Schuljahr."""
    with patch.object(modul, "AsyncSessionLocal", return_value=_db_mit_treffer(None)), \
         patch.object(modul, "load_school_year",
                      return_value=SimpleNamespace(schuljahr="2026/27")):
        assert await modul._umstellung_bereits_gelaufen() is False


def test_zweiter_neuaufbau_bricht_ab(modul, monkeypatch, capsys):
    """Abbruch mit Rückgabewert 1 — und ohne dass eine Zuteilung angestoßen wird."""
    monkeypatch.setattr("sys.argv", ["weekly_budget_accrual.py", "--neuaufbau"])
    monkeypatch.setattr(modul, "_umstellung_bereits_gelaufen", AsyncMock(return_value=True))
    gelaufen = MagicMock()
    monkeypatch.setattr(modul, "run", gelaufen)

    with pytest.raises(SystemExit) as exc:
        modul.main()

    assert exc.value.code == 1
    gelaufen.assert_not_called()


def test_trotzdem_hebt_die_sperre_auf(modul, monkeypatch):
    monkeypatch.setattr("sys.argv", ["weekly_budget_accrual.py", "--neuaufbau", "--trotzdem"])
    monkeypatch.setattr(modul, "_umstellung_bereits_gelaufen", AsyncMock(return_value=True))
    aufrufe = []
    monkeypatch.setattr(modul.asyncio, "run", lambda coro: aufrufe.append(coro) or coro.close())

    modul.main()

    assert aufrufe, "Mit --trotzdem muss die Zuteilung angestoßen werden."


def test_regellauf_ist_von_der_sperre_nicht_betroffen(modul, monkeypatch):
    """Ohne `--neuaufbau` wird der Merkposten gar nicht erst abgefragt.

    Der wöchentliche Cron läuft mit bestehenden Merkposten — genau dann, wenn die Sperre
    greifen würde. Sie darf ihn nicht anfassen.
    """
    monkeypatch.setattr("sys.argv", ["weekly_budget_accrual.py"])
    gefragt = AsyncMock(return_value=True)
    monkeypatch.setattr(modul, "_umstellung_bereits_gelaufen", gefragt)
    monkeypatch.setattr(modul.asyncio, "run", lambda coro: coro.close())

    modul.main()

    gefragt.assert_not_awaited()
