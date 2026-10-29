"""Assistenten-Vorschlag im Chat (Päckchen C2, Schritt 2) — der Dienst gegen die Datenbank.

Vektoren mit drei Stellen (wie `test_assistent_ausloeser.py`); der Klassifikator ist ersetzt —
gemessen wird er in `scripts/assistent_vorschlag_klassifikator.py`. Erfordert TEST_DATABASE_URL.
"""
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assistants import vorschlag as dienst
from app.assistants.sichtbarkeit import Zugang
from app.config import settings
from app.db.models import Assistant, AssistantTriggerExample

pytestmark = pytest.mark.asyncio

PRAEFIX = "VOR "
NACHRICHT = [1.0, 0.0, 0.0]
ZUGANG = Zugang(pseudonym="vor-test", rollen=frozenset({"student"}), gruppen=frozenset(),
                lehrgruppen=frozenset(), stufe=9)


@pytest_asyncio.fixture
async def sitzungen(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    yield fabrik
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.name.like(f"{PRAEFIX}%")))
        await db.commit()


async def _assistent(db, name, suggest, beispiele, gegen=(), scope="all_students", modell=None, **mehr):
    a = Assistant(name=PRAEFIX + name, system_prompt="P", model="", audience="student", scope=scope,
                  status="active", suggest=suggest, fallbacks=[], suggestion_text=f"Hilfe für {name}", **mehr)
    db.add(a)
    await db.flush()
    for art, vektoren in (("beispiel", beispiele), ("gegenbeispiel", gegen)):
        for n, v in enumerate(vektoren):
            db.add(AssistantTriggerExample(assistant_id=a.id, art=art, text_=f"{name} {art} {n}", position=n,
                                           embedding=v, embedding_model=modell or settings.embedding_model))
    return a


@pytest_asyncio.fixture
async def bestand(sitzungen):
    async with sitzungen() as db:
        rueck = await _assistent(db, "NW", "fallback", [[1.0, 0.6, 0.0]])            # ~0,14
        stoech = await _assistent(db, "Stöchio", "specific", [[1.0, 0.1, 0.0], [0.0, 1.0, 0.0]])  # ~0,005
        stoech.fallbacks = [rueck.id]
        await _assistent(db, "Fern", "specific", [[0.0, 0.0, 1.0]])                 # 1,0
        await _assistent(db, "Nie", "never", [[1.0, 0.0, 0.0]])
        await _assistent(db, "Privat", "specific", [[1.0, 0.0, 0.0]], scope="private")
        await _assistent(db, "Versteckt", "specific", [[1.0, 0.0, 0.0]], visibility="hidden")
        await _assistent(db, "Altes Modell", "specific", [[1.0, 0.0, 0.0]], modell="anderes-modell")
        await db.commit()
        return {"nw": rueck.id, "stoech": stoech.id}


async def _vorschlag(sitzungen, antwort='{"spezifisch": [], "rueckfall": []}', **mehr):
    werte = dict(nachricht="Wie viel Gramm …", vektor=NACHRICHT, zugang=ZUGANG, aktuell_id=None,
                 schon_vorgeschlagen=set(), konversationsfach=None, client=None) | mehr
    k = AsyncMock(return_value={"roh": antwort, "dauer": 0.1})
    with patch.object(dienst, "klassifiziere", k), patch.object(settings, "vorschlag_model", "system-vorschlag"):
        async with sitzungen() as db:
            return await dienst.vorschlagen(db, **werte), k


def _ids(v):
    return [o.assistant_id for o in v.optionen] if v else []


async def test_treffer_mit_rueckfall_aus_fallbacks(sitzungen, bestand):
    v, k = await _vorschlag(sitzungen, f'{{"spezifisch": [{bestand["stoech"]}], "rueckfall": []}}')
    assert _ids(v) == [bestand["stoech"], bestand["nw"]]
    band = [c.name for c in k.await_args.args[1]]
    # Im Band nur Sichtbare mit Vorschlag und Beispielen des eingestellten Modells — nicht „Fern“.
    assert band == [PRAEFIX + "Stöchio", PRAEFIX + "NW"]
    assert all(len(c.beispiele) >= 1 for c in k.await_args.args[1])


