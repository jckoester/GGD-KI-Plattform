"""Integrationstests: SSO-Gruppe → Subject-Auflösung gegen die Test-DB.

Deckt die DB-seitige Matching-Logik aus `_resolve_subject_id` ab, die per
Unit-Test nicht erreichbar ist (case-insensitiv, Alias-Map, Umlaut-Toleranz).
Die `sync_groups`-Orchestrierung selbst ist (gemockt) in test_auth_router.py
abgedeckt; sie committet intern und passt deshalb nicht in die transaktionale
db_session-Fixture (Rollback pro Test).
"""
import pytest
from sqlalchemy import func, select

from app.auth.group_sync import _resolve_subject_id
from app.db.models import Subject


# Aliase analog config/auth.yaml (echte Fachschaftsvarianten)
ALIASES = {
    "bildende.kunst": "kunst",
    "reli": "religion",
    "religion.ev": "religion",
    "religion.kath": "religion",
}


async def _get_or_create_subject(db, slug: str, name: str) -> int:
    """Idempotent: vorhandenes Subject finden, sonst anlegen (kein commit).

    Vergibt eine explizite ID = MAX(id)+1 statt Autoincrement: Die geteilte
    Test-DB enthält committete Subjects mit expliziten IDs, hinter denen die
    Sequenz zurückliegt — Autoincrement würde dann kollidieren.
    """
    res = await db.execute(select(Subject).where(Subject.slug == slug))
    subject = res.scalar_one_or_none()
    if subject is not None:
        return subject.id
    next_id = (await db.execute(select(func.coalesce(func.max(Subject.id), 0)))).scalar_one() + 1
    subject = Subject(id=next_id, slug=slug, name=name)
    db.add(subject)
    await db.flush()
    return subject.id


async def _seed_base_subjects(db) -> dict[str, int]:
    return {
        "mathematik": await _get_or_create_subject(db, "mathematik", "Mathematik"),
        "kunst": await _get_or_create_subject(db, "kunst", "Kunst"),
        "religion": await _get_or_create_subject(db, "religion", "Religion"),
        "nwt": await _get_or_create_subject(db, "nwt", "NwT"),
    }


@pytest.mark.asyncio
async def test_resolve_direct_case_insensitive(db_session):
    """Direkter Treffer, unabhängig von der Schreibweise des abgeleiteten Werts."""
    ids = await _seed_base_subjects(db_session)
    assert await _resolve_subject_id(db_session, "mathematik", ALIASES) == ids["mathematik"]
    # IServ-Account fs.NwT → captured "NwT" → trifft Slug "nwt" case-insensitiv
    assert await _resolve_subject_id(db_session, "NwT", ALIASES) == ids["nwt"]


@pytest.mark.asyncio
async def test_resolve_via_alias_dotted_name(db_session):
    """Mehrteiliger Account (fs.bildende.kunst) wird per Alias auf "kunst" gemappt."""
    ids = await _seed_base_subjects(db_session)
    assert await _resolve_subject_id(db_session, "bildende.kunst", ALIASES) == ids["kunst"]


@pytest.mark.asyncio
async def test_resolve_religion_variants_via_alias(db_session):
    """reli / religion.ev / religion.kath → alle auf Subject "religion"."""
    ids = await _seed_base_subjects(db_session)
    for variant in ("reli", "religion.ev", "religion.kath"):
        assert await _resolve_subject_id(db_session, variant, ALIASES) == ids["religion"], variant


@pytest.mark.asyncio
async def test_resolve_unknown_returns_none(db_session):
    """Fachschaft ohne passendes Subject (z.B. Französisch nicht geseedet) → None."""
    await _seed_base_subjects(db_session)
    assert await _resolve_subject_id(db_session, "franzoesisch", ALIASES) is None
    assert await _resolve_subject_id(db_session, "wirtschaft", ALIASES) is None


@pytest.mark.asyncio
async def test_resolve_umlaut_normalisation(db_session):
    """Umlaut-Eingabe (Französisch) trifft umlautfreien DB-Slug (franzoesisch)."""
    sid = await _get_or_create_subject(db_session, "franzoesisch", "Französisch")
    assert await _resolve_subject_id(db_session, "Französisch", {}) == sid


@pytest.mark.asyncio
async def test_resolve_alias_is_case_insensitive(db_session):
    """Alias-Auflösung ignoriert Groß-/Kleinschreibung des Variantennamens."""
    ids = await _seed_base_subjects(db_session)
    assert await _resolve_subject_id(db_session, "Reli", ALIASES) == ids["religion"]
