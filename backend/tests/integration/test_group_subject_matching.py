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
from app.db.models import Group, GroupMembership, GroupSourceClass, Subject


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


# ── Der Immediate Mirror und die Gruppen ohne SSO-Entsprechung ───────────────

OHNE_UNTERRICHT = SsoGroupPatterns(
    subject_department=r"^FS\.(.+)$",
    school_class=r"^Klasse\.(.+)$",
)


async def _adoptierte_gruppe(db, fach_id: int, klasse_id: int, pseudonym: str) -> int:
    """Eine Unterrichtsgruppe, wie sie beim Bestätigen eines Vorschlags entsteht:
    ohne `sso_group_id`, mit Bezug auf die Quellklasse, Lehrkraft als einziges Mitglied."""
    gruppe = Group(
        name="9z", slug=f"teaching-adoptiert-{klasse_id}", type="teaching_group",
        subject_id=fach_id, sso_group_id=None,
        # „Klasse × Fach" ist der ganze Klassenverband — die Gruppe erbt (Alembic 0069).
        erbt_mitglieder=True,
    )
    db.add(gruppe)
    await db.flush()
    db.add(GroupSourceClass(group_id=gruppe.id, class_group_id=klasse_id))
    db.add(GroupMembership(
        group_id=gruppe.id, pseudonym=pseudonym, role_in_group="teacher",
        herkunft="eigen",
    ))
    return gruppe.id


async def test_adoptierte_gruppe_ueberlebt_den_naechsten_login(async_engine):
    """Der Blocker, nachgemessen am 13.09.2026 — und behoben.

    Eine aus einem Vorschlag bestätigte Unterrichtsgruppe hat kein `sso_group_id`, steht
    also in keinem Token. Der Immediate Mirror löschte deshalb bei **jedem** Login die
    Mitgliedschaft — auch die der Lehrkraft, die die Gruppe gerade angelegt hatte. Die
    Gruppe war danach leer und nur noch über das Archiv erreichbar.

    Der Spiegel fasst jetzt nur noch Gruppen mit `sso_group_id` an.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    lehrkraft = "mirror-lehrkraft"
    try:
        async with factory() as db:
            fach_id = await _get_or_create_subject(db, "mirror-fach", "Spiegelkunde")
            klasse = Group(name="9z", slug="klasse-9z-mirror", type="school_class",
                           sso_group_id="klasse.9z")
            db.add(klasse)
            await db.flush()
            gruppe_id = await _adoptierte_gruppe(db, fach_id, klasse.id, lehrkraft)
            await db.commit()

        async with factory() as db:
            await sync_groups(
                db=db, pseudonym=lehrkraft, sso_groups=["klasse.9z"],
                primary_role="teacher", patterns=OHNE_UNTERRICHT,
            )

        async with factory() as db:
            noch_drin = (await db.execute(
                select(func.count()).select_from(GroupMembership).where(
                    GroupMembership.pseudonym == lehrkraft,
                    GroupMembership.group_id == gruppe_id,
                )
            )).scalar()
            assert noch_drin == 1, "adoptierte Gruppe verlor ihre Lehrkraft beim Login"
    finally:
        async with factory() as db:
            await db.execute(delete(GroupMembership).where(GroupMembership.pseudonym == lehrkraft))
            await db.execute(delete(Group).where(
                Group.slug.in_(["klasse-9z-mirror", "fs-spiegelkunde"])
                | Group.slug.like("teaching-adoptiert-%")
            ))
            await db.execute(delete(Subject).where(Subject.slug == "mirror-fach"))
            await db.commit()


async def test_der_spiegel_raeumt_sso_gruppen_weiterhin_auf(async_engine):
    """Die Gegenrichtung: Was aus dem Token kam und nicht mehr darin steht, fällt.

    Ohne diesen Test wäre „nur Gruppen mit sso_group_id anfassen" auch dann erfüllt,
    wenn der Spiegel gar nichts mehr täte.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    pseudo = "mirror-abgang"
    try:
        async with factory() as db:
            await _get_or_create_subject(db, "abgang-fach", "Abgangskunde")
            await db.commit()

        async with factory() as db:
            await sync_groups(db=db, pseudonym=pseudo, sso_groups=["Klasse.9w", "FS.Abgangskunde"],
                              primary_role="teacher", patterns=OHNE_UNTERRICHT)
        async with factory() as db:
            assert (await db.execute(
                select(func.count()).select_from(GroupMembership)
                .where(GroupMembership.pseudonym == pseudo)
            )).scalar() == 2

        # Zweiter Login, Fachschaft weg
        async with factory() as db:
            await sync_groups(db=db, pseudonym=pseudo, sso_groups=["Klasse.9w"],
                              primary_role="teacher", patterns=OHNE_UNTERRICHT)
        async with factory() as db:
            uebrig = (await db.execute(
                select(Group.type)
                .join(GroupMembership, GroupMembership.group_id == Group.id)
                .where(GroupMembership.pseudonym == pseudo)
            )).all()
            assert [t for (t,) in uebrig] == ["school_class"]
    finally:
        async with factory() as db:
            await db.execute(delete(GroupMembership).where(GroupMembership.pseudonym == pseudo))
            await db.execute(delete(Group).where(Group.slug.in_(["klasse-9w", "fs-abgangskunde"])))
            await db.execute(delete(Subject).where(Subject.slug == "abgang-fach"))
            await db.commit()


