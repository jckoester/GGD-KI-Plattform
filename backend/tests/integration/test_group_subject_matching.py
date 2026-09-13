"""Integrationstests: SSO-Gruppe → Subject-Auflösung gegen die Test-DB.

Deckt ab:
- `_resolve_subject_id(s)`: case-insensitiv gegen subject.slug ODER subject.sso_aliases
  (geseedet aus config/subjects.yaml), inkl. Mehrfach-Auflösung (Sammel-Fachschaft →
  mehrere Fächer, Direkt-Treffer vor Alias-Treffern).
- `sync_groups`: eine Fachschaft mit mehreren Fächern → je Fach eine Gruppe. Da
  sync_groups intern committet, nutzt dieser Test eine eigene Session + explizites
  Cleanup statt der rollback-basierten db_session-Fixture.
"""
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.config import SsoGroupPatterns
from app.auth.group_sync import (
    _normalize_for_slug,
    _resolve_subject_id,
    _resolve_subject_ids,
    sync_groups,
)
from app.db.models import Group, GroupMembership, Subject


PATTERNS = SsoGroupPatterns(
    subject_department=r"^FS\.(.+)$",
    school_class=r"^Klasse\.(.+)$",
    teaching_group=r"^unterricht\.(.+)$",
)


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


# ── Mehrfach-Auflösung (Sammel-Fachschaft → mehrere Fächer) ───────────────────

@pytest.mark.asyncio
async def test_resolve_ids_multi_direct_before_alias(db_session):
    """fs.wirtschaft → [wirtschaft (direkt), wbs (Alias)] — Direkt-Treffer zuerst."""
    wirt = await _get_or_create_subject(db_session, "wirtschaft", "Wirtschaft")
    wbs = await _get_or_create_subject(db_session, "wbs", "WBS", aliases=["wirtschaft"])
    ids = await _resolve_subject_ids(db_session, "wirtschaft")
    assert ids == [wirt, wbs]  # direkt vor Alias
    # Einzel-Auflösung bevorzugt den Direkt-Treffer (wichtig für Unterrichtsgruppen)
    assert await _resolve_subject_id(db_session, "wirtschaft") == wirt


@pytest.mark.asyncio
async def test_resolve_ids_single_and_empty(db_session):
    """Einzelfach → genau eine ID; unbekannt → leer."""
    mid = await _get_or_create_subject(db_session, "mathematik", "Mathematik")
    assert await _resolve_subject_ids(db_session, "mathematik") == [mid]
    assert await _resolve_subject_ids(db_session, "franzoesisch") == []


# ── sync_groups: Fachschaft mit mehreren Fächern → mehrere Gruppen ────────────

@pytest.mark.asyncio
async def test_sync_groups_fachschaft_multi_subject(async_engine):
    """fs.wirtschaft → zwei subject_department-Gruppen (wirtschaft + wbs), beide Mitglied.

    sync_groups committet intern, daher eigene Session + explizites Cleanup
    (statt der rollback-basierten db_session-Fixture).
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    pseudo = "fs-multi-test-pseudo"
    try:
        async with factory() as db:
            wirt_id = await _get_or_create_subject(db, "wirtschaft", "Wirtschaft")
            wbs_id = await _get_or_create_subject(db, "wbs", "WBS", aliases=["wirtschaft"])
            await db.commit()

        async with factory() as db:
            await sync_groups(
                db=db, pseudonym=pseudo, sso_groups=["fs.wirtschaft"],
                primary_role="teacher", patterns=PATTERNS,
            )

        async with factory() as db:
            rows = (await db.execute(
                select(Group.subject_id, Group.slug)
                .join(GroupMembership, GroupMembership.group_id == Group.id)
                .where(
                    GroupMembership.pseudonym == pseudo,
                    Group.type == "subject_department",
                )
            )).all()
            assert len(rows) == 2
            assert {r.subject_id for r in rows} == {wirt_id, wbs_id}
            # eindeutige Slugs je Fach
            assert {r.slug for r in rows} == {"fs-wirtschaft-wirtschaft", "fs-wirtschaft-wbs"}
    finally:
        async with factory() as db:
            await db.execute(delete(GroupMembership).where(GroupMembership.pseudonym == pseudo))
            await db.execute(delete(Group).where(Group.sso_group_id == "fs.wirtschaft"))
            await db.execute(delete(Subject).where(Subject.slug.in_(["wirtschaft", "wbs"])))
            await db.commit()


# ── Unterrichtsgruppen aus dem Stundenplan (Produktionsfall 13.09.2026) ───────

STUNDENPLAN_PATTERNS = SsoGroupPatterns(
    school_class=r"^Klasse\.(.+)$",
    teaching_group=r"^unterricht\.(?P<bezeichnung>(?P<fach>[^-]+)-.+)$",
)


async def test_unterrichtsgruppe_findet_ihr_fach_ueber_das_stundenplan_kuerzel(
    async_engine,
):
    """`unterricht.ch2-ks-11` → Gruppe **mit** subject_id, aufgelöst über `untis_codes`.

    Die ganze Kette auf einmal: benannte Capture-Gruppe im Muster, Rückfall auf das
    Stundenplan-Vokabular, Abschneiden der Kursziffer (`ch2` → `CH`). Vorher entstand
    hier eine Gruppe ohne Fach — sichtbar im Profil, unter keinem Fach auffindbar.

    Bewusst **ohne** `sso_aliases`: Stundenplan-Kürzel dort zu wiederholen wäre ein
    viertes Vokabular mit demselben Inhalt.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    pseudo = "stundenplan-gruppe-pseudo"
    try:
        async with factory() as db:
            chem_id = await _get_or_create_subject(db, "chemie-sp", "Chemie (Test)")
            fach = await db.get(Subject, chem_id)
            fach.untis_codes = ["CH"]
            await db.commit()

        async with factory() as db:
            await sync_groups(
                db=db, pseudonym=pseudo, sso_groups=["unterricht.ch2-ks-11"],
                primary_role="teacher", patterns=STUNDENPLAN_PATTERNS,
            )

        async with factory() as db:
            row = (await db.execute(
                select(Group.subject_id, Group.name, Group.type)
                .join(GroupMembership, GroupMembership.group_id == Group.id)
                .where(GroupMembership.pseudonym == pseudo)
            )).one()
            assert row.type == "teaching_group"
            assert row.subject_id == chem_id, "Gruppe ohne Fach — Auflösung griff nicht"
            assert row.name == "ch2-ks-11"
    finally:
        async with factory() as db:
            await db.execute(delete(GroupMembership).where(GroupMembership.pseudonym == pseudo))
            await db.execute(
                delete(Group).where(Group.sso_group_id == "unterricht.ch2-ks-11")
            )
            await db.execute(delete(Subject).where(Subject.slug == "chemie-sp"))
            await db.commit()


