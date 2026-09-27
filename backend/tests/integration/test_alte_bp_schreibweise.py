"""Was Alembic 0080 löscht — und vor allem, was es stehen lässt.

⚠️ **Eine Migration, die Zeilen löscht, prüft man vorher.** Die Bedingungen sind eng
formuliert, damit der Lauf selbstbegrenzend ist; ob sie das wirklich sind, zeigt sich
erst an Zeilen, die knapp danebenliegen. Jeder Fall hier ist so einer.

Gemessen im Dev-System (27.09.2026): 326 Zeilen, alle Mathematik `2016.V2`. Die 319
Knoten der Basisfassung tragen dieselbe alte Schreibweise und bleiben — dort ist die
ganze Edition archiviert, und das ist die legitime Bedeutung von „abgelöst".
"""
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.db.models import ChatContextNode, ContextEdge, ContextNode, Conversation, Subject

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migration():
    pfad = (
        Path(__file__).resolve().parents[2]
        / "alembic" / "versions" / "0080_alte_bp_schreibweise.py"
    )
    spec = importlib.util.spec_from_file_location("m0080", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture
async def fach(db_session):
    s = Subject(slug=f"altfach-{uuid.uuid4().hex[:8]}", name="Altfach")
    db_session.add(s)
    await db_session.flush()
    return s


async def _ik(db_session, fach, nr, *, status, version="2016.V2") -> ContextNode:
    node = ContextNode(
        category="knowledge", content_type="ik_kompetenz", title=f"{nr} irgendwas",
        content="x", subject_id=fach.id, bp_version=version, status=status,
        read_scope="school", write_scope="school",
        metadata_={"kompetenz_nr": nr},
    )
    db_session.add(node)
    await db_session.flush()
    return node


async def _laeuft(db_session, migration) -> None:
    await db_session.execute(
        sa.text(f"DELETE FROM context_nodes WHERE id IN ({migration.AUSWAHL})")
    )


async def _lebt(db_session, node) -> bool:
    return (await db_session.execute(
        sa.select(sa.func.count()).select_from(ContextNode)
        .where(ContextNode.id == node.id)
    )).scalar_one() == 1


class TestWasGeloeschtWird:
    async def test_alte_schreibweise_mit_aktivem_zwilling(
        self, db_session, fach, migration
    ):
        alt = await _ik(db_session, fach, "3.1.1.(1)", status="archived")
        neu = await _ik(db_session, fach, "3.1.1(1)", status="active")
        await _laeuft(db_session, migration)
        assert not await _lebt(db_session, alt)
        assert await _lebt(db_session, neu), "der aktive Knoten bleibt selbstverständlich"


class TestWasStehenBleibt:
    async def test_ohne_aktiven_zwilling(self, db_session, fach, migration):
        """Der Fall der Basisfassung: alte Schreibweise, aber nichts ersetzt sie.
        Löschen hieße hier, Inhalt ersatzlos wegzuwerfen."""
        alt = await _ik(db_session, fach, "3.1.1.(1)", status="archived")
        await _laeuft(db_session, migration)
        assert await _lebt(db_session, alt)

    async def test_zwilling_in_anderer_edition_zaehlt_nicht(
        self, db_session, fach, migration
    ):
        """⚠️ Editionen sind eigenständige Fassungen. Ein V3-Knoten derselben Nummer
        ist **nicht** der Ersatz für einen V2-Knoten — er sagt womöglich etwas
        anderes."""
        alt = await _ik(db_session, fach, "3.1.1.(1)", status="archived", version="2016.V2")
        await _ik(db_session, fach, "3.1.1(1)", status="active", version="2016.V3")
        await _laeuft(db_session, migration)
        assert await _lebt(db_session, alt)

    async def test_mit_eingehender_kante(self, db_session, fach, migration):
        """Ein Curriculum, eine Lernsequenz oder ein Fachbegriff zeigt darauf — dann
        ist es ein Re-Link, kein Löschlauf."""
        alt = await _ik(db_session, fach, "3.1.1.(1)", status="archived")
        await _ik(db_session, fach, "3.1.1(1)", status="active")
        quelle = await _ik(db_session, fach, "9.9.9(9)", status="active")
        db_session.add(ContextEdge(
            from_node_id=quelle.id, to_node_id=alt.id, relation="references",
            metadata_={},
        ))
        await db_session.flush()
        await _laeuft(db_session, migration)
        assert await _lebt(db_session, alt)

    async def test_in_einem_chat_angeheftet(self, db_session, fach, migration):
        """Im Dev-Bestand trifft das genau einen Knoten. Ihn wegzulöschen risse ein
        Loch in ein Gespräch, das jemand geführt hat."""
        alt = await _ik(db_session, fach, "3.1.1.(1)", status="archived")
        await _ik(db_session, fach, "3.1.1(1)", status="active")
        conv = Conversation(pseudonym="alt-schreibweise-probe", model_used="chat-standard")
        db_session.add(conv)
        await db_session.flush()
        db_session.add(ChatContextNode(chat_id=conv.id, node_id=alt.id))
        await db_session.flush()
        await _laeuft(db_session, migration)
        assert await _lebt(db_session, alt)

    async def test_neue_schreibweise_bleibt_auch_archiviert(
        self, db_session, fach, migration
    ):
        """Archiviert heißt hier „abgelöst" oder „Edition gilt noch nicht" — beides
        legitim. Die Migration räumt nur die dritte Bedeutung weg."""
        alt = await _ik(db_session, fach, "3.1.1(1)", status="archived")
        await _ik(db_session, fach, "3.1.1(2)", status="active")
        await _laeuft(db_session, migration)
        assert await _lebt(db_session, alt)

    async def test_anderer_knotentyp(self, db_session, fach, migration):
        node = ContextNode(
            category="knowledge", content_type="leitidee", title="3.1.1.(1) Leitidee",
            content="x", subject_id=fach.id, bp_version="2016.V2", status="archived",
            read_scope="school", write_scope="school",
            metadata_={"kompetenz_nr": "3.1.1.(1)"},
        )
        db_session.add(node)
        await db_session.flush()
        await _ik(db_session, fach, "3.1.1(1)", status="active")
        await _laeuft(db_session, migration)
        assert await _lebt(db_session, node)