# ── Die Klasse kommt mit: Adoption ohne eigene SSO-Gruppe ────────────────────


class TestVererbungAusDerKlasse:
    """Mathe im Klassenverband soll **keine** eigene SSO-Gruppe brauchen.

    Die Lehrkraft bestätigt „Klasse 8a × Mathematik", und die Schüler:innen der 8a sind
    beim nächsten Login in der Gruppe. Bis 13.09.2026 war die Gruppe für sie unsichtbar:
    Die Quellklasse stand in der Datenbank, wurde aber nirgends für
    Mitgliedschaften ausgewertet.
    """

    async def test_schuelerin_erbt_die_adoptierte_gruppe(self, async_engine):
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        lehrkraft, schuelerin = "erbe-lehrkraft", "erbe-schuelerin"
        try:
            async with factory() as db:
                fach_id = await _get_or_create_subject(db, "erbe-fach", "Erbkunde")
                klasse = Group(name="8a", slug="klasse-8a-erbe", type="school_class",
                               sso_group_id="klasse.8a-erbe")
                db.add(klasse)
                await db.flush()
                gruppe_id = await _adoptierte_gruppe(db, fach_id, klasse.id, lehrkraft)
                await db.commit()

            async with factory() as db:
                await sync_groups(db=db, pseudonym=schuelerin,
                                  sso_groups=["klasse.8a-erbe"],
                                  primary_role="student", patterns=OHNE_UNTERRICHT)

            async with factory() as db:
                rolle = (await db.execute(
                    select(GroupMembership.role_in_group).where(
                        GroupMembership.pseudonym == schuelerin,
                        GroupMembership.group_id == gruppe_id,
                    )
                )).scalar_one_or_none()
                assert rolle == "student", "Schülerin erbte die Unterrichtsgruppe nicht"
        finally:
            await _erbe_aufraeumen(factory, [lehrkraft, schuelerin],
                                   ["klasse-8a-erbe"], "erbe-fach")

    async def test_klassenwechsel_nimmt_die_gruppe_wieder_mit(self, async_engine):
        """Abgeleitet heißt abgeleitet — der Immediate Mirror räumt sie nicht auf."""
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        lehrkraft, schuelerin = "erbe2-lehrkraft", "erbe2-schuelerin"
        try:
            async with factory() as db:
                fach_id = await _get_or_create_subject(db, "erbe2-fach", "Erbkunde 2")
                klasse = Group(name="8b", slug="klasse-8b-erbe", type="school_class",
                               sso_group_id="klasse.8b-erbe")
                db.add(klasse)
                await db.flush()
                gruppe_id = await _adoptierte_gruppe(db, fach_id, klasse.id, lehrkraft)
                await db.commit()

            async with factory() as db:
                await sync_groups(db=db, pseudonym=schuelerin, sso_groups=["klasse.8b-erbe"],
                                  primary_role="student", patterns=OHNE_UNTERRICHT)
            # Nächstes Schuljahr: nicht mehr in der 8b
            async with factory() as db:
                await sync_groups(db=db, pseudonym=schuelerin, sso_groups=[],
                                  primary_role="student", patterns=OHNE_UNTERRICHT)

            async with factory() as db:
                noch_drin = (await db.execute(
                    select(func.count()).select_from(GroupMembership).where(
                        GroupMembership.pseudonym == schuelerin,
                        GroupMembership.group_id == gruppe_id,
                    )
                )).scalar()
                assert noch_drin == 0, "geerbte Mitgliedschaft blieb nach dem Klassenwechsel"
        finally:
            await _erbe_aufraeumen(factory, [lehrkraft, schuelerin],
                                   ["klasse-8b-erbe"], "erbe2-fach")

    async def test_die_lehrkraft_erbt_nichts(self, async_engine):
        """Sonst säße die Klassenleitung in jedem Fach ihrer Klasse.

        Die Deutschlehrerin ist in der 8c und in der Fachschaft Deutsch. Die adoptierte
        Mathe-Gruppe der 8c geht sie nichts an.
        """
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        mathe_lk, deutsch_lk = "erbe3-mathe", "erbe3-deutsch"
        try:
            async with factory() as db:
                fach_id = await _get_or_create_subject(db, "erbe3-fach", "Erbkunde 3")
                klasse = Group(name="8c", slug="klasse-8c-erbe", type="school_class",
                               sso_group_id="klasse.8c-erbe")
                db.add(klasse)
                await db.flush()
                gruppe_id = await _adoptierte_gruppe(db, fach_id, klasse.id, mathe_lk)
                await db.commit()

            async with factory() as db:
                await sync_groups(db=db, pseudonym=deutsch_lk, sso_groups=["klasse.8c-erbe"],
                                  primary_role="teacher", patterns=OHNE_UNTERRICHT)

            async with factory() as db:
                drin = (await db.execute(
                    select(func.count()).select_from(GroupMembership).where(
                        GroupMembership.pseudonym == deutsch_lk,
                        GroupMembership.group_id == gruppe_id,
                    )
                )).scalar()
                assert drin == 0, "fremde Lehrkraft wurde in die Gruppe gezogen"
        finally:
            await _erbe_aufraeumen(factory, [mathe_lk, deutsch_lk],
                                   ["klasse-8c-erbe"], "erbe3-fach")

    async def test_gruppe_mit_sso_entsprechung_wird_nicht_beerbt(self, async_engine):
        """Gibt es eine IServ-Gruppe, ist deren Mitgliederliste maßgeblich.

        Sonst schriebe die Ableitung Leute hinein, die der Provider nicht nennt — etwa
        die ganze Klasse in einen Differenzierungskurs.
        """
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        schuelerin = "erbe4-schuelerin"
        try:
            async with factory() as db:
                fach_id = await _get_or_create_subject(db, "erbe4-fach", "Erbkunde 4")
                klasse = Group(name="8d", slug="klasse-8d-erbe", type="school_class",
                               sso_group_id="klasse.8d-erbe")
                db.add(klasse)
                await db.flush()
                mit_sso = Group(name="8d", slug="teaching-mit-sso", type="teaching_group",
                                subject_id=fach_id,
                                sso_group_id="unterricht.erbe4-8d")
                db.add(mit_sso)
                await db.flush()
                db.add(GroupSourceClass(group_id=mit_sso.id, class_group_id=klasse.id))
                await db.flush()
                gruppe_id = mit_sso.id
                await db.commit()

            async with factory() as db:
                await sync_groups(db=db, pseudonym=schuelerin, sso_groups=["klasse.8d-erbe"],
                                  primary_role="student", patterns=OHNE_UNTERRICHT)

            async with factory() as db:
                drin = (await db.execute(
                    select(func.count()).select_from(GroupMembership).where(
                        GroupMembership.pseudonym == schuelerin,
                        GroupMembership.group_id == gruppe_id,
                    )
                )).scalar()
                assert drin == 0, "SSO-geführte Gruppe wurde beerbt"
        finally:
            async with factory() as db:
                await db.execute(delete(GroupMembership).where(
                    GroupMembership.pseudonym == schuelerin))
                await db.execute(delete(Group).where(
                    Group.slug.in_(["klasse-8d-erbe", "teaching-mit-sso"])))
                await db.execute(delete(Subject).where(Subject.slug == "erbe4-fach"))
                await db.commit()


