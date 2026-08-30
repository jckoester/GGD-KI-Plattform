"""Kostenabrechnung eines Chat-Zuges (app/chat/router.py).

Ein Zug ist **mehr als eine LLM-Anfrage**: je Werkzeugrunde eine, dazu die
Titelgenerierung. Alle laufen über den Virtual Key der Nutzer:in und belasten deren
Budget. Bis 08/2026 wurde nur die letzte abgerechnet — ein Zug mit drei Runden belastete
das Budget um zwei Drittel zu wenig, und die Konversationssumme stimmte nicht.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.chat.router import _kosten_des_zuges


class _Client:
    """Liefert je Request-ID einen Betrag — oder erst ab dem n-ten Versuch."""

    def __init__(self, betraege: dict, ab_versuch: dict | None = None):
        self.betraege = betraege
        self.ab_versuch = ab_versuch or {}
        self.abfragen: list[str] = []

    async def get_spend_log(self, request_id: str):
        self.abfragen.append(request_id)
        noetig = self.ab_versuch.get(request_id, 1)
        if self.abfragen.count(request_id) < noetig:
            return None
        return self.betraege.get(request_id)


@pytest.fixture(autouse=True)
def _ohne_warten():
    """Die Wartezeit ist hier nur Ablauf, nicht Gegenstand der Prüfung."""
    with patch("app.chat.router.asyncio.sleep", new=AsyncMock()):
        yield


async def _summe(client, ids, wartezeiten=(0.0, 0.0, 0.0)):
    return await _kosten_des_zuges(client, ids, wartezeiten=wartezeiten)


class TestSummierung:
    async def test_alle_runden_zaehlen(self):
        """Der Kern: drei Anfragen, drei Beträge, eine Summe."""
        c = _Client({"a": 0.0005, "b": 0.0002, "c": 0.0001})
        k = await _summe(c, ["a", "b", "c"])
        assert k.summe == pytest.approx(0.0008)
        assert (k.gefunden, k.gesamt) == (3, 3)

    async def test_teilsumme_wenn_eine_fehlt(self):
        """Lieber ein belegter Teilbetrag als gar keiner — die Zahlen sagen, dass er
        unvollständig ist."""
        c = _Client({"a": 0.0005, "c": 0.0001})
        k = await _summe(c, ["a", "b", "c"])
        assert k.summe == pytest.approx(0.0006)
        assert (k.gefunden, k.gesamt) == (2, 3)

    async def test_nichts_gefunden_bleibt_ohne_angabe(self):
        """Wie bisher: keine Kostenangabe statt einer erfundenen Null."""
        k = await _summe(_Client({}), ["a", "b"])
        assert k.summe is None and (k.gefunden, k.gesamt) == (0, 2)

    async def test_ohne_anfragen(self):
        k = await _summe(_Client({}), [])
        assert k.summe is None and k.gesamt == 0

    async def test_dubletten_zaehlen_einmal(self):
        """Dieselbe ID doppelt zu summieren wäre schlimmer, als sie zu verlieren."""
        c = _Client({"a": 0.0005})
        k = await _summe(c, ["a", "a", None, ""])
        assert k.summe == pytest.approx(0.0005) and k.gesamt == 1


class TestWartezeit:
    async def test_staffel_wird_eingehalten(self):
        """Gestaffelt statt gleichmäßig — gemessen begründet.

        LiteLLM braucht für Streaming-Anfragen 6–13 s, bis die Buchung abrufbar ist; ein
        festes Fenster müsste sich am schlechtesten Fall ausrichten und wartete dann auch
        im guten. Die Staffel ist nach 1 s fertig, wenn alles da ist, und reicht im
        Ausreißerfall bis 15 s.
        """
        from app.chat.router import _SPEND_LOG_WARTEZEITEN

        assert _SPEND_LOG_WARTEZEITEN == (1.0, 2.0, 4.0, 8.0)
        assert sum(_SPEND_LOG_WARTEZEITEN) >= 12.6, (
            "muss den gemessenen schlechtesten Fall (12,6 s) abdecken"
        )
        assert _SPEND_LOG_WARTEZEITEN[0] <= 1.0, (
            "die erste Abfrage soll früh kommen — der Normalfall ist schnell da"
        )

        with patch("app.chat.router.asyncio.sleep", new=AsyncMock()) as schlaf:
            await _kosten_des_zuges(_Client({}), ["a"],
                                    wartezeiten=_SPEND_LOG_WARTEZEITEN)
        assert [c.args[0] for c in schlaf.await_args_list] == [1.0, 2.0, 4.0, 8.0]

    async def test_versuche_wachsen_nicht_mit_der_rundenzahl(self):
        """Die Zusage, die den Chat schnell hält.

        LiteLLM schreibt die SpendLogs verzögert, also wird wiederholt nachgefragt. Läge
        die Schleife andersherum — IDs außen, Versuche innen —, wartete ein Zug mit drei
        Runden im ungünstigsten Fall neunmal statt dreimal; bei den 3 s der Dev-Umgebung
        wären das 27 Sekunden bis zur fertigen Antwort.
        """
        with patch("app.chat.router.asyncio.sleep", new=AsyncMock()) as schlaf:
            await _summe(_Client({}), ["a", "b", "c"])
        assert schlaf.await_count == 3, "einmal je Versuch, nicht je Anfrage"

    async def test_hoert_auf_sobald_alles_da_ist(self):
        with patch("app.chat.router.asyncio.sleep", new=AsyncMock()) as schlaf:
            await _summe(_Client({"a": 0.1}), ["a"])
        assert schlaf.await_count == 1

    async def test_spaet_geschriebene_logs_werden_nachgeholt(self):
        """Der Grund für die Wiederholung überhaupt."""
        c = _Client({"a": 0.1, "b": 0.2}, ab_versuch={"b": 3})
        k = await _summe(c, ["a", "b"])
        assert k.summe == pytest.approx(0.3) and k.gefunden == 2

    async def test_bereits_gefundene_werden_nicht_erneut_abgefragt(self):
        c = _Client({"a": 0.1, "b": 0.2}, ab_versuch={"b": 3})
        await _summe(c, ["a", "b"])
        assert c.abfragen.count("a") == 1, "einmal gefunden, nicht wieder nachfragen"