async def test_ohne_benanntes_fach_bleibt_die_gruppe_ohne_fach(async_engine):
    """Der Ausgangszustand, festgehalten: altes Muster + Stundenplan-Benennung.

    Ohne diesen Test sagte der obige nur, dass etwas funktioniert — nicht, dass es
    vorher nicht funktionierte.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    pseudo = "stundenplan-ohne-muster-pseudo"
    try:
        async with factory() as db:
            chem_id = await _get_or_create_subject(db, "chemie-sp2", "Chemie (Test 2)")
            fach = await db.get(Subject, chem_id)
            fach.untis_codes = ["CH"]
            await db.commit()

        async with factory() as db:
            await sync_groups(
                db=db, pseudonym=pseudo, sso_groups=["unterricht.ch2-ks-11"],
                primary_role="teacher", patterns=PATTERNS,
            )

        async with factory() as db:
            row = (await db.execute(
                select(Group.subject_id)
                .join(GroupMembership, GroupMembership.group_id == Group.id)
                .where(GroupMembership.pseudonym == pseudo)
            )).one()
            assert row.subject_id is None
    finally:
        async with factory() as db:
            await db.execute(delete(GroupMembership).where(GroupMembership.pseudonym == pseudo))
            await db.execute(
                delete(Group).where(Group.sso_group_id == "unterricht.ch2-ks-11")
            )
            await db.execute(delete(Subject).where(Subject.slug == "chemie-sp2"))
            await db.commit()


async def test_nachziehen_der_konfiguration_traegt_das_fach_nach(async_engine):
    """Erst ohne Muster anmelden, dann mit — es darf **eine** Gruppe bleiben.

    Genau der Rollout-Weg in Produktion: Die Gruppen stehen schon ohne Fach in der
    Datenbank, dann wird `config/auth.yaml` nachgezogen. Ohne Adoption ergäbe das ein
    Paar aus verwaister Zeile und neuer Gruppe mit Slug-Suffix `-2`; `dedup_groups`
    räumt das nicht auf, weil `subject_id` Teil seines Schlüssels ist.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    pseudo = "nachziehen-pseudo"
    try:
        async with factory() as db:
            chem_id = await _get_or_create_subject(db, "chemie-sp3", "Chemie (Test 3)")
            fach = await db.get(Subject, chem_id)
            fach.untis_codes = ["CH"]
            await db.commit()

        # 1. Login mit altem Muster → Gruppe ohne Fach
        async with factory() as db:
            await sync_groups(
                db=db, pseudonym=pseudo, sso_groups=["unterricht.ch2-ks-11"],
                primary_role="teacher", patterns=PATTERNS,
            )
        async with factory() as db:
            vorher = (await db.execute(
                select(Group.id, Group.subject_id, Group.slug)
                .where(func.lower(Group.sso_group_id) == "unterricht.ch2-ks-11")
            )).all()
            assert len(vorher) == 1 and vorher[0].subject_id is None

        # 2. Login mit nachgezogenem Muster → dieselbe Zeile, jetzt mit Fach
        async with factory() as db:
            await sync_groups(
                db=db, pseudonym=pseudo, sso_groups=["unterricht.ch2-ks-11"],
                primary_role="teacher", patterns=STUNDENPLAN_PATTERNS,
            )
        async with factory() as db:
            nachher = (await db.execute(
                select(Group.id, Group.subject_id, Group.slug)
                .where(func.lower(Group.sso_group_id) == "unterricht.ch2-ks-11")
            )).all()
            assert len(nachher) == 1, f"Doppelanlage statt Adoption: {nachher}"
            assert nachher[0].id == vorher[0].id
            assert nachher[0].subject_id == chem_id
            assert nachher[0].slug == vorher[0].slug, "Slug bekam ein Suffix"
    finally:
        async with factory() as db:
            await db.execute(delete(GroupMembership).where(GroupMembership.pseudonym == pseudo))
            await db.execute(
                delete(Group).where(func.lower(Group.sso_group_id) == "unterricht.ch2-ks-11")
            )
            await db.execute(delete(Subject).where(Subject.slug == "chemie-sp3"))
            await db.commit()
