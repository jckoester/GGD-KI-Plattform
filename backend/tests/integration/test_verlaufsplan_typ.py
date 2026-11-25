"""Jahresverlaufsplan: Datenbank-Regeln des Typs (Päckchen BD, Schritt 2, Alembic 0114).
Erfordert TEST_DATABASE_URL."""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from app.db.models import ContextNode, Subject

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]


def _plan(fach, stufe=9, schuljahr="2026/27", status="draft", typ="verlaufsplan"):
    return ContextNode(category="knowledge", content_type=typ, title=f"Plan {stufe} {schuljahr}",
                       status=status, subject_id=fach.id, min_grade=stufe, max_grade=stufe,
                       read_scope="school", write_scope="private", owner_pseudonym="test",
                       metadata_={"schuljahr": schuljahr, "abschnitte": []})


@pytest_asyncio.fixture
async def fach(db_session):
    f = Subject(slug=f"m-{TOKEN}", name=f"Mathe {TOKEN}", sort_order=0)
    db_session.add(f)
    await db_session.flush()
    return f


async def _speichern(db, knoten) -> bool:
    """True, wenn die Datenbank den Knoten annimmt."""
    try:
        async with db.begin_nested():
            db.add(knoten)
            await db.flush()
        return True
    except IntegrityError:
        return False


async def test_entwurf_erlaubt(db_session, fach):
    assert await _speichern(db_session, _plan(fach))


async def test_entwurf_anderer_planungstypen_bleibt_verboten(db_session, fach):
    assert not await _speichern(db_session, _plan(fach, typ="jahresplan"))


async def test_ein_plan_je_fach_stufe_schuljahr(db_session, fach):
    assert await _speichern(db_session, _plan(fach))
    # Beschlossen zählt wie Entwurf
    assert not await _speichern(db_session, _plan(fach, status="active"))
    # Andere Stufe, anderes Schuljahr: frei
    assert await _speichern(db_session, _plan(fach, stufe=10))
    assert await _speichern(db_session, _plan(fach, schuljahr="2027/28"))


async def test_archivierte_zaehlen_nicht(db_session, fach):
    assert await _speichern(db_session, _plan(fach, status="archived"))
    assert await _speichern(db_session, _plan(fach, status="active"))