async def test_klassifikator_sagt_keiner(sitzungen, bestand):
    v, _ = await _vorschlag(sitzungen)
    assert v is None


async def test_ohne_kandidat_im_band_kein_aufruf(sitzungen, bestand):
    v, k = await _vorschlag(sitzungen, vektor=[0.0, -1.0, 0.0])
    assert v is None and not k.await_count


async def test_ruheregel_filtert_das_ergebnis_nicht_die_kandidaten(sitzungen, bestand):
    """Probe 28.10.2026: Ohne den schon angebotenen Assistenten wählte der Klassifikator den
    nächstbesten Nachbarn. Er sieht ihn also weiter — gezeigt wird er nicht mehr."""
    v, k = await _vorschlag(sitzungen, f'{{"spezifisch": [{bestand["stoech"]}], "rueckfall": []}}',
                            schon_vorgeschlagen={bestand["stoech"]})
    assert PRAEFIX + "Stöchio" in [c.name for c in k.await_args.args[1]]
    assert _ids(v) == [bestand["nw"]]                 # sein Rückfall bleibt
    v, _ = await _vorschlag(sitzungen, f'{{"spezifisch": [{bestand["stoech"]}], "rueckfall": []}}',
                            schon_vorgeschlagen={bestand["stoech"], bestand["nw"]})
    assert v is None


async def test_ohne_modell_kein_vorschlag(sitzungen, bestand):
    k = AsyncMock()
    with patch.object(dienst, "klassifiziere", k), patch.object(settings, "vorschlag_model", ""):
        async with sitzungen() as db:
            v = await dienst.vorschlagen(db, nachricht="x", vektor=NACHRICHT, zugang=ZUGANG, aktuell_id=None,
                                         schon_vorgeschlagen=set(), konversationsfach=None, client=None)
    assert v is None and not k.await_count


async def _im_assistenten(sitzungen, antwort='{"neue_aufgabe": null}', **mehr):
    werte = dict(nachricht="Wie viel Gramm …", vektor=NACHRICHT, zugang=ZUGANG, schon_vorgeschlagen=set(),
                 konversationsfach=None, client=None, letzte_antwort="Welche Größe fehlt dir noch?") | mehr
    k = AsyncMock(return_value={"roh": antwort, "dauer": 0.1})
    with patch.object(dienst, "_aufruf", k), patch.object(settings, "vorschlag_model", "system-vorschlag"):
        async with sitzungen() as db:
            return await dienst.vorschlagen(db, **werte), k


async def test_in_der_assistenten_konversation_entscheidet_der_klassifikator(sitzungen, bestand):
    """Jan, 29.10.2026 (nach k5-1): Liegt ein anderer Assistent näher als 0,45, fragt der
    Klassifikator — mit der letzten Nachricht des Assistenten als Kontext."""
    v, k = await _im_assistenten(sitzungen, f'{{"neue_aufgabe": {bestand["stoech"]}}}', aktuell_id=bestand["nw"])
    assert _ids(v) == [bestand["stoech"]]
    system, inhalt = k.await_args.args
    assert system == dienst.SYSTEM_IM_ASSISTENTEN
    assert "Welche Größe fehlt dir noch?" in inhalt and "Assistent für VOR NW" in inhalt
    assert f"Kennung {bestand['stoech']}" in inhalt
    # Laufendes Gespräch, fremde Kennung oder Unlesbares: bleiben.
    for roh in ('{"neue_aufgabe": null}', '{"neue_aufgabe": 999}', "weiß nicht"):
        v, _ = await _im_assistenten(sitzungen, roh, aktuell_id=bestand["nw"])
        assert v is None
    # Schon angeboten: nicht noch einmal.
    v, _ = await _im_assistenten(sitzungen, f'{{"neue_aufgabe": {bestand["stoech"]}}}', aktuell_id=bestand["nw"],
                                 schon_vorgeschlagen={bestand["stoech"]})
    assert v is None


async def test_in_der_assistenten_konversation_ohne_kandidat_kein_aufruf(sitzungen, bestand):
    # Nachricht weit weg von allem: bleiben, ohne Aufruf — und nie „beenden“.
    v, k = await _im_assistenten(sitzungen, aktuell_id=bestand["stoech"], vektor=[0.0, 0.0, -1.0])
    assert v is None and not k.await_count
