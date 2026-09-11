"""Das Nachtragen der Kosten im Hintergrund (AP2).

Bis 09/2026 hielt der Chat den Stream bis zu 15 s offen, nur um auf die SpendLogs
zu warten — nachdem der Antworttext längst dastand.
"""
import asyncio
from uuid import uuid4

import pytest

from app.chat import kosten_nachtrag
from app.core import hintergrund


class _Sitzung:
    """Sitzung, die ihre Anweisungen mitschreibt, statt sie auszuführen."""

    def __init__(self, protokoll):
        self.protokoll = protokoll

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, statement, *args, **kwargs):
        self.protokoll.append(statement)

    async def commit(self):
        self.protokoll.append("commit")


def _factory(protokoll):
    return lambda: _Sitzung(protokoll)


@pytest.mark.asyncio
async def test_schreibt_betrag_und_zustand(monkeypatch):
    protokoll = []
    msg, conv = uuid4(), uuid4()

    async def kosten(client, ids, *, wartezeiten):
        from app.chat.router import Zugkosten
        return Zugkosten(summe=0.012, gefunden=2, gesamt=2)

    monkeypatch.setattr("app.chat.router._kosten_des_zuges", kosten)
    monkeypatch.setattr("app.litellm.client.LiteLLMClient", _KeinClient)

    await kosten_nachtrag.nachtragen(
        _factory(protokoll), message_id=msg, conversation_id=conv,
        request_ids=["a", "b"], wartezeiten=(0.0,),
    )

    sql = " ".join(str(s) for s in protokoll)
    assert "UPDATE messages" in sql
    assert "UPDATE conversations" in sql
    assert "commit" in protokoll


@pytest.mark.asyncio
async def test_ohne_betrag_wird_nur_der_zustand_gesetzt(monkeypatch):
    """Nichts gefunden heißt: kein Betrag addieren, aber sagen, dass es fehlt."""
    protokoll = []

    async def kosten(client, ids, *, wartezeiten):
        from app.chat.router import Zugkosten
        return Zugkosten(summe=None, gefunden=0, gesamt=2)

    monkeypatch.setattr("app.chat.router._kosten_des_zuges", kosten)
    monkeypatch.setattr("app.litellm.client.LiteLLMClient", _KeinClient)

    await kosten_nachtrag.nachtragen(
        _factory(protokoll), message_id=uuid4(), conversation_id=uuid4(),
        request_ids=["a"], wartezeiten=(0.0,),
    )

    sql = " ".join(str(s) for s in protokoll)
    assert "UPDATE messages" in sql
    # Die Konversationssumme bleibt unangetastet — es gibt nichts zu addieren.
    assert "UPDATE conversations" not in sql


@pytest.mark.asyncio
async def test_fehler_bleibt_im_log_und_reisst_nichts_mit(monkeypatch, caplog):
    """Der Chat ist an dieser Stelle fertig; ein Fehler darf ihn nicht stören."""
    async def kaputt(client, ids, *, wartezeiten):
        raise RuntimeError("LiteLLM weg")

    monkeypatch.setattr("app.chat.router._kosten_des_zuges", kaputt)
    monkeypatch.setattr("app.litellm.client.LiteLLMClient", _KeinClient)

    aufgabe = kosten_nachtrag.nachtragen(
        _factory([]), message_id=uuid4(), conversation_id=uuid4(),
        request_ids=["a"], wartezeiten=(0.0,),
    )
    await aufgabe  # kein Ausbruch
    assert aufgabe.done() and aufgabe.exception() is None


@pytest.mark.asyncio
async def test_aufgabe_wird_festgehalten_und_wieder_freigegeben(monkeypatch):
    """Ohne starke Referenz darf der Garbage Collector sie einsammeln."""
    async def langsam(client, ids, *, wartezeiten):
        from app.chat.router import Zugkosten
        await asyncio.sleep(0.05)
        return Zugkosten(summe=0.001, gefunden=1, gesamt=1)

    monkeypatch.setattr("app.chat.router._kosten_des_zuges", langsam)
    monkeypatch.setattr("app.litellm.client.LiteLLMClient", _KeinClient)

    vorher = hintergrund.offene_anzahl()
    aufgabe = kosten_nachtrag.nachtragen(
        _factory([]), message_id=uuid4(), conversation_id=uuid4(),
        request_ids=["a"], wartezeiten=(0.0,),
    )
    assert hintergrund.offene_anzahl() == vorher + 1
    await aufgabe
    await asyncio.sleep(0)  # Callback laufen lassen
    assert hintergrund.offene_anzahl() == vorher


@pytest.mark.asyncio
async def test_herunterfahren_wartet_auf_offene_nachtraege(monkeypatch):
    protokoll = []

    async def langsam(client, ids, *, wartezeiten):
        from app.chat.router import Zugkosten
        await asyncio.sleep(0.05)
        return Zugkosten(summe=0.001, gefunden=1, gesamt=1)

    monkeypatch.setattr("app.chat.router._kosten_des_zuges", langsam)
    monkeypatch.setattr("app.litellm.client.LiteLLMClient", _KeinClient)

    kosten_nachtrag.nachtragen(
        _factory(protokoll), message_id=uuid4(), conversation_id=uuid4(),
        request_ids=["a"], wartezeiten=(0.0,),
    )
    await hintergrund.warte_auf_abschluss(frist=2.0)

    # Der Nachtrag ist durch — nicht abgeschnitten.
    assert "commit" in protokoll
    assert hintergrund.offene_anzahl() == 0


@pytest.mark.asyncio
async def test_herunterfahren_gibt_nach_der_frist_auf(monkeypatch, caplog):
    """Was die Frist nicht schafft, bleibt auf `ausstehend` — ehrlicher als ein
    Betrag, der nie kam, sich aber endgültig liest."""
    async def endlos(client, ids, *, wartezeiten):
        await asyncio.sleep(30)

    monkeypatch.setattr("app.chat.router._kosten_des_zuges", endlos)
    monkeypatch.setattr("app.litellm.client.LiteLLMClient", _KeinClient)

    kosten_nachtrag.nachtragen(
        _factory([]), message_id=uuid4(), conversation_id=uuid4(),
        request_ids=["a"], wartezeiten=(0.0,),
    )
    with caplog.at_level("WARNING", logger="app.chat.kosten_nachtrag"):
        await hintergrund.warte_auf_abschluss(frist=0.05)

    assert any("abgebrochen" in r.getMessage() for r in caplog.records)


class _KeinClient:
    """LiteLLM-Client-Ersatz — die Kostenermittlung ist ohnehin gemockt."""

    def __init__(self, *a, **kw):
        pass

    async def close(self):
        pass
