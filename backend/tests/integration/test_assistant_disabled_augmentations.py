"""Integrationstest für assistants.disabled_augmentations (Phase 13, Schritt 2).

Server-Default (leeres Array) + ARRAY-Round-Trip gegen die echte Test-DB.
Erfordert TEST_DATABASE_URL.
"""

from sqlalchemy import select

from app.db.models import Assistant


async def test_disabled_augmentations_defaults_empty(db_session):
    a = Assistant(name="A1", system_prompt="P", model="m")
    db_session.add(a)
    await db_session.flush()
    await db_session.refresh(a)
    assert a.disabled_augmentations == []


async def test_disabled_augmentations_roundtrip(db_session):
    a = Assistant(
        name="A2",
        system_prompt="P",
        model="m",
        disabled_augmentations=["socratic_preference", "metacognitive_nudges"],
    )
    db_session.add(a)
    await db_session.flush()
    row = await db_session.scalar(select(Assistant).where(Assistant.id == a.id))
    assert row.disabled_augmentations == ["socratic_preference", "metacognitive_nudges"]
