"""Die Bausteine einer Antwort kennen und behalten (0.14, Schritt 2).

„Gefunden, nicht verwendet": Festgehalten wird, was beim Antworten vorlag — die Treffer
der Vorab-Suche (`vorab`) und was die Suchwerkzeuge dem Modell lieferten (`werkzeug`).
Der Ankerkontext eines Assistenten gehört **nicht** dazu. Gespeichert wird im selben
Commit wie die Antwort; die Verweise verschwinden mit der Nachricht und mit dem Baustein.

Die Testdatenbank enthält Knoten anderer Module; geprüft wird deshalb, ob die hier
angelegten Knoten in der Liste stehen (oder fehlen), nicht die ganze Liste.
"""
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import psycopg2
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.context.bausteine import (
    VORAB, WERKZEUG, Baustein, aus_treffern, speichere, vereinige,
)
from app.db.models import ContextNode, Conversation, Message, MessageContextNode


_TITEL = ("Bausteinprobe%", "Anker% Bausteine", "Werkzeugprobe%", "Persistprobe%")


@pytest.fixture(autouse=True)
def _aufraeumen(db_url, run_migrations):
    """Die Knoten hier sind Vorab-Typen mit Vektor — blieben sie stehen, tauchten sie in
    der Vorab-Suche späterer Module auf."""
    yield
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        for muster in _TITEL:
            cur.execute("DELETE FROM context_nodes WHERE title LIKE %s", (muster,))
        cur.execute("DELETE FROM conversations WHERE pseudonym = 'bausteine-probe'")
    conn.commit()
    conn.close()


# ── reine Regeln ─────────────────────────────────────────────────────────────


def test_aus_treffern_rechnet_aehnlichkeit_und_laesst_fremde_formen_weg():
    treffer = [
        {"node_id": "a", "title": "Oxidation", "content_type": "begriff", "fach": "Chemie",
         "distanz": 0.249},
        {"node_id": "b", "title": "Wasser", "content_type": "begriff", "fach": None},
        {"operatoren": ["nennen"]},          # fremde Form (z. B. get_operatoren)
        "kein dict",
    ]
    bausteine = aus_treffern(treffer, VORAB)
    assert [b.node_id for b in bausteine] == ["a", "b"]
    assert bausteine[0].aehnlichkeit == 0.751
    assert bausteine[1].aehnlichkeit is None   # Treffer über den Namen: nicht „ähnlich"
    assert {b.herkunft for b in bausteine} == {VORAB}


def test_vereinige_jeder_einmal_in_der_reihenfolge_des_ersten_auftretens():
    vorab = [Baustein("a", "A", None, None, VORAB), Baustein("b", "B", None, None, VORAB)]
    runde1 = [Baustein("b", "B", None, None, WERKZEUG), Baustein("c", "C", None, None, WERKZEUG)]
    runde2 = [Baustein("c", "C", None, None, WERKZEUG), Baustein("d", "D", None, None, WERKZEUG)]
    ergebnis = vereinige(vorab, runde1, runde2)
    assert [b.node_id for b in ergebnis] == ["a", "b", "c", "d"]
    # Was vorab da war, bleibt `vorab` — es lag vor, bevor das Modell suchte.
    assert ergebnis[1].herkunft == VORAB


# ── Kontext: Bausteine = Treffer der Vorab-Suche ─────────────────────────────


def _sync(db_url):
    return db_url.replace("postgresql+asyncpg://", "postgresql://")


def _breite(db_url) -> int:
    conn = psycopg2.connect(_sync(db_url))
    with conn.cursor() as cur:
        cur.execute("SELECT atttypmod FROM pg_attribute WHERE attrelid = "
                    "'context_nodes'::regclass AND attname = 'embedding'")
        breite = cur.fetchone()[0]
    conn.close()
    return breite


def _vektor(breite: int, index: int) -> list[float]:
    v = [0.0] * breite
    v[index] = 1.0
    return v


