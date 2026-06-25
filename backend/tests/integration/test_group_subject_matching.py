"""Integrationstests: SSO-Gruppe → Subject-Auflösung gegen die Test-DB.

Deckt die DB-seitige Matching-Logik aus `_resolve_subject_id` ab: case-insensitiv
gegen subject.slug ODER subject.sso_aliases (geseedet aus config/subjects.yaml,
Single Source of Truth). Die `sync_groups`-Orchestrierung ist (gemockt) in
test_auth_router.py abgedeckt; sie committet intern und passt deshalb nicht in
die transaktionale db_session-Fixture (Rollback pro Test).
"""
import pytest
from sqlalchemy import func, select

from app.auth.group_sync import _resolve_subject_id, _normalize_for_slug
from app.db.models import Subject


async def _get_or_create_subject(db, slug: str, name: str, aliases=()) -> int:
    """Idempotent: vorhandenes Subject finden, sonst anlegen (kein commit).

    Vergibt eine explizite ID = MAX(id)+1 statt Autoincrement: Die geteilte
    Test-DB enthält committete Subjects mit expliziten IDs, hinter denen die
    Sequenz zurückliegt — Autoincrement würde dann kollidieren.
    Aliase werden wie im Seed normalisiert (lowercase + Umlaute) gespeichert.
    """
    norm_aliases = sorted({_normalize_for_slug(a) for a in aliases})
    res = await db.execute(select(Subject).where(Subject.slug == slug))
    subject = res.scalar_one_or_none()
    if subject is not None:
        subject.sso_aliases = norm_aliases
        await db.flush()
        return subject.id
    next_id = (await db.execute(select(func.coalesce(func.max(Subject.id), 0)))).scalar_one() + 1
    subject = Subject(id=next_id, slug=slug, name=name, sso_aliases=norm_aliases)
    db.add(subject)
    await db.flush()
    return subject.id


async def _seed_base_subjects(db) -> dict[str, int]:
    return {
        "mathematik": await _get_or_create_subject(db, "mathematik", "Mathematik"),
        "kunst": await _get_or_create_subject(db, "kunst", "Kunst", aliases=["bildende.kunst"]),
        "religion-ev": await _get_or_create_subject(
            db, "religion-ev", "Evangelische Religion", aliases=["religion.ev"]
        ),
        "nwt": await _get_or_create_subject(db, "nwt", "NwT"),
        "wirtschaft": await _get_or_create_subject(db, "wirtschaft", "Wirtschaft"),
    }


@pytest.mark.asyncio
async def test_resolve_direct_case_insensitive(db_session):
    """Direkter Slug-Treffer, unabhängig von der Schreibweise des abgeleiteten Werts."""
    ids = await _seed_base_subjects(db_session)
    assert await _resolve_subject_id(db_session, "mathematik") == ids["mathematik"]
    # IServ fs.NwT → captured "NwT" → trifft Slug "nwt" case-insensitiv
    assert await _resolve_subject_id(db_session, "NwT") == ids["nwt"]
    # Zusammengefasste Fachschaft fs.wirtschaft → direkter Slug-Treffer
    assert await _resolve_subject_id(db_session, "wirtschaft") == ids["wirtschaft"]


@pytest.mark.asyncio
async def test_resolve_via_sso_alias(db_session):
    """sso_aliases-Treffer: fs.bildende.kunst → kunst, fs.religion.ev → religion-ev."""
    ids = await _seed_base_subjects(db_session)
    assert await _resolve_subject_id(db_session, "bildende.kunst") == ids["kunst"]
    assert await _resolve_subject_id(db_session, "religion.ev") == ids["religion-ev"]


@pytest.mark.asyncio
async def test_resolve_unknown_returns_none(db_session):
    """Werte ohne Fach/Alias → None (z.B. Sammelgruppe fs.reli, fehlende Fächer)."""
    await _seed_base_subjects(db_session)
    assert await _resolve_subject_id(db_session, "reli") is None  # Sammelgruppe, kein Fach
    assert await _resolve_subject_id(db_session, "franzoesisch") is None
    assert await _resolve_subject_id(db_session, "spanisch") is None


@pytest.mark.asyncio
async def test_resolve_umlaut_normalisation(db_session):
    """Umlaut-Eingabe (Französisch) trifft umlautfreien DB-Slug (franzoesisch)."""
    sid = await _get_or_create_subject(db_session, "franzoesisch", "Französisch")
    assert await _resolve_subject_id(db_session, "Französisch") == sid


@pytest.mark.asyncio
async def test_resolve_alias_is_case_insensitive(db_session):
    """Alias-Auflösung ignoriert Groß-/Kleinschreibung des Variantennamens."""
    ids = await _seed_base_subjects(db_session)
    assert await _resolve_subject_id(db_session, "Bildende.Kunst") == ids["kunst"]
    assert await _resolve_subject_id(db_session, "Religion.EV") == ids["religion-ev"]
