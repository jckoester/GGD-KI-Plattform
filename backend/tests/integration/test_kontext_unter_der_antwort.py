"""Die Liste unter der Antwort (0.14, Schritt 3).

Live (SSE `kontext`) und nach dem Neuladen (`message.kontext`) kommt die Liste aus
**derselben** Abfrage, `kontext_der_nachrichten`. Geprüft wird hier die Abfrage selbst und
der Ladeweg; dass der Stream sie benutzt, prüft `tests/unit/test_chat_models.py`.
"""
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.context.bausteine import VORAB, WERKZEUG, kontext_der_nachrichten
from app.db.models import (
    ContextNode, Conversation, Message, MessageContextNode, Subject,
)
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def antwort(async_engine):
    """Eine Konversation von teacher1 mit einer Antwort und drei Bausteinen — einer davon
    gehört inzwischen privat jemand anderem."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    ids: dict = {}
    async with factory() as s:
        fach = Subject(slug=f"kontextprobe-{uuid4().hex[:6]}", name="Kontextprobe-Chemie")
        s.add(fach)
        await s.flush()
        ids["fach"] = fach.id

        def knoten(titel, **extra):
            return ContextNode(category="concept", content_type="begriff", title=titel,
                               content="Text.", read_scope="school", write_scope="school",
                               status="active", **extra)

        # Die Reihenfolge nach `position` muss sich von jeder unterscheiden, die die
        # Datenbank sonst liefern könnte: Nach node_id und in jeder Einfügereihenfolge
        # (Knoten wie Verweise) kommt `ohne_fach` zuerst, nach `position` `mit_fach`.
        klein, gross = sorted([uuid4(), uuid4()])
        ohne_fach = knoten("Kontextprobe Wasser", id=klein)
        mit_fach = knoten("Kontextprobe Oxidation", subject_id=fach.id, id=gross,
                          metadata_={"fassung": "Elektronenabgabe"})
        fremd_privat = knoten("Kontextprobe Geheim")
        for k in (ohne_fach, mit_fach, fremd_privat):
            s.add(k)
            await s.flush()

        konv = Conversation(id=uuid4(), pseudonym=TEACHER1_PSEUDO, model_used="model-x")
        s.add(konv)
        await s.flush()
        frage = Message(conversation_id=konv.id, role="user", content="Was ist Oxidation?")
        s.add(frage)
        await s.flush()
        antwort = Message(conversation_id=konv.id, role="assistant", content="Antwort.")
        ohne = Message(conversation_id=konv.id, role="assistant", content="Ohne Bausteine.")
        s.add_all([antwort, ohne])
        await s.flush()
        # Einzeln geschrieben, damit die Einfügereihenfolge feststeht.
        for verweis in (
            MessageContextNode(message_id=antwort.id, node_id=ohne_fach.id, position=1,
                               herkunft=WERKZEUG),
            MessageContextNode(message_id=antwort.id, node_id=mit_fach.id, position=0,
                               herkunft=VORAB, aehnlichkeit=0.616),
            MessageContextNode(message_id=antwort.id, node_id=fremd_privat.id, position=2,
                               herkunft=VORAB),
        ):
            s.add(verweis)
            await s.flush()
        await s.commit()
        # Nach dem Antworten privat geworden — für teacher1 nicht mehr lesbar.
        fremd_privat.read_scope = "private"
        fremd_privat.write_scope = "private"
        fremd_privat.owner_pseudonym = "jemand-anderes"
        await s.commit()
        ids.update(konv=konv.id, frage=frage.id, antwort=antwort.id, ohne=ohne.id,
                   mit_fach=mit_fach.id, ohne_fach=ohne_fach.id, fremd=fremd_privat.id)

    yield ids

    async with factory() as s:
        await s.execute(sa.delete(Conversation).where(Conversation.id == ids["konv"]))
        await s.execute(sa.delete(ContextNode).where(ContextNode.title.like("Kontextprobe %")))
        await s.execute(sa.delete(Subject).where(Subject.id == ids["fach"]))
        await s.commit()


async def test_liste_in_gespeicherter_reihenfolge_mit_fach_und_datum(db_session, antwort):
    ergebnis = await kontext_der_nachrichten(
        db_session, [antwort["antwort"], antwort["ohne"]], TEACHER1_PSEUDO, ["teacher"],
    )
    liste = ergebnis[antwort["antwort"]]
    assert [b.node_id for b in liste] == [antwort["mit_fach"], antwort["ohne_fach"]]
    erster, zweiter = liste
    assert (erster.title, erster.fassung, erster.fach, erster.herkunft) == (
        "Kontextprobe Oxidation", "Elektronenabgabe", "Kontextprobe-Chemie", VORAB)
    assert erster.aehnlichkeit == pytest.approx(0.616)
    assert erster.updated_at is not None
    assert (zweiter.fassung, zweiter.fach, zweiter.herkunft, zweiter.aehnlichkeit) == (
        None, None, WERKZEUG, None)
    # Eine Antwort ohne Bausteine fehlt — sie bekommt keine (leere) Liste.
    assert antwort["ohne"] not in ergebnis


async def test_nicht_mehr_lesbarer_baustein_verschwindet_aus_der_liste(db_session, antwort):
    """Auch für Admins: Fremde private Knoten sieht niemand (read_scope_clause)."""
    for rollen in (["teacher"], ["teacher", "admin"]):
        ergebnis = await kontext_der_nachrichten(
            db_session, [antwort["antwort"]], TEACHER1_PSEUDO, rollen,
        )
        assert antwort["fremd"] not in {b.node_id for b in ergebnis[antwort["antwort"]]}
    # Die Eigentümerin sieht ihn weiter.
    eigen = await kontext_der_nachrichten(db_session, [antwort["antwort"]], "jemand-anderes")
    assert antwort["fremd"] in {b.node_id for b in eigen[antwort["antwort"]]}


async def test_ohne_nachrichten_keine_abfrage(db_session):
    assert await kontext_der_nachrichten(db_session, [], TEACHER1_PSEUDO) == {}


async def test_neuladen_liefert_die_liste_an_der_antwort(test_client, auth_headers, antwort):
    resp = await test_client.get(f"/conversations/{antwort['konv']}/messages",
                                 headers=auth_headers)
    assert resp.status_code == 200, resp.text
    nachrichten = {m["id"]: m for m in resp.json()["messages"]}

    liste = nachrichten[str(antwort["antwort"])]["kontext"]
    assert [b["node_id"] for b in liste] == [str(antwort["mit_fach"]), str(antwort["ohne_fach"])]
    assert set(liste[0]) == {"node_id", "title", "fassung", "content_type", "fach",
                             "herkunft", "aehnlichkeit", "updated_at"}
    assert liste[0]["fach"] == "Kontextprobe-Chemie"
    assert nachrichten[str(antwort["ohne"])]["kontext"] == []
    assert nachrichten[str(antwort["frage"])]["kontext"] == []