def _knoten_sync(db_url, *, titel, content_type, category, vektor, content="Text."):
    conn = psycopg2.connect(_sync(db_url))
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO context_nodes (category, content_type, title, content, read_scope, "
            "write_scope, status, embedding) VALUES (%s, %s, %s, %s, 'school', 'school', "
            "'active', %s) RETURNING id",
            (category, content_type, titel, content, "[" + ",".join(map(str, vektor)) + "]"),
        )
        node_id = str(cur.fetchone()[0])
    conn.commit()
    conn.close()
    return node_id


@pytest.mark.asyncio
async def test_bausteine_sind_die_vorab_treffer_und_der_text_bleibt(db_session, db_url):
    from app.context.service import get_context_for_query, kontext_fuer_frage

    breite = _breite(db_url)
    vektor = _vektor(breite, breite - 11)     # eine Richtung, die sonst niemand benutzt
    node_id = _knoten_sync(db_url, titel="Bausteinprobe Oxidation", content_type="begriff",
                           category="concept", vektor=vektor)

    with patch("app.context.search.generate_embedding", new=AsyncMock(return_value=vektor)):
        kontext = await kontext_fuer_frage(None, "bausteine-probe", "Bausteinprobe Frage",
                                           None, db_session)
        text = await get_context_for_query(None, "bausteine-probe", "Bausteinprobe Frage",
                                           None, db_session)

    treffer = [b for b in kontext.bausteine if b.node_id == node_id]
    assert len(treffer) == 1
    assert treffer[0].herkunft == VORAB
    assert treffer[0].titel == "Bausteinprobe Oxidation"
    assert treffer[0].aehnlichkeit == 1.0
    # Die Hülle liefert denselben Text — sie baut nichts eigenes.
    assert kontext.text == text
    # Die Distanz geht nicht in den Prompt.
    assert "distanz" not in kontext.text


@pytest.mark.asyncio
async def test_ankerkontext_gehoert_nicht_in_die_liste(db_session, db_url, seed_test_assistant):
    """Der Gegenstand eines Assistenten ist nicht die Antwort auf diese Frage."""
    from app.context.service import kontext_fuer_frage

    breite = _breite(db_url)
    vektor = _vektor(breite, breite - 12)
    anker = _knoten_sync(db_url, titel="Ankereinheit Bausteine", content_type="unterrichtseinheit",
                         category="artifact", vektor=_vektor(breite, breite - 13))
    # Eine Kompetenz ist kein Vorab-Typ — sie kommt nur über den Anker in den Prompt.
    kind = _knoten_sync(db_url, titel="Ankerkompetenz Bausteine", content_type="ik_kompetenz",
                        category="knowledge", vektor=vektor)
    conn = psycopg2.connect(_sync(db_url))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO context_edges (from_node_id, to_node_id, relation) "
                    "VALUES (%s, %s, 'part_of')", (kind, anker))
        cur.execute("INSERT INTO assistant_context_anchors (assistant_id, node_id, role) "
                    "VALUES (%s, %s, 'retrieval_scope')", (seed_test_assistant, anker))
    conn.commit()
    try:
        with patch("app.context.search.generate_embedding", new=AsyncMock(return_value=vektor)):
            kontext = await kontext_fuer_frage(seed_test_assistant, "bausteine-probe",
                                               "Ankerkompetenz", None, db_session)
        assert "Ankerkompetenz Bausteine" in kontext.text      # im Prompt …
        assert kind not in {b.node_id for b in kontext.bausteine}   # … aber nicht in der Liste
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM assistant_context_anchors WHERE node_id = %s", (anker,))
        conn.commit()
        conn.close()


