"""Unit-Tests für die Lebenszyklus-Läufe der Kontextknoten (AP4, ADR-013).

Geprüft werden die **Bedingungen**, die beide Läufe aufbauen — nicht die Datenbank. Die
Bedingungen sind das Riskante: Ein zu weites `WHERE` löscht den archivierten
Bildungsplan, ein zu enges lässt die Frist ins Leere laufen, und beides fiele erst
Jahre später auf.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa

from app.crons.node_lifecycle_service import (
    ARCHIV_AUFBEWAHRUNG_TAGE,
    archiviere_abgelaufene,
    loesche_alte_archivierte,
)
from app.db.models import ContextNode


def _db(zaehler):
    """DB-Attrappe: liefert die Zählwerte der Reihe nach, protokolliert die Anweisungen."""
    db = AsyncMock()
    ergebnisse = []
    for wert in zaehler:
        m = MagicMock()
        m.scalar_one.return_value = wert
        ergebnisse.append(m)
    db.execute = AsyncMock(side_effect=ergebnisse + [MagicMock()])
    db.commit = AsyncMock()
    return db


def _sql(db, index):
    return str(db.execute.await_args_list[index].args[0].compile(
        compile_kwargs={"literal_binds": True}
    ))


class TestArchivierung:

    async def test_ohne_faellige_knoten_passiert_nichts(self):
        db = _db([0])
        lauf = await archiviere_abgelaufene(db)

        assert lauf.archiviert == 0
        db.commit.assert_not_called()

    async def test_faellige_werden_archiviert(self):
        db = _db([7])
        lauf = await archiviere_abgelaufene(db, heute=date(2026, 9, 2))

        assert lauf.geprueft == 7 and lauf.archiviert == 7
        db.commit.assert_awaited_once()
        anweisung = _sql(db, 1)
        assert "UPDATE context_nodes" in anweisung
        assert "archived" in anweisung

    async def test_dry_run_aendert_nichts(self):
        db = _db([7])
        lauf = await archiviere_abgelaufene(db, dry_run=True)

        assert lauf.geprueft == 7 and lauf.archiviert == 0
        db.commit.assert_not_called()

    async def test_bedingung_trifft_nur_aktive_mit_ueberschrittenem_datum(self):
        db = _db([0])
        await archiviere_abgelaufene(db, heute=date(2026, 9, 2))

        bedingung = _sql(db, 0)
        assert "status = 'active'" in bedingung
        assert "valid_until IS NOT NULL" in bedingung
        assert "valid_until < '2026-09-02'" in bedingung

    async def test_stichtag_ist_ein_echter_vergleich(self):
        """Genau am `valid_until` ist ein Knoten noch gültig — erst danach fällt er."""
        db = _db([0])
        await archiviere_abgelaufene(db, heute=date(2026, 9, 2))

        assert "valid_until <= " not in _sql(db, 0)


class TestLoeschung:

    def _zaehler(self, faellig=0, glob=0, ausgesetzt=0, zu_loeschen=0):
        return [faellig, glob, ausgesetzt, zu_loeschen]

    async def test_frist_betraegt_drei_schuljahre(self):
        assert ARCHIV_AUFBEWAHRUNG_TAGE == 1095

    async def test_nichts_faelliges_kein_commit(self):
        db = _db(self._zaehler())
        lauf = await loesche_alte_archivierte(db)

        assert lauf.geloescht == 0
        db.commit.assert_not_called()

    async def test_faellige_werden_geloescht(self):
        db = _db(self._zaehler(faellig=5, zu_loeschen=5))
        lauf = await loesche_alte_archivierte(db)

        assert lauf.faellig == 5 and lauf.geloescht == 5
        db.commit.assert_awaited_once()
        assert "DELETE FROM context_nodes" in _sql(db, 4)

    async def test_globale_knoten_sind_ausgenommen(self):
        """⚠️ Die Regel, die den archivierten Bildungsplan rettet.

        Am 02.09.2026 waren **alle** 4770 archivierten Knoten der Entwicklungsdatenbank
        `write_scope = 'global'` — der Bildungsplan wird jahrgangsweise archiviert, wenn
        eine neue Edition greift. Ohne diese Ausnahme hätte der Lauf ihn nach drei Jahren
        gelöscht, während Curricula weiter darauf verweisen.
        """
        db = _db(self._zaehler(faellig=4770, glob=4770))
        lauf = await loesche_alte_archivierte(db)

        assert lauf.faellig == 4770
        assert lauf.geschuetzt_global == 4770
        assert lauf.geloescht == 0
        db.commit.assert_not_called()
        assert "write_scope != 'global'" in _sql(db, 3)

    async def test_ausgesetzte_loeschung_wird_uebersprungen(self):
        db = _db(self._zaehler(faellig=3, ausgesetzt=3))
        lauf = await loesche_alte_archivierte(db)

        assert lauf.geschuetzt_ausgesetzt == 3 and lauf.geloescht == 0
        assert "loeschung_ausgesetzt" in _sql(db, 3)

    async def test_ohne_archived_at_keine_loeschung(self):
        """Wer nicht weiß, seit wann etwas liegt, kann keine Frist berechnen.

        Betrifft Knoten, die vor der Einführung des Feldes archiviert wurden.
        """
        db = _db(self._zaehler())
        await loesche_alte_archivierte(db)

        assert "archived_at IS NOT NULL" in _sql(db, 0)

    async def test_grenze_liegt_1095_tage_zurueck(self):
        jetzt = datetime(2029, 9, 2, 5, 0, tzinfo=timezone.utc)
        db = _db(self._zaehler())
        await loesche_alte_archivierte(db, jetzt=jetzt)

        erwartet = (jetzt - timedelta(days=1095)).date().isoformat()
        assert erwartet in _sql(db, 0)

    async def test_dry_run_zaehlt_nur(self):
        db = _db(self._zaehler(faellig=5, zu_loeschen=5))
        lauf = await loesche_alte_archivierte(db, dry_run=True)

        assert lauf.faellig == 5 and lauf.geloescht == 0
        db.commit.assert_not_called()
