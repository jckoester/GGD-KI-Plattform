"""AP4: Beitrittscode gegen die Datenbank — Einlösen, Rücknahme, Abgrenzung.

Die wichtigste Zusage steht in `test_ruecknahme_laesst_geerbte_stehen`: Die Rücknahme
darf **nur** Code-Beitritte treffen. Träfe sie auch geerbte Mitgliedschaften, würfe eine
Lehrkraft beim Aufräumen eines Fehlbeitritts die halbe Klasse hinaus — ohne Namen und
damit ohne Chance, es zu bemerken.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Group, GroupJoinCode, GroupMembership, Subject
from app.groups.beitritt import (
    aktueller_code,
    beitritte_je_tag,
    erzeuge_code,
    loese_ein,
    nimm_beitritte_zurueck,
    widerrufe_codes,
)

LEHRKRAFT = "bc-lehrkraft"
SCHUELER = ["bc-a", "bc-b", "bc-c"]


async def _gruppe(db) -> int:
    fach = (await db.execute(
        select(Subject).where(Subject.slug == "bc-fach")
    )).scalar_one_or_none()
    if fach is None:
        fach = Subject(slug="bc-fach", name="Beitrittskunde")
        db.add(fach)
        await db.flush()
    gruppe = Group(name="BC 11", slug="teaching-bc-11", type="teaching_group",
                   subject_id=fach.id, sso_group_id=None)
    db.add(gruppe)
    await db.flush()
    db.add(GroupMembership(group_id=gruppe.id, pseudonym=LEHRKRAFT,
                           role_in_group="teacher", herkunft="eigen"))
    await db.flush()
    return gruppe.id


async def _aufraeumen(factory):
    async with factory() as db:
        await db.execute(delete(GroupMembership).where(
            GroupMembership.pseudonym.in_([LEHRKRAFT, *SCHUELER])))
        await db.execute(delete(Group).where(Group.slug == "teaching-bc-11"))
        await db.execute(delete(Subject).where(Subject.slug == "bc-fach"))
        await db.commit()


def _f(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Einlösen ─────────────────────────────────────────────────────────────────


async def test_einloesen_macht_zum_mitglied(async_engine):
    factory = _f(async_engine)
    try:
        async with factory() as db:
            gid = await _gruppe(db)
            code = await erzeuge_code(db, gid, LEHRKRAFT)
            roh = code.code
            await db.commit()

        async with factory() as db:
            _, lage = await loese_ein(db, roh, SCHUELER[0])
            await db.commit()
        assert lage.gueltig

        async with factory() as db:
            zeile = (await db.execute(
                select(GroupMembership).where(
                    GroupMembership.group_id == gid,
                    GroupMembership.pseudonym == SCHUELER[0])
            )).scalar_one()
        assert zeile.herkunft == "code"
        assert zeile.role_in_group == "student"
        assert zeile.join_code_id is not None
        assert zeile.beigetreten_am is not None
    finally:
        await _aufraeumen(factory)


async def test_zweimal_einloesen_bleibt_eine_mitgliedschaft(async_engine):
    factory = _f(async_engine)
    try:
        async with factory() as db:
            gid = await _gruppe(db)
            roh = (await erzeuge_code(db, gid, LEHRKRAFT)).code
            await db.commit()
        for _ in range(2):
            async with factory() as db:
                await loese_ein(db, roh, SCHUELER[0])
                await db.commit()
        async with factory() as db:
            n = len((await db.execute(
                select(GroupMembership).where(
                    GroupMembership.group_id == gid,
                    GroupMembership.pseudonym == SCHUELER[0])
            )).scalars().all())
        assert n == 1
    finally:
        await _aufraeumen(factory)


async def test_geerbtes_mitglied_bleibt_geerbt(async_engine):
    """⚠️ Wer schon geerbt drin ist und trotzdem den Code eintippt, bleibt **geerbt**.

    Würde die Herkunft auf `code` umgeschrieben, fiele die Person beim Klassenwechsel
    nicht mehr aus der Gruppe — der Vererbungslauf räumt nur `geerbt` ab.
    """
    factory = _f(async_engine)
    try:
        async with factory() as db:
            gid = await _gruppe(db)
            roh = (await erzeuge_code(db, gid, LEHRKRAFT)).code
            db.add(GroupMembership(group_id=gid, pseudonym=SCHUELER[0],
                                   role_in_group="student", herkunft="geerbt"))
            await db.commit()

        async with factory() as db:
            await loese_ein(db, roh, SCHUELER[0])
            await db.commit()

        async with factory() as db:
            zeile = (await db.execute(
                select(GroupMembership).where(
                    GroupMembership.group_id == gid,
                    GroupMembership.pseudonym == SCHUELER[0])
            )).scalar_one()
        assert zeile.herkunft == "geerbt"
    finally:
        await _aufraeumen(factory)


async def test_abgelaufener_und_widerrufener_code_tragen_nicht(async_engine):
    factory = _f(async_engine)
    try:
        async with factory() as db:
            gid = await _gruppe(db)
            code = await erzeuge_code(db, gid, LEHRKRAFT)
            code.gueltig_bis = datetime.now(UTC) - timedelta(minutes=1)
            roh = code.code
            await db.commit()
        async with factory() as db:
            _, lage = await loese_ein(db, roh, SCHUELER[0])
            await db.rollback()
        assert lage.grund == "abgelaufen"

        async with factory() as db:
            roh2 = (await erzeuge_code(db, gid, LEHRKRAFT)).code
            await widerrufe_codes(db, gid)
            await db.commit()
        async with factory() as db:
            _, lage2 = await loese_ein(db, roh2, SCHUELER[0])
            await db.rollback()
        assert lage2.grund == "unbekannt"
    finally:
        await _aufraeumen(factory)


async def test_erneuern_entwertet_den_alten(async_engine):
    """Zwei gleichzeitig gültige Codes wären nicht erklärbar."""
    factory = _f(async_engine)
    try:
        async with factory() as db:
            gid = await _gruppe(db)
            alt = (await erzeuge_code(db, gid, LEHRKRAFT)).code
            await db.commit()
        async with factory() as db:
            neu = (await erzeuge_code(db, gid, LEHRKRAFT)).code
            await db.commit()
        assert alt != neu
        async with factory() as db:
            _, lage = await loese_ein(db, alt, SCHUELER[0])
            await db.rollback()
        assert not lage.gueltig
    finally:
        await _aufraeumen(factory)


# ── Rücknahme ────────────────────────────────────────────────────────────────


async def test_ruecknahme_laesst_geerbte_stehen(async_engine):
    """⚠️ **Die wichtigste Zusage von AP4.**

    Entfernt die Rücknahme mehr als Code-Beitritte, wirft eine Lehrkraft beim Aufräumen
    eines Fehlbeitritts die halbe Klasse hinaus — ohne Namen und damit ohne Chance, es
    zu bemerken.
    """
    factory = _f(async_engine)
    try:
        async with factory() as db:
            gid = await _gruppe(db)
            roh = (await erzeuge_code(db, gid, LEHRKRAFT)).code
            db.add(GroupMembership(group_id=gid, pseudonym=SCHUELER[2],
                                   role_in_group="student", herkunft="geerbt"))
            await db.commit()

        for p in SCHUELER[:2]:
            async with factory() as db:
                await loese_ein(db, roh, p)
                await db.commit()

        async with factory() as db:
            code = await aktueller_code(db, gid)
            entfernt = await nimm_beitritte_zurueck(db, code.id)
            await db.commit()
        assert entfernt == 2

        async with factory() as db:
            uebrig = {
                z.pseudonym: z.herkunft for z in (await db.execute(
                    select(GroupMembership).where(GroupMembership.group_id == gid)
                )).scalars().all()
            }
        assert uebrig == {LEHRKRAFT: "eigen", SCHUELER[2]: "geerbt"}, (
            "Die Rücknahme hat mehr als Code-Beitritte getroffen."
        )
    finally:
        await _aufraeumen(factory)


async def test_ruecknahme_widerruft_den_code(async_engine):
    """Ohne Widerruf treten dieselben Falschen sofort wieder bei."""
    factory = _f(async_engine)
    try:
        async with factory() as db:
            gid = await _gruppe(db)
            roh = (await erzeuge_code(db, gid, LEHRKRAFT)).code
            await db.commit()
        async with factory() as db:
            await loese_ein(db, roh, SCHUELER[0])
            await db.commit()
        async with factory() as db:
            code = await aktueller_code(db, gid)
            await nimm_beitritte_zurueck(db, code.id)
            await db.commit()

        async with factory() as db:
            _, lage = await loese_ein(db, roh, SCHUELER[0])
            await db.rollback()
        assert not lage.gueltig, "Der zurückgenommene Code gilt weiter — Rücknahme folgenlos."
    finally:
        await _aufraeumen(factory)


async def test_beitritte_je_tag_zaehlt_ohne_namen(async_engine):
    factory = _f(async_engine)
    try:
        async with factory() as db:
            gid = await _gruppe(db)
            roh = (await erzeuge_code(db, gid, LEHRKRAFT)).code
            await db.commit()
        for p in SCHUELER:
            async with factory() as db:
                await loese_ein(db, roh, p)
                await db.commit()

        async with factory() as db:
            code = await aktueller_code(db, gid)
            tage = await beitritte_je_tag(db, code.id)
        assert sum(t.anzahl for t in tage) == 3
        # Der Rückgabetyp trägt **nur** Tag und Anzahl — keine Pseudonyme.
        assert set(vars(tage[0])) == {"tag", "anzahl"}
    finally:
        await _aufraeumen(factory)


async def test_ruecknahme_eines_tages_trifft_nur_diesen(async_engine):
    """Eine Runde lief über zwei Tage, nur der zweite ging schief."""
    factory = _f(async_engine)
    try:
        async with factory() as db:
            gid = await _gruppe(db)
            code = await erzeuge_code(db, gid, LEHRKRAFT)
            roh, code_id = code.code, code.id
            await db.commit()

        gestern = datetime.now(UTC) - timedelta(days=1)
        async with factory() as db:
            await loese_ein(db, roh, SCHUELER[0], jetzt=gestern)
            await db.commit()
        async with factory() as db:
            await loese_ein(db, roh, SCHUELER[1])
            await db.commit()

        async with factory() as db:
            entfernt = await nimm_beitritte_zurueck(db, code_id, tag=gestern.date())
            await db.commit()
        assert entfernt == 1

        async with factory() as db:
            uebrig = {p for (p,) in (await db.execute(
                select(GroupMembership.pseudonym).where(
                    GroupMembership.group_id == gid,
                    GroupMembership.herkunft == "code")
            )).all()}
        assert uebrig == {SCHUELER[1]}
    finally:
        await _aufraeumen(factory)