# ── Werkzeuge sammeln ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_suchwerkzeug_sammelt_was_es_dem_modell_liefert(db_session, db_url):
    from app.chat.router import _search_context_nodes_handler
    from app.chat.tools import ToolContext
    from app.auth.jwt import JwtPayload

    breite = _breite(db_url)
    vektor = _vektor(breite, breite - 14)
    node_id = _knoten_sync(db_url, titel="Werkzeugprobe Stoffmenge", content_type="begriff",
                           category="concept", vektor=vektor)
    sammler: list = []
    ctx = ToolContext(db=db_session, user=JwtPayload.model_construct(sub="werkzeug-probe",
                      roles=["teacher"], grade=None), group_id=None, conversation_id=None,
                      bausteine=sammler)
    with patch("app.context.search.generate_embedding", new=AsyncMock(return_value=vektor)):
        antwort = await _search_context_nodes_handler({"query": "Werkzeugprobe Stoffmenge"}, ctx)

    gesammelt = [b for b in sammler if b.node_id == node_id]
    assert gesammelt and gesammelt[0].herkunft == WERKZEUG
    geliefert = (antwort["exakte_namenstraeger"] + antwort["aehnlich_benannte_bausteine"]
                 + antwort["naechstliegende_bausteine"])
    # Gesammelt wird genau, was das Modell bekam — nicht mehr, nicht weniger.
    assert len(sammler) == len(geliefert)


# ── Speichern: im selben Commit, Kaskaden, gelöschter Baustein ───────────────


@pytest.fixture
def sitzungen(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def _konversation(sitzungen) -> UUID:
    async with sitzungen() as db:
        konv = Conversation(pseudonym="bausteine-probe", model_used="model-x")
        db.add(konv)
        await db.commit()
        return konv.id


async def _verweise(sitzungen, message_id) -> list[tuple]:
    async with sitzungen() as db:
        return (await db.execute(
            sa.select(MessageContextNode.node_id, MessageContextNode.position,
                      MessageContextNode.herkunft, MessageContextNode.aehnlichkeit)
            .where(MessageContextNode.message_id == message_id)
            .order_by(MessageContextNode.position)
        )).all()


@pytest.mark.asyncio
async def test_persist_schreibt_die_bausteine_mit(sitzungen, db_url):
    from app.chat import router

    breite = _breite(db_url)
    a = _knoten_sync(db_url, titel="Persistprobe A", content_type="begriff", category="concept",
                     vektor=_vektor(breite, 1))
    b = _knoten_sync(db_url, titel="Persistprobe B", content_type="begriff", category="concept",
                     vektor=_vektor(breite, 2))
    konv = await _konversation(sitzungen)
    bausteine = [Baustein(a, "A", "begriff", None, VORAB, 0.9),
                 Baustein(b, "B", "begriff", None, WERKZEUG)]
    async with sitzungen() as db:
        message_id = await router._persist(db, konv, "frage", [], "antwort", {}, "model-x",
                                           bausteine=bausteine)

    assert await _verweise(sitzungen, message_id) == [
        (UUID(a), 0, VORAB, pytest.approx(0.9)), (UUID(b), 1, WERKZEUG, None),
    ]

    # Kaskade über den Baustein …
    async with sitzungen() as db:
        await db.execute(sa.delete(ContextNode).where(ContextNode.id == UUID(a)))
        await db.commit()
    assert [z[0] for z in await _verweise(sitzungen, message_id)] == [UUID(b)]
    # … und über die Nachricht.
    async with sitzungen() as db:
        await db.execute(sa.delete(Message).where(Message.id == message_id))
        await db.commit()
    assert await _verweise(sitzungen, message_id) == []


@pytest.mark.asyncio
async def test_geloeschter_baustein_kippt_die_antwort_nicht(sitzungen):
    """Zwischen Suche und Speichern vergehen Sekunden — ein gelöschter Baustein darf die
    Antwort nicht mitreißen."""
    from app.chat import router

    konv = await _konversation(sitzungen)
    weg = Baustein(str(uuid4()), "Gibt es nicht mehr", "begriff", None, VORAB)
    async with sitzungen() as db:
        message_id = await router._persist(db, konv, "frage", [], "antwort", {}, "model-x",
                                           bausteine=[weg])
    assert message_id is not None
    assert await _verweise(sitzungen, message_id) == []


@pytest.mark.asyncio
async def test_speichere_ohne_bausteine_tut_nichts(db_session):
    await speichere(db_session, uuid4(), [])     # keine Abfrage, kein Fehler
