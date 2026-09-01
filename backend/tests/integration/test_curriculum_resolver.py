"""Integrationstests für resolve_group_curricula (UP-Phase-3a).

Seeding läuft über die transaktionale db_session-Fixture (Rollback pro Test).
"""

import pytest

from app.db.models import ContextEdge, ContextNode, Group, Subject
from app.planning.curriculum_resolver import resolve_group_curricula

SUBJECT_ID = 900
SUBJECT_NO_CURR = 901


async def _kapitel(db, curriculum, titel, reihenfolge, std=None):
    node = ContextNode(
        category="knowledge",
        content_type="kapitel",
        title=titel,
        subject_id=curriculum.subject_id,
        metadata_={"reihenfolge": reihenfolge, "std": std},
    )
    db.add(node)
    await db.flush()
    db.add(ContextEdge(from_node_id=node.id, to_node_id=curriculum.id, relation="part_of"))
    await db.flush()
    return node


async def _curriculum(db, titel, min_grade, max_grade, jg):
    node = ContextNode(
        category="knowledge",
        content_type="curriculum",
        title=titel,
        subject_id=SUBJECT_ID,
        min_grade=min_grade,
        max_grade=max_grade,
        metadata_={"jahrgangsstufe": jg},
    )
    db.add(node)
    await db.flush()
    return node


async def _seed(db):
    """Legt Fach, Klassengruppen, teaching_groups und zwei Curricula an."""
    db.add(Subject(id=SUBJECT_ID, slug="mathe-res", name="Mathe Resolver", sort_order=0))
    db.add(Subject(id=SUBJECT_NO_CURR, slug="ohne-curr", name="Ohne Curr", sort_order=1))
    await db.flush()  # Subjects vor den Groups (FK groups.subject_id)
    db.add_all([
        Group(id=910, name="5a", slug="cls-5a", type="school_class"),
        Group(id=911, name="6a", slug="cls-6a", type="school_class"),
        Group(id=920, name="5a Mathe", slug="tg-5a-m", type="teaching_group",
              subject_id=SUBJECT_ID, source_class_group_id=910),
        Group(id=921, name="6a Mathe", slug="tg-6a-m", type="teaching_group",
              subject_id=SUBJECT_ID, source_class_group_id=911),
        Group(id=922, name="Kurs ohne Klasse", slug="tg-nograde", type="teaching_group",
              subject_id=SUBJECT_ID, source_class_group_id=None),
        Group(id=923, name="Fach ohne Curr", slug="tg-nocurr", type="teaching_group",
              subject_id=SUBJECT_NO_CURR, source_class_group_id=910),
    ])
    await db.flush()

    cur5 = await _curriculum(db, "Mathe Kl. 5", 5, 5, "5")
    cur56 = await _curriculum(db, "Mathe Kl. 5/6", 5, 6, "5/6")
    # Reihenfolge absichtlich verdreht eingefügt → Resolver muss sortieren
    await _kapitel(db, cur5, "Kapitel B", reihenfolge=2, std=10)
    await _kapitel(db, cur5, "Kapitel A", reihenfolge=1, std=8)
    await _kapitel(db, cur56, "Band-Kapitel", reihenfolge=1, std=12)
    await db.flush()
    return cur5, cur56


@pytest.mark.asyncio
async def test_grade5_matcht_beide_ueberlappenden_curricula(db_session):
    await _seed(db_session)
    res = await resolve_group_curricula(db_session, 920)

    assert res.grade == 5
    assert res.grade_unbekannt is False
    titel = {c.titel for c in res.curricula}
    assert titel == {"Mathe Kl. 5", "Mathe Kl. 5/6"}


@pytest.mark.asyncio
async def test_kapitel_nach_reihenfolge_sortiert(db_session):
    await _seed(db_session)
    res = await resolve_group_curricula(db_session, 920)

    cur5 = next(c for c in res.curricula if c.titel == "Mathe Kl. 5")
    assert [k.titel for k in cur5.kapitel] == ["Kapitel A", "Kapitel B"]
    assert cur5.kapitel[0].std == 8


@pytest.mark.asyncio
async def test_band_matcht_grade6_einzelstufe_nicht(db_session):
    await _seed(db_session)
    res = await resolve_group_curricula(db_session, 921)

    assert res.grade == 6
    titel = {c.titel for c in res.curricula}
    # Nur das 5/6-Band gilt für Klasse 6, nicht das reine Kl.-5-Curriculum
    assert titel == {"Mathe Kl. 5/6"}


@pytest.mark.asyncio
async def test_grade_unbekannt_liefert_alle_curricula(db_session):
    await _seed(db_session)
    res = await resolve_group_curricula(db_session, 922)

    assert res.grade is None
    assert res.grade_unbekannt is True
    titel = {c.titel for c in res.curricula}
    assert titel == {"Mathe Kl. 5", "Mathe Kl. 5/6"}


@pytest.mark.asyncio
async def test_fach_ohne_curriculum_leer(db_session):
    await _seed(db_session)
    res = await resolve_group_curricula(db_session, 923)

    assert res.curricula == []


