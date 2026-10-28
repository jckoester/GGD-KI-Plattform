"""Abschnitt „Andere allgemeine Assistenten“ (0.26, Plan „Rückfall-Assistenten“, Schritt 3).

Am echten Bestand: nur aktive, sichtbare Rückfälle mit Vorschlagssatz, nicht der eigene,
nicht versteckte, nicht außerhalb der Klassenstufe, keine spezifischen.
Erfordert TEST_DATABASE_URL.
"""
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assistants.andere import UEBERSCHRIFT, andere_allgemeine
from app.assistants.sichtbarkeit import Zugang
from app.db.models import Assistant

pytestmark = pytest.mark.asyncio

P = "AND "
ZUGANG = Zugang(pseudonym="and-schueler", rollen=frozenset({"student"}), gruppen=frozenset(),
                lehrgruppen=frozenset(), stufe=7)


def _a(name, **mehr):
    werte = dict(name=P + name, system_prompt="P", audience="student", scope="all_students",
                 status="active", visibility="public", suggest="fallback", model="",
                 suggestion_text=f"Satz {name}.", created_by="__test__", creator_role="admin")
    return Assistant(**(werte | mehr))


@pytest_asyncio.fixture
async def db(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as s:
        yield s
        await s.rollback()
        await s.execute(sa.delete(Assistant).where(Assistant.name.like(f"{P}%")))
        await s.commit()


async def test_nur_passende_rueckfaelle(db):
    eigen = _a("Eigen")
    db.add_all([eigen, _a("Mathe"), _a("Versteckt", visibility="hidden"), _a("Ohne Satz", suggestion_text=None),
                _a("Oberstufe", min_grade=11), _a("Spezifisch", suggest="specific"),
                _a("Entwurf", status="draft")])
    await db.commit()
    text = await andere_allgemeine(db, ZUGANG, eigen.id)
    zeilen = [z for z in text.splitlines() if z.startswith(f"- Assistent für {P}")]
    assert text.startswith(UEBERSCHRIFT)
    assert zeilen == [f"- Assistent für {P}Mathe: Satz Mathe."]


async def test_leer_ohne_andere(db):
    eigen = _a("Allein")
    db.add(eigen)
    await db.commit()
    text = await andere_allgemeine(db, ZUGANG, eigen.id)
    assert P not in text
