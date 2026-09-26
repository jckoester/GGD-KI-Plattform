"""Woher die Klassenstufe kommt (Paket 9, N5) und wie die Bänder entstehen (N6).

⚠️ **Die Reihenfolge ist die Aussage:** Unterrichtsgruppe vor Anmeldung. Eine
Zehntklässlerin im Chemie-Chat ihrer Klasse 10 ist dort in Klasse 10, auch wenn ihr
Konto etwas anderes sagt — Wiederholerin, Springerin, oder eine Schulkonto-Gruppe, die
nie nachgepflegt wurde.
"""
import uuid

import pytest
import sqlalchemy as sa

from app.context.service import stufe_der_person
from app.context.stufen import bp_baender_zu
from app.db.models import Conversation, ContextEdge, ContextNode, Group, Subject

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def gruppe_kl10(db_session):
    kennung = uuid.uuid4().hex[:8]
    fach = Subject(slug=f"chemie-{kennung}", name="Chemie T", fach_code="CHT")
    db_session.add(fach)
    await db_session.flush()
    gruppe = Group(
        name="CH 10a", slug=f"ch-10a-{kennung}", type="teaching_group",
        subject_id=fach.id, sso_group_id=f"ch10a-{kennung}", jahrgang=10,
    )
    db_session.add(gruppe)
    await db_session.flush()
    return gruppe, fach


class TestStufeDerPerson:
    async def test_gruppe_schlaegt_anmeldung(self, db_session, gruppe_kl10):
        gruppe, _ = gruppe_kl10
        chat = Conversation(pseudonym="p", group_id=gruppe.id, model_used="test")
        db_session.add(chat)
        await db_session.flush()

        assert await stufe_der_person(db_session, chat.id, "7") == 10

    async def test_ohne_gruppe_zaehlt_die_anmeldung(self, db_session):
        assert await stufe_der_person(db_session, None, "9") == 9

    async def test_unbekannt_bleibt_unbekannt(self, db_session):
        """Kein Rückfall auf eine Vorgabe: Sonst bekäme jeder Erwachsene ohne Jahrgang
        die Kennzeichnung einer Achtklässlerin."""
        assert await stufe_der_person(db_session, None, None) is None
        assert await stufe_der_person(db_session, None, "") is None
        assert await stufe_der_person(db_session, None, "Oberstufe") is None


class TestBpBaender:
    async def test_band_kommt_aus_der_kompetenz(self, db_session, gruppe_kl10):
        """⚠️ Die Bänder stehen in den Daten (`min_grade`/`max_grade` an der
        Kompetenz) — sie werden nicht nachgebaut."""
        _, fach = gruppe_kl10
        kompetenz = ContextNode(
            category="knowledge", content_type="ik_kompetenz", title="3.2.1.1(1) X",
            content="x", subject_id=fach.id, bp_version="2016.V2", status="active",
            read_scope="school", write_scope="school", min_grade=8, max_grade=10,
        )
        begriff = ContextNode(
            category="concept", content_type="begriff", title="Testbegriff",
            content="x", subject_id=fach.id, status="active",
            read_scope="school", write_scope="school",
        )
        db_session.add_all([kompetenz, begriff])
        await db_session.flush()
        db_session.add(ContextEdge(
            from_node_id=begriff.id, to_node_id=kompetenz.id,
            relation="references", metadata_={},
        ))
        await db_session.flush()

        treffer = [{"node_id": str(begriff.id), "content_type": "begriff",
                    "subject_id": fach.id}]
        assert await bp_baender_zu(db_session, treffer, 9) == {str(begriff.id): (8, 10)}

    async def test_archivierte_fundstelle_zaehlt_nicht(self, db_session, gruppe_kl10):
        """Im Dev-Bestand ist die ganze V3-Edition Chemie archiviert — zählte sie mit,
        bekäme jeder Begriff ein Band, das für niemanden gilt."""
        _, fach = gruppe_kl10
        kompetenz = ContextNode(
            category="knowledge", content_type="ik_kompetenz", title="3.1.2.1(1) X",
            content="x", subject_id=fach.id, bp_version="2016.V2", status="archived",
            read_scope="school", write_scope="school", min_grade=8, max_grade=10,
        )
        begriff = ContextNode(
            category="concept", content_type="begriff", title="Testbegriff 2",
            content="x", subject_id=fach.id, status="active",
            read_scope="school", write_scope="school",
        )
        db_session.add_all([kompetenz, begriff])
        await db_session.flush()
        db_session.add(ContextEdge(
            from_node_id=begriff.id, to_node_id=kompetenz.id,
            relation="references", metadata_={},
        ))
        await db_session.flush()

        treffer = [{"node_id": str(begriff.id), "content_type": "begriff",
                    "subject_id": fach.id}]
        assert await bp_baender_zu(db_session, treffer, 9) == {}

    async def test_ohne_treffer_keine_abfrage(self, db_session):
        assert await bp_baender_zu(db_session, [], 9) == {}
        assert await bp_baender_zu(
            db_session, [{"node_id": "x", "content_type": "arbeitsblatt"}], 9
        ) == {}