@pytest.mark.asyncio
async def test_verknuepfte_ue_erscheint_am_kapitel(db_session):
    await _seed(db_session)
    # UE der Gruppe 920 anlegen und mit dem ersten Kapitel verknüpfen
    res_before = await resolve_group_curricula(db_session, 920)
    cur5_res = next(c for c in res_before.curricula if c.titel == "Mathe Kl. 5")
    kapitel_id = cur5_res.kapitel[0].id

    ue = ContextNode(
        category="artifact",
        content_type="unterrichtseinheit",
        title="Meine UE",
        write_scope="group",
        write_scope_group_id=920,
    )
    db_session.add(ue)
    await db_session.flush()
    db_session.add(ContextEdge(from_node_id=ue.id, to_node_id=kapitel_id, relation="references"))
    await db_session.flush()

    res = await resolve_group_curricula(db_session, 920)
    cur5_res = next(c for c in res.curricula if c.titel == "Mathe Kl. 5")
    target = next(k for k in cur5_res.kapitel if k.id == kapitel_id)
    assert "Meine UE" in target.ues


# ── group_grade: der Jahrgang allein, ohne Curriculum-Auflösung ──────────────
# Einstieg für die editionsbewusste Kontextsuche: Der Jahrgang entscheidet dort,
# welche BP-Fassung gilt.

@pytest.mark.asyncio
async def test_group_grade_liest_den_jahrgang_der_klassengruppe(db_session):
    from app.planning.curriculum_resolver import group_grade

    await _seed(db_session)

    assert await group_grade(db_session, 920) == 5
    assert await group_grade(db_session, 921) == 6


@pytest.mark.asyncio
async def test_group_grade_ohne_klassenbezug_ist_none(db_session):
    """Oberstufenkurs ohne Klassengruppe — der Jahrgang bleibt unbekannt."""
    from app.planning.curriculum_resolver import group_grade

    await _seed(db_session)

    assert await group_grade(db_session, 922) is None


@pytest.mark.asyncio
async def test_group_grade_unbekannte_gruppe_ist_none(db_session):
    from app.planning.curriculum_resolver import group_grade

    assert await group_grade(db_session, 99999) is None


@pytest.mark.asyncio
async def test_conversation_grade_folgt_der_unterrichtsgruppe(db_session):
    """Konversation mit Gruppenbezug -> Jahrgang; ohne Bezug -> None."""
    from app.context.service import _conversation_grade
    from app.db.models import Conversation

    await _seed(db_session)
    mit_gruppe = Conversation(pseudonym="p1", model_used="gpt-4o-mini", group_id=921)
    ohne_gruppe = Conversation(pseudonym="p1", model_used="gpt-4o-mini")
    db_session.add_all([mit_gruppe, ohne_gruppe])
    await db_session.flush()

    assert await _conversation_grade(db_session, mit_gruppe.id) == 6
    assert await _conversation_grade(db_session, ohne_gruppe.id) is None
    assert await _conversation_grade(db_session, None) is None


@pytest.mark.asyncio
async def test_kontext_string_filtert_nach_der_fassung_der_gruppe(db_session):
    """End-to-End über `get_context_for_query`: nur die geltende Fassung im Kontext.

    Deckt zugleich den Pfad ab, auf dem die Fassungs-Abfrage **innerhalb** des
    `asyncio.gather` mit dem Engagement-Retrieval auf derselben Session läuft.
    """
    from unittest.mock import AsyncMock, patch

    from app.config import settings
    from app.context.service import get_context_for_query
    from app.db.models import Assistant, AssistantContextAnchor, Conversation

    await _seed(db_session)

    def vec(pos):
        v = [0.0] * settings.embedding_dimensions
        v[pos] = 1.0
        return v

    anker = ContextNode(category="knowledge", content_type="fachplan",
                        title="Fachplan", subject_id=SUBJECT_ID, embedding=vec(0))
    db_session.add(anker)
    await db_session.flush()
    for bp_version, pos in (("2016.V2", 1), ("2016.V3", 2)):
        node = ContextNode(
            category="knowledge", content_type="ik_kompetenz",
            title=f"IK 3.1.1(1) {bp_version}",
            content=f"Kennzeichen der Fassung {bp_version}",
            subject_id=SUBJECT_ID, bp_version=bp_version,
            metadata_={"kompetenz_nr": "3.1.1(1)"}, embedding=vec(pos),
        )
        db_session.add(node)
        await db_session.flush()
        db_session.add(ContextEdge(from_node_id=node.id, to_node_id=anker.id,
                                   relation="part_of"))

    assistant = Assistant(name="Mathe-Helfer", system_prompt="Hilf.",
                          model="gpt-4o-mini", status="active")
    db_session.add(assistant)
    await db_session.flush()
    db_session.add(AssistantContextAnchor(assistant_id=assistant.id, node_id=anker.id,
                                          role="retrieval_scope"))
    # Gruppe 920 haengt an Klasse 5a -> Jahrgang 5 -> im SJ 2026/27 gilt V3.
    conv = Conversation(pseudonym="p1", model_used="gpt-4o-mini", group_id=920)
    db_session.add(conv)
    await db_session.flush()

    with patch("app.context.search.generate_embedding",
               new=AsyncMock(return_value=vec(1))), \
         patch("app.context.editions.aktuelles_schuljahr_start", return_value=2026):
        kontext = await get_context_for_query(
            assistant_id=assistant.id, pseudonym="p1",
            query_text="Zahlen", chat_id=conv.id, db=db_session,
        )

    assert "Kennzeichen der Fassung 2016.V3" in kontext
    assert "2016.V2" not in kontext
