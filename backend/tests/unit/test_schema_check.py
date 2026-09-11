"""Die Startprüfung auf den Migrationsstand.

Hintergrund: Am 09.09.2026 stand die Entwicklungsdatenbank auf `0056`, der Code auf
`0057`. Jede Knotenliste antwortete mit 500 (`relation "node_aliases" does not
exist`) — bei grünem Prüflauf, weil die Integrationstests ihre eigene Datenbank
hochfahren und die betriebene nie sehen.
"""
import pytest

from app.db.schema_check import (
    SchemaVeraltet,
    abweichung,
    bekannte_revisionen,
    kopf_revisionen,
    pruefe_beim_start,
)


class TestAbweichung:

    def test_gleicher_stand_meldet_nichts(self):
        assert abweichung({"0057"}, {"0057"}) is None

    def test_datenbank_hinterher_nennt_beide_staende_und_den_befehl(self):
        meldung = abweichung({"0056"}, {"0057"})
        assert "0056" in meldung and "0057" in meldung
        assert "alembic upgrade head" in meldung

    def test_leere_datenbank_bekommt_einen_eigenen_satz(self):
        # „steht auf []" wäre keine Auskunft; hier fehlt nicht eine Migration,
        # sondern alle.
        meldung = abweichung(set(), {"0057"})
        assert "keine Migration" in meldung
        assert "alembic upgrade head" in meldung

    def test_unbekannte_revision_schlaegt_kein_upgrade_vor(self):
        # Die Datenbank wurde von einer neueren Fassung migriert; `upgrade head`
        # hülfe hier nicht, hier läuft der falsche Stand.
        meldung = abweichung({"0058"}, {"0057"}, bekannt={"0056", "0057"})
        assert "kennt dieser Code nicht" in meldung
        assert "upgrade" in meldung and "hilft nicht" in meldung

    def test_ohne_bekannte_revisionen_wird_nichts_behauptet(self):
        # Ohne die Liste lässt sich „hinterher" nicht von „voraus" unterscheiden —
        # dann bleibt es beim schlichten Hinweis samt Befehl.
        meldung = abweichung({"0058"}, {"0057"})
        assert "kennt dieser Code nicht" not in meldung
        assert "alembic upgrade head" in meldung


class TestKopfRevisionen:

    def test_liest_den_kopf_aus_den_migrationsdateien(self):
        kopf = kopf_revisionen()
        assert len(kopf) == 1, f"mehrere Köpfe: {kopf}"
        # Kein fester Wert: Der Kopf wandert mit jeder Migration weiter, und ein
        # Test, der bei jeder Migration bricht, wird irgendwann blind angepasst.
        assert next(iter(kopf)).strip()

    def test_der_kopf_gehoert_zu_den_bekannten_revisionen(self):
        # Sonst meldete die Prüfung bei einer aktuellen Datenbank „unbekannt".
        assert kopf_revisionen() <= bekannte_revisionen()

    def test_kennt_deutlich_mehr_als_nur_den_kopf(self):
        assert len(bekannte_revisionen()) > 50


class _Session:
    def __init__(self, zeilen=None, fehler=None):
        self._zeilen = zeilen or []
        self._fehler = fehler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, *args, **kwargs):
        if self._fehler:
            raise self._fehler

        class _Ergebnis:
            def __init__(self, zeilen):
                self._zeilen = zeilen

            def all(self):
                return self._zeilen

        return _Ergebnis(self._zeilen)


def _factory(session):
    return lambda: session


class TestPruefeBeimStart:

    @pytest.mark.asyncio
    async def test_bricht_bei_veralteter_datenbank_ab(self, monkeypatch):
        monkeypatch.setattr(
            "app.db.schema_check.kopf_revisionen", lambda: {"0057"}
        )
        monkeypatch.setattr(
            "app.db.schema_check.bekannte_revisionen", lambda: {"0056", "0057"}
        )
        with pytest.raises(SchemaVeraltet, match="0056"):
            await pruefe_beim_start(_factory(_Session([("0056",)])))

    @pytest.mark.asyncio
    async def test_laesst_passenden_stand_durch(self, monkeypatch):
        monkeypatch.setattr(
            "app.db.schema_check.kopf_revisionen", lambda: {"0057"}
        )
        monkeypatch.setattr(
            "app.db.schema_check.bekannte_revisionen", lambda: {"0056", "0057"}
        )
        await pruefe_beim_start(_factory(_Session([("0057",)])))

    @pytest.mark.asyncio
    async def test_unerreichbare_datenbank_warnt_nur(self, monkeypatch, caplog):
        """Unbekannt ist nicht dasselbe wie veraltet.

        Ist die Datenbank weg, scheitern die übrigen Startprüfungen ohnehin an
        derselben Verbindung — hier eine Migrationsdiagnose zu behaupten, wäre eine
        falsche Fährte.
        """
        monkeypatch.setattr(
            "app.db.schema_check.kopf_revisionen", lambda: {"0057"}
        )
        monkeypatch.setattr(
            "app.db.schema_check.bekannte_revisionen", lambda: {"0057"}
        )
        session = _Session(fehler=RuntimeError("keine Verbindung"))
        await pruefe_beim_start(_factory(session))  # kein Ausbruch

    @pytest.mark.asyncio
    async def test_kaputte_alembic_konfiguration_warnt_nur(self, monkeypatch):
        def kaputt():
            raise RuntimeError("alembic.ini weg")

        monkeypatch.setattr("app.db.schema_check.kopf_revisionen", kaputt)
        await pruefe_beim_start(_factory(_Session([("0056",)])))  # kein Ausbruch
