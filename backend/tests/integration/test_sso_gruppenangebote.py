"""AP1: Unbekannte SSO-Unterrichtsgruppen werden angeboten, nicht angelegt.

**Der Befund dahinter** (gemessen 23.09.2026): Die alte Adoptionsheuristik suchte über
`(Lehrkraft, Fach)` und endete auf `scalar_one_or_none()`. Eine Lehrkraft mit *Chemie 9c*
**und** *Chemie 9d* traf zwei Zeilen — `MultipleResultsFound`, und weil `sync_groups`
ungeschützt im Login-Pfad lief, endete die Anmeldung mit 500.

Der Schlüssel war nicht unscharf, sondern falsch: Zwei Gruppen im selben Fach sind der
**Normalfall** (getrennter Unterricht, eigene Termine, eigene Ausfälle, je ein eigener
Stundenplan-Eintrag). Geraten wird deshalb gar nichts mehr.
"""
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.config import SsoGroupPatterns
from app.auth.group_sync import sync_groups
from app.db.models import (
    Group, GroupMembership, GroupSourceClass, SsoGroupOffer, Subject,
)

MUSTER = SsoGroupPatterns(
    teachers=r"^lehrer$",
    school_class=r"^klasse\.(.+)$",
    subject_department=r"^fs\.(.+)$",
    teaching_group=r"^unterricht\.(.+)$",
    activity_group=r"^ag\.(.+)$",
)
LK = "angebot-lk"


