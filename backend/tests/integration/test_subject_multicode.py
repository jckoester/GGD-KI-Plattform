"""Integrationstests: Multi-Fachcode-Auflösung (subjects.fach_codes).

Prüft, dass ein Fach mit zwei Bildungsplänen über die Klassenspanne (z. B. NwT:
NWT 8-10 + NWTBFO 11-12) über BEIDE Codes auf dasselbe Fach auflöst — gegen eine
echte PostgreSQL-Test-DB (ARRAY-Operator `= ANY(fach_codes)`).
"""

from app.context.service import get_subject_id_by_code
from app.db.models import Subject


async def test_both_codes_resolve_to_same_subject(db_session):
    subj = Subject(slug="nwt", name="NwT", fach_code="NWT", fach_codes=["NWT", "NWTBFO"])
    db_session.add(subj)
    await db_session.flush()

    assert await get_subject_id_by_code(db_session, "NWT") == subj.id
    assert await get_subject_id_by_code(db_session, "NWTBFO") == subj.id


async def test_resolution_is_case_insensitive(db_session):
    subj = Subject(slug="nwt", name="NwT", fach_code="NWT", fach_codes=["NWT", "NWTBFO"])
    db_session.add(subj)
    await db_session.flush()

    assert await get_subject_id_by_code(db_session, "nwtbfo") == subj.id


async def test_scalar_only_subject_resolves(db_session):
    subj = Subject(slug="mathematik", name="Mathe", fach_code="M", fach_codes=["M"])
    db_session.add(subj)
    await db_session.flush()

    assert await get_subject_id_by_code(db_session, "M") == subj.id


async def test_empty_fach_codes_resolves_via_scalar(db_session):
    # Bestandsdaten vor Re-Seed: fach_codes leer → Auflösung über die skalare Spalte.
    subj = Subject(slug="chemie", name="Chemie", fach_code="CH", fach_codes=[])
    db_session.add(subj)
    await db_session.flush()

    assert await get_subject_id_by_code(db_session, "CH") == subj.id


async def test_unknown_code_returns_none(db_session):
    assert await get_subject_id_by_code(db_session, "ZZZ") is None