async def _erbe_aufraeumen(factory, pseudonyme, klassen_slugs, fach_slug):
    async with factory() as db:
        await db.execute(delete(GroupMembership).where(
            GroupMembership.pseudonym.in_(pseudonyme)))
        await db.execute(delete(Group).where(
            Group.slug.in_(klassen_slugs) | Group.slug.like("teaching-adoptiert-%")))
        await db.execute(delete(Subject).where(Subject.slug == fach_slug))
        await db.commit()


@pytest.mark.asyncio
async def test_der_sync_laesst_den_anzeigenamen_stehen(async_engine):
    """Der Kern der Entscheidung, `display_name` als eigene Spalte zu führen.

    `sync_groups` schreibt `group.name` bei **jedem** Login neu — der Name gehört dem
    Schulkonto. Läge der selbst vergebene Name dort, wäre er nach der nächsten Anmeldung
    weg, und zwar lautlos. Dieser Test hält fest, dass der Sync ihn nicht anfasst und den
    rohen Namen trotzdem weiterhin nachführt.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    pseudonym = "pseudo-anzeigename"
    sso = "unterricht.ch2-ks-abi28"
    try:
        await sync_groups(
            await _session(factory), pseudonym, [sso], "teacher", PATTERNS
        )
        async with factory() as db:
            gruppe = (await db.execute(
                select(Group).where(Group.sso_group_id == sso.lower())
            )).scalar_one()
            roh = gruppe.name
            gruppe.display_name = "Chemie LK Abi 28"
            await db.commit()

        # Zweite Anmeldung — dabei schreibt der Sync `name` neu.
        await sync_groups(
            await _session(factory), pseudonym, [sso], "teacher", PATTERNS
        )
        async with factory() as db:
            gruppe = (await db.execute(
                select(Group).where(Group.sso_group_id == sso.lower())
            )).scalar_one()
            assert gruppe.display_name == "Chemie LK Abi 28"
            assert gruppe.name == roh, "der rohe Name wird weiter vom Schulkonto geführt"
            assert gruppe.anzeigename == "Chemie LK Abi 28"
    finally:
        async with factory() as db:
            await db.execute(delete(GroupMembership).where(
                GroupMembership.pseudonym == pseudonym))
            await db.execute(delete(Group).where(Group.sso_group_id == sso.lower()))
            await db.commit()


# ── Alembic 0068: Herkunft entscheidet, mehrere Quellklassen tragen ──────────


class TestHerkunftUndMehrereQuellklassen:
    """Was der Vererbungslauf anfassen darf — und woher eine Gruppe erben kann.

    Bis Alembic 0068 räumte der Abgangslauf nach `role_in_group == 'student'` auf. Das
    war richtig, solange jede Schüler-Mitgliedschaft geerbt war. Mit dem Beitrittscode
    (AP4) stimmt das nicht mehr: Ein Nachzügler tritt per Code einer Gruppe bei, die
    durchaus eine Quellklasse hat — und darf beim nächsten Login nicht herausfliegen.
    """

    async def test_code_beitritt_ueberlebt_den_login(self, async_engine):
        """Die Gegenprobe zum Abgangslauf.

        ⚠️ **Der Wächter für AP2 Punkt 4.** Stellt man die Löschbedingung wieder auf
        `GroupMembership.role_in_group == "student"` um, fällt dieser Test — und genau
        das wäre der Bruch, den der Beitrittscode nicht überleben würde.
        """
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        lehrkraft, nachzuegler = "hk-lehrkraft", "hk-nachzuegler"
        try:
            async with factory() as db:
                fach_id = await _get_or_create_subject(db, "hk-fach", "Herkunftskunde")
                klasse = Group(name="8b", slug="klasse-8b-hk", type="school_class",
                               sso_group_id="klasse.8b-hk")
                db.add(klasse)
                await db.flush()
                gruppe_id = await _adoptierte_gruppe(db, fach_id, klasse.id, lehrkraft)
                # Der Nachzügler ist **nicht** in der Quellklasse — er ist per Code drin.
                db.add(GroupMembership(
                    group_id=gruppe_id, pseudonym=nachzuegler,
                    role_in_group="student", herkunft="code",
                ))
                await db.commit()

            # Login ohne die Quellklasse: Der Abgangslauf läuft und findet ihn.
            async with factory() as db:
                await sync_groups(db=db, pseudonym=nachzuegler, sso_groups=[],
                                  primary_role="student", patterns=OHNE_UNTERRICHT)

            async with factory() as db:
                geblieben = (await db.execute(
                    select(GroupMembership.herkunft).where(
                        GroupMembership.pseudonym == nachzuegler,
                        GroupMembership.group_id == gruppe_id,
                    )
                )).scalar_one_or_none()
            assert geblieben == "code", (
                "Der Code-Beitritt wurde vom Vererbungslauf entfernt — dann ist die "
                "Löschbedingung wieder an der Rolle statt an der Herkunft."
            )
        finally:
            async with factory() as db:
                await db.execute(delete(GroupMembership).where(
                    GroupMembership.pseudonym.in_([lehrkraft, nachzuegler])))
                await db.execute(delete(Group).where(
                    Group.slug.in_(["klasse-8b-hk", "teaching-adoptiert-"])))
                await db.execute(delete(Group).where(Group.slug.like("teaching-adoptiert-%")))
                await db.execute(delete(Subject).where(Subject.slug == "hk-fach"))
                await db.commit()

    async def test_geerbte_mitgliedschaft_faellt_weiterhin(self, async_engine):
        """Die Kehrseite: Was geerbt ist, verschwindet beim Klassenwechsel weiterhin.

        Ohne diesen Test wäre `test_code_beitritt_ueberlebt_den_login` auch dann grün,
        wenn der Abgangslauf **gar nichts** mehr löschte.
        """
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        lehrkraft, schuelerin = "hk2-lehrkraft", "hk2-schuelerin"
        try:
            async with factory() as db:
                fach_id = await _get_or_create_subject(db, "hk2-fach", "Herkunftskunde 2")
                klasse = Group(name="8c", slug="klasse-8c-hk2", type="school_class",
                               sso_group_id="klasse.8c-hk2")
                db.add(klasse)
                await db.flush()
                gruppe_id = await _adoptierte_gruppe(db, fach_id, klasse.id, lehrkraft)
                await db.commit()

            async with factory() as db:
                await sync_groups(db=db, pseudonym=schuelerin,
                                  sso_groups=["klasse.8c-hk2"],
                                  primary_role="student", patterns=OHNE_UNTERRICHT)
            async with factory() as db:
                assert (await db.execute(
                    select(GroupMembership.herkunft).where(
                        GroupMembership.pseudonym == schuelerin,
                        GroupMembership.group_id == gruppe_id,
                    )
                )).scalar_one_or_none() == "geerbt"

            # Klassenwechsel: Die Quellklasse passt nicht mehr.
            async with factory() as db:
                await sync_groups(db=db, pseudonym=schuelerin, sso_groups=[],
                                  primary_role="student", patterns=OHNE_UNTERRICHT)
            async with factory() as db:
                assert (await db.execute(
                    select(GroupMembership.herkunft).where(
                        GroupMembership.pseudonym == schuelerin,
                        GroupMembership.group_id == gruppe_id,
                    )
                )).scalar_one_or_none() is None, "geerbte Mitgliedschaft muss fallen"
        finally:
            async with factory() as db:
                await db.execute(delete(GroupMembership).where(
                    GroupMembership.pseudonym.in_([lehrkraft, schuelerin])))
                await db.execute(delete(Group).where(Group.slug.like("teaching-adoptiert-%")))
                await db.execute(delete(Group).where(Group.slug == "klasse-8c-hk2"))
                await db.execute(delete(Subject).where(Subject.slug == "hk2-fach"))
                await db.commit()

    async def test_gruppe_aus_drei_klassen_vererbt_an_niemanden(self, async_engine):
        """⚠️ **NwT 10a/10b/10c erbt nicht** (Befund Jan, 23.09.2026).

        Eine Gruppe über mehreren Klassen ist per Konstruktion eine **Auswahl** aus
        diesen Klassen — sonst würde sie je Klasse unterrichtet. Alle drei Klassen
        hineinzuschreiben gäbe Schüler:innen Zugang zu einer Gruppe, in der sie nicht
        sind: fremde Assistenten-Freigaben, fremder Unterrichtskontext. Solche Gruppen
        füllen sich über einen Beitrittscode oder über eine SSO-Gruppe.

        Die Herkunft bleibt trotzdem gespeichert (`group_source_classes`) — sie trägt die
        Stundenplan-Zuordnung und die Jahrgangsableitung. Nur **Mitgliedschaft** folgt
        daraus nicht.
        """
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        schueler = ["nwt-a", "nwt-b", "nwt-c"]
        klassen_slugs = ["klasse-10a-nwt", "klasse-10b-nwt", "klasse-10c-nwt"]
        try:
            async with factory() as db:
                fach_id = await _get_or_create_subject(db, "nwt-fach", "NwT")
                klassen = []
                for name, slug in zip(["10a", "10b", "10c"], klassen_slugs):
                    k = Group(name=name, slug=slug, type="school_class",
                              sso_group_id=f"klasse.{name}-nwt")
                    db.add(k)
                    klassen.append(k)
                await db.flush()
                gruppe = Group(name="NwT 10", slug="teaching-nwt-10",
                               type="teaching_group", subject_id=fach_id, sso_group_id=None,
                               # Vorbelegung bei mehreren Klassen: Teilgruppe.
                               erbt_mitglieder=False)
                db.add(gruppe)
                await db.flush()
                for k in klassen:
                    db.add(GroupSourceClass(group_id=gruppe.id, class_group_id=k.id))
                db.add(GroupMembership(group_id=gruppe.id, pseudonym="nwt-lehrkraft",
                                       role_in_group="teacher", herkunft="eigen"))
                gruppe_id = gruppe.id
                await db.commit()

            for pseudo, name in zip(schueler, ["10a", "10b", "10c"]):
                async with factory() as db:
                    await sync_groups(db=db, pseudonym=pseudo,
                                      sso_groups=[f"klasse.{name}-nwt"],
                                      primary_role="student", patterns=OHNE_UNTERRICHT)

            async with factory() as db:
                drin = (await db.execute(
                    select(GroupMembership.pseudonym).where(
                        GroupMembership.group_id == gruppe_id,
                        GroupMembership.herkunft == "geerbt",
                    )
                )).scalars().all()
                quellen = (await db.execute(
                    select(GroupSourceClass.class_group_id).where(
                        GroupSourceClass.group_id == gruppe_id)
                )).scalars().all()
            assert drin == [], (
                "Eine mehrklassige Gruppe hat vererbt — damit sitzen Schüler:innen in "
                "einer Gruppe, in der sie nicht sind."
            )
            assert len(quellen) == 3, "die Herkunft bleibt gespeichert, nur die Vererbung nicht"
        finally:
            async with factory() as db:
                await db.execute(delete(GroupMembership).where(
                    GroupMembership.pseudonym.in_([*schueler, "nwt-lehrkraft"])))
                await db.execute(delete(Group).where(Group.slug == "teaching-nwt-10"))
                await db.execute(delete(Group).where(Group.slug.in_(klassen_slugs)))
                await db.execute(delete(Subject).where(Subject.slug == "nwt-fach"))
                await db.commit()


async def _session(factory) -> AsyncSession:
    """`sync_groups` committet selbst — es bekommt deshalb eine eigene Sitzung."""
    return factory()


class TestEntscheidungIstKorrigierbar:
    """Von „ganze Klasse" auf „Teilgruppe" umzustellen muss die Mitglieder abräumen.

    Sonst wäre die Entscheidung nur in eine Richtung korrigierbar: Wer sich beim Anlegen
    vertut, bekäme die zu viel geerbten Schüler:innen nie wieder heraus — manuelle
    Mitgliederpflege gibt es nicht.
    """

    async def test_umschalten_auf_teilgruppe_raeumt_ab(self, async_engine):
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        lehrkraft, schuelerin = "flip-lehrkraft", "flip-schuelerin"
        try:
            async with factory() as db:
                fach_id = await _get_or_create_subject(db, "flip-fach", "Umschaltkunde")
                klasse = Group(name="7e", slug="klasse-7e-flip", type="school_class",
                               sso_group_id="klasse.7e-flip")
                db.add(klasse)
                await db.flush()
                gruppe_id = await _adoptierte_gruppe(db, fach_id, klasse.id, lehrkraft)
                await db.commit()

            # Erst erben …
            async with factory() as db:
                await sync_groups(db=db, pseudonym=schuelerin,
                                  sso_groups=["klasse.7e-flip"],
                                  primary_role="student", patterns=OHNE_UNTERRICHT)
            async with factory() as db:
                assert (await db.execute(
                    select(GroupMembership.herkunft).where(
                        GroupMembership.pseudonym == schuelerin,
                        GroupMembership.group_id == gruppe_id)
                )).scalar_one_or_none() == "geerbt"

            # … dann die Entscheidung drehen.
            async with factory() as db:
                gruppe = await db.get(Group, gruppe_id)
                gruppe.erbt_mitglieder = False
                await db.commit()

            async with factory() as db:
                await sync_groups(db=db, pseudonym=schuelerin,
                                  sso_groups=["klasse.7e-flip"],
                                  primary_role="student", patterns=OHNE_UNTERRICHT)
            async with factory() as db:
                geblieben = (await db.execute(
                    select(GroupMembership.herkunft).where(
                        GroupMembership.pseudonym == schuelerin,
                        GroupMembership.group_id == gruppe_id)
                )).scalar_one_or_none()
            assert geblieben is None, (
                "Nach dem Umschalten auf Teilgruppe muss die geerbte Mitgliedschaft "
                "fallen — sonst ist die Entscheidung nicht korrigierbar."
            )
        finally:
            async with factory() as db:
                await db.execute(delete(GroupMembership).where(
                    GroupMembership.pseudonym.in_([lehrkraft, schuelerin])))
                await db.execute(delete(Group).where(Group.slug.like("teaching-adoptiert-%")))
                await db.execute(delete(Group).where(Group.slug == "klasse-7e-flip"))
                await db.execute(delete(Subject).where(Subject.slug == "flip-fach"))
                await db.commit()