def _f(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _fach(db) -> int:
    fach = (await db.execute(
        select(Subject).where(Subject.slug == "angebot-ch")
    )).scalar_one_or_none()
    if fach is None:
        fach = Subject(slug="angebot-ch", name="Angebotschemie", fach_code="CH")
        db.add(fach)
        await db.flush()
    return fach.id


async def _gruppe(db, fach_id, name, slug, klasse_id=None) -> int:
    g = Group(name=name, slug=slug, type="teaching_group",
              subject_id=fach_id, sso_group_id=None, erbt_mitglieder=bool(klasse_id))
    db.add(g)
    await db.flush()
    if klasse_id:
        db.add(GroupSourceClass(group_id=g.id, class_group_id=klasse_id))
    db.add(GroupMembership(group_id=g.id, pseudonym=LK,
                           role_in_group="teacher", herkunft="eigen"))
    await db.flush()
    return g.id


async def _aufraeumen(factory):
    async with factory() as db:
        await db.execute(delete(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK))
        await db.execute(delete(GroupMembership).where(GroupMembership.pseudonym == LK))
        for spalte in (Group.slug.like("angebot-%"), Group.sso_group_id.like("unterricht.angebot%")):
            await db.execute(delete(Group).where(spalte))
        await db.execute(delete(Subject).where(Subject.slug == "angebot-ch"))
        await db.commit()


# ── Der Absturz ──────────────────────────────────────────────────────────────


async def test_zwei_gruppen_desselben_fachs_sperren_niemanden_aus(async_engine):
    """⚠️ **Der Wächter über den Login.**

    *Chemie 9c* und *Chemie 9d* **müssen** getrennte Unterrichtsgruppen sein. Kommt dann
    eine Chemie-Unterrichtsgruppe aus dem SSO, darf der Sync weder abstürzen noch eine
    der beiden willkürlich verschmelzen.
    """
    factory = _f(async_engine)
    try:
        async with factory() as db:
            fach_id = await _fach(db)
            await _gruppe(db, fach_id, "Chemie 9c", "angebot-ch-9c")
            await _gruppe(db, fach_id, "Chemie 9d", "angebot-ch-9d")
            await db.commit()

        async with factory() as db:
            await sync_groups(db=db, pseudonym=LK,
                              sso_groups=["unterricht.angebot9d.ch"],
                              primary_role="teacher", patterns=MUSTER)

        async with factory() as db:
            verknuepft = (await db.execute(
                select(Group.name).where(Group.sso_group_id.is_not(None),
                                         Group.slug.like("angebot-%"))
            )).scalars().all()
        assert verknuepft == [], (
            "Eine der beiden Gruppen wurde verschmolzen — damit stecken zwei "
            "Jahrespläne ineinander."
        )
    finally:
        await _aufraeumen(factory)


# ── Angeboten statt angelegt ─────────────────────────────────────────────────


async def test_unbekannte_unterrichtsgruppe_wird_angeboten(async_engine):
    factory = _f(async_engine)
    try:
        async with factory() as db:
            await _fach(db)
            await db.commit()

        async with factory() as db:
            await sync_groups(db=db, pseudonym=LK,
                              sso_groups=["unterricht.angebot9d.ch"],
                              primary_role="teacher", patterns=MUSTER)

        async with factory() as db:
            angebote = (await db.execute(
                select(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK)
            )).scalars().all()
            gruppen = (await db.execute(
                select(Group).where(Group.sso_group_id == "unterricht.angebot9d.ch")
            )).scalars().all()

        assert len(angebote) == 1, "Kein Angebot hinterlegt"
        assert angebote[0].sso_group_id == "unterricht.angebot9d.ch"
        assert angebote[0].ignoriert_am is None
        assert gruppen == [], "Es wurde trotzdem eine Gruppe angelegt"
    finally:
        await _aufraeumen(factory)


async def test_klassen_entstehen_weiterhin_automatisch(async_engine):
    """⚠️ **Die Abgrenzung.** Nur Unterrichtsgruppen werden angeboten.

    Klassen sind keine Entscheidung — und die Vererbung hängt an ihnen. Würden auch sie
    nur angeboten, bekäme niemand mehr Mitglieder, bis jemand eine Liste abarbeitet.
    """
    factory = _f(async_engine)
    try:
        async with factory() as db:
            await sync_groups(db=db, pseudonym=LK,
                              sso_groups=["klasse.angebot9d"],
                              primary_role="student", patterns=MUSTER)

        async with factory() as db:
            klasse = (await db.execute(
                select(Group).where(Group.sso_group_id == "klasse.angebot9d")
            )).scalar_one_or_none()
            angebote = (await db.execute(
                select(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK)
            )).scalars().all()
        assert klasse is not None, "Die Klasse wurde nicht angelegt"
        assert angebote == [], "Für eine Klasse darf kein Angebot entstehen"
    finally:
        async with factory() as db:
            await db.execute(delete(GroupMembership).where(GroupMembership.pseudonym == LK))
            await db.execute(delete(Group).where(Group.sso_group_id == "klasse.angebot9d"))
            await db.commit()
        await _aufraeumen(factory)


async def test_verknuepfte_gruppe_erzeugt_kein_angebot(async_engine):
    """Ist die Gruppe schon zugeordnet, gibt es nichts zu fragen."""
    factory = _f(async_engine)
    try:
        async with factory() as db:
            fach_id = await _fach(db)
            g = Group(name="Chemie 9d", slug="angebot-verknuepft",
                      type="teaching_group", subject_id=fach_id,
                      sso_group_id="unterricht.angebot9d.ch")
            db.add(g)
            await db.flush()
            db.add(GroupMembership(group_id=g.id, pseudonym=LK,
                                   role_in_group="teacher", herkunft="sso"))
            await db.commit()

        async with factory() as db:
            await sync_groups(db=db, pseudonym=LK,
                              sso_groups=["unterricht.angebot9d.ch"],
                              primary_role="teacher", patterns=MUSTER)

        async with factory() as db:
            angebote = (await db.execute(
                select(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK)
            )).scalars().all()
        assert angebote == []
    finally:
        await _aufraeumen(factory)


async def test_ignoriertes_angebot_kehrt_nicht_zurueck(async_engine):
    """⚠️ Sonst wäre die Ablehnung eine Dauerfrage.

    Der Sync läuft bei **jedem** Login. Würde er ein abgelehntes Angebot neu anlegen
    oder `ignoriert_am` zurücksetzen, stünde dieselbe Frage jeden Morgen wieder da.
    """
    factory = _f(async_engine)
    try:
        async with factory() as db:
            await _fach(db)
            await db.commit()
        async with factory() as db:
            await sync_groups(db=db, pseudonym=LK,
                              sso_groups=["unterricht.angebot9d.ch"],
                              primary_role="teacher", patterns=MUSTER)

        from datetime import UTC, datetime
        async with factory() as db:
            angebot = (await db.execute(
                select(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK)
            )).scalar_one()
            angebot.ignoriert_am = datetime.now(UTC)
            await db.commit()

        # Nächster Login.
        async with factory() as db:
            await sync_groups(db=db, pseudonym=LK,
                              sso_groups=["unterricht.angebot9d.ch"],
                              primary_role="teacher", patterns=MUSTER)

        async with factory() as db:
            angebot = (await db.execute(
                select(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK)
            )).scalar_one()
        assert angebot.ignoriert_am is not None, "Die Ablehnung wurde zurückgesetzt"
    finally:
        await _aufraeumen(factory)


async def test_nachgezogene_fachableitung_erreicht_das_angebot(async_engine):
    """Wird `auth.yaml` repariert, bekommt das Angebot sein Fach — ohne neue Zeile."""
    factory = _f(async_engine)
    ohne_fach = SsoGroupPatterns(
        teachers=r"^lehrer$", school_class=r"^klasse\.(.+)$",
        subject_department=r"^fs\.(.+)$",
        teaching_group=r"^unterricht\.(?P<rest>.+)$",
        activity_group=r"^ag\.(.+)$",
    )
    try:
        async with factory() as db:
            fach_id = await _fach(db)
            await db.commit()

        async with factory() as db:
            await sync_groups(db=db, pseudonym=LK, sso_groups=["unterricht.angebot9d"],
                              primary_role="teacher", patterns=ohne_fach)
        async with factory() as db:
            vorher = (await db.execute(
                select(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK)
            )).scalar_one()
            assert vorher.subject_id is None
            id_vorher = vorher.id

        async with factory() as db:
            await sync_groups(db=db, pseudonym=LK,
                              sso_groups=["unterricht.angebot9d.ch"],
                              primary_role="teacher", patterns=MUSTER)

        async with factory() as db:
            alle = (await db.execute(
                select(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK)
            )).scalars().all()
        # Zwei verschiedene SSO-IDs → zwei Angebote; das zweite trägt das Fach.
        mit_fach = [a for a in alle if a.subject_id == fach_id]
        assert mit_fach, "Das Fach kam nicht am Angebot an"
        assert any(a.id == id_vorher for a in alle), "Das erste Angebot verschwand"
    finally:
        await _aufraeumen(factory)


async def test_verknuepfung_loest_angebote_aller_lehrkraefte_auf(async_engine):
    """⚠️ **Entscheidung F2: Die erste Bestätigung gilt für alle.**

    Hat eine Kollegin die Gruppe verknüpft, muss das Angebot auch bei den übrigen
    verschwinden — sonst legt die zweite Antwort eine Doppelgruppe an, also genau das,
    was dieser Weg verhindern soll.
    """
    factory = _f(async_engine)
    zweite = "angebot-lk2"
    try:
        async with factory() as db:
            await _fach(db)
            await db.commit()
        # Beide sehen dieselbe SSO-Gruppe.
        for wer in (LK, zweite):
            async with factory() as db:
                await sync_groups(db=db, pseudonym=wer,
                                  sso_groups=["unterricht.angebot9d.ch"],
                                  primary_role="teacher", patterns=MUSTER)
        async with factory() as db:
            offen = (await db.execute(
                select(SsoGroupOffer).where(
                    SsoGroupOffer.sso_group_id == "unterricht.angebot9d.ch")
            )).scalars().all()
        assert len(offen) == 2, "Beide Lehrkräfte sollten ein eigenes Angebot haben"

        # Die erste verknüpft — hier abgekürzt über den Sync einer vorhandenen Gruppe.
        async with factory() as db:
            fach_id = await _fach(db)
            g = Group(name="Chemie 9d", slug="angebot-erste",
                      type="teaching_group", subject_id=fach_id,
                      sso_group_id="unterricht.angebot9d.ch")
            db.add(g)
            await db.flush()
            db.add(GroupMembership(group_id=g.id, pseudonym=LK,
                                   role_in_group="teacher", herkunft="sso"))
            await db.commit()
        async with factory() as db:
            await sync_groups(db=db, pseudonym=LK,
                              sso_groups=["unterricht.angebot9d.ch"],
                              primary_role="teacher", patterns=MUSTER)

        async with factory() as db:
            uebrig = (await db.execute(
                select(SsoGroupOffer).where(
                    SsoGroupOffer.sso_group_id == "unterricht.angebot9d.ch")
            )).scalars().all()
        assert uebrig == [], (
            "Das Angebot der zweiten Lehrkraft steht noch — sie würde eine Doppelgruppe "
            "anlegen."
        )
    finally:
        async with factory() as db:
            await db.execute(delete(SsoGroupOffer).where(SsoGroupOffer.pseudonym == zweite))
            await db.execute(delete(GroupMembership).where(GroupMembership.pseudonym == zweite))
            await db.commit()
        await _aufraeumen(factory)


# ── AP2: Die Bestätigung ─────────────────────────────────────────────────────


async def test_zuordnen_verknuepft_und_raeumt_geerbte_weg(async_engine):
    """⚠️ **Geerbte Mitgliedschaften müssen beim Verknüpfen fallen.**

    Ab der Zuordnung führt das Schulkonto die Mitglieder; die Vererbung aus der Klasse
    ist für SSO-Gruppen abgeschaltet. Bliebe das Geerbte stehen, räumte es **niemand**
    mehr auf — auch der Immediate Mirror nicht, der nur `sso` anfasst. Zwei Wahrheiten
    über die Mitgliedschaft, und eine davon eingefroren.
    """
    from app.groups.angebote import ordne_zu

    factory = _f(async_engine)
    try:
        async with factory() as db:
            fach_id = await _fach(db)
            klasse = Group(name="9d", slug="angebot-klasse-9d", type="school_class")
            db.add(klasse)
            await db.flush()
            gid = await _gruppe(db, fach_id, "Chemie 9d", "angebot-vorhanden", klasse.id)
            db.add(GroupMembership(group_id=gid, pseudonym="angebot-schueler",
                                   role_in_group="student", herkunft="geerbt"))
            db.add(GroupMembership(group_id=gid, pseudonym="angebot-code",
                                   role_in_group="student", herkunft="code"))
            await db.commit()

        async with factory() as db:
            await sync_groups(db=db, pseudonym=LK,
                              sso_groups=["unterricht.angebot9d.ch"],
                              primary_role="teacher", patterns=MUSTER)

        async with factory() as db:
            angebot = (await db.execute(
                select(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK)
            )).scalar_one()
            ergebnis = await ordne_zu(db, angebot.id, gid, LK)
            await db.commit()

        assert ergebnis.geerbte_entfernt == 1
        async with factory() as db:
            gruppe = await db.get(Group, gid)
            herkuenfte = sorted((await db.execute(
                select(GroupMembership.herkunft).where(GroupMembership.group_id == gid)
            )).scalars().all())
            offen = (await db.execute(
                select(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK)
            )).scalars().all()

        assert gruppe.sso_group_id == "unterricht.angebot9d.ch"
        assert gruppe.erbt_mitglieder is False, "Vererbung muss abgeschaltet sein"
        assert herkuenfte == ["code", "eigen"], (
            "Geerbtes muss fallen, Code-Beitritte müssen bleiben — sie sind die "
            "Entscheidung eines Menschen."
        )
        assert offen == [], "Das beantwortete Angebot steht noch"
    finally:
        async with factory() as db:
            for p in ("angebot-schueler", "angebot-code"):
                await db.execute(delete(GroupMembership).where(GroupMembership.pseudonym == p))
            await db.execute(delete(Group).where(Group.slug == "angebot-klasse-9d"))
            await db.commit()
        await _aufraeumen(factory)


async def test_fremdes_angebot_laesst_sich_nicht_beantworten(async_engine):
    """Wem ein Angebot gehört, geht niemand anderen etwas an."""
    from app.groups.angebote import ignoriere

    factory = _f(async_engine)
    try:
        async with factory() as db:
            await _fach(db)
            await db.commit()
        async with factory() as db:
            await sync_groups(db=db, pseudonym=LK,
                              sso_groups=["unterricht.angebot9d.ch"],
                              primary_role="teacher", patterns=MUSTER)
        async with factory() as db:
            angebot = (await db.execute(
                select(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK)
            )).scalar_one()
            with pytest.raises(LookupError):
                await ignoriere(db, angebot.id, "jemand-anderes")
    finally:
        await _aufraeumen(factory)


async def test_neu_anlegen_erzeugt_eine_verknuepfte_gruppe(async_engine):
    from app.groups.angebote import lege_an

    factory = _f(async_engine)
    try:
        async with factory() as db:
            await _fach(db)
            await db.commit()
        async with factory() as db:
            await sync_groups(db=db, pseudonym=LK,
                              sso_groups=["unterricht.angebot9d.ch"],
                              primary_role="teacher", patterns=MUSTER)
        async with factory() as db:
            angebot = (await db.execute(
                select(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK)
            )).scalar_one()
            gid = await lege_an(db, angebot.id, LK)
            await db.commit()

        async with factory() as db:
            gruppe = await db.get(Group, gid)
            offen = (await db.execute(
                select(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK)
            )).scalars().all()
        assert gruppe.sso_group_id == "unterricht.angebot9d.ch"
        assert gruppe.erbt_mitglieder is False
        assert offen == []
    finally:
        async with factory() as db:
            await db.execute(delete(GroupMembership).where(GroupMembership.pseudonym == LK))
            await db.execute(delete(Group).where(Group.slug.like("sso-unterricht-angebot%")))
            await db.commit()
        await _aufraeumen(factory)


async def test_ignorieren_ist_ruecknehmbar(async_engine):
    """Ein Fehlklick darf nicht endgültig sein."""
    from app.groups.angebote import hebe_ignorieren_auf, ignoriere, lade_angebote

    factory = _f(async_engine)
    try:
        async with factory() as db:
            await _fach(db)
            await db.commit()
        async with factory() as db:
            await sync_groups(db=db, pseudonym=LK,
                              sso_groups=["unterricht.angebot9d.ch"],
                              primary_role="teacher", patterns=MUSTER)
        async with factory() as db:
            angebot = (await db.execute(
                select(SsoGroupOffer).where(SsoGroupOffer.pseudonym == LK)
            )).scalar_one()
            await ignoriere(db, angebot.id, LK)
            await db.commit()
        async with factory() as db:
            assert await lade_angebote(db, LK) == []
            assert len(await lade_angebote(db, LK, mit_ignorierten=True)) == 1
        async with factory() as db:
            await hebe_ignorieren_auf(db, angebot.id, LK)
            await db.commit()
        async with factory() as db:
            assert len(await lade_angebote(db, LK)) == 1
    finally:
        await _aufraeumen(factory)
