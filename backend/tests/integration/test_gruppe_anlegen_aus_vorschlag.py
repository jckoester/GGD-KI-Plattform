"""AP3: `lege_gruppe_aus_vorschlag_an` — woher die Mitglieder kommen werden.

Die Anlage entscheidet, ob eine Gruppe ihre Schüler:innen **erbt** oder auf den
Beitrittscode angewiesen ist. Das ist der Unterschied zwischen „läuft von selbst" und
„die Lehrkraft muss etwas tun" — und er wird hier festgehalten.
"""
from dataclasses import dataclass

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.calendar.groups import lege_gruppe_aus_vorschlag_an
from app.db.models import Group, GroupMembership, GroupSourceClass, Subject

LEHRKRAFT = "anlage-lehrkraft"


@dataclass
class _Key:
    label: str


@dataclass
class _Vorschlag:
    """Nur die Felder, die die Anlage liest — kein echtes `GroupSuggestion` nötig."""

    subject_id: int
    subject_slug: str
    class_names: tuple[str, ...]
    vorschlag_name: str
    key: _Key = None


async def _fach(db) -> int:
    fach = (await db.execute(
        select(Subject).where(Subject.slug == "anlage-fach")
    )).scalar_one_or_none()
    if fach is None:
        fach = Subject(slug="anlage-fach", name="Anlagekunde")
        db.add(fach)
        await db.flush()
    return fach.id


async def _klassen(db, namen):
    ids = []
    for n in namen:
        k = Group(name=n, slug=f"klasse-{n.lower()}-anlage", type="school_class")
        db.add(k)
        await db.flush()
        ids.append(k.id)
    return ids


async def _aufraeumen(factory):
    async with factory() as db:
        await db.execute(delete(GroupMembership).where(
            GroupMembership.pseudonym == LEHRKRAFT))
        await db.execute(delete(Group).where(Group.slug.like("teaching-anlage-fach-%")))
        await db.execute(delete(Group).where(Group.slug.like("klasse-%-anlage")))
        await db.execute(delete(Subject).where(Subject.slug == "anlage-fach"))
        await db.commit()


async def test_mehrere_klassen_werden_verknuepft_aber_nicht_vererbt(async_engine):
    """NwT 10a/10b/10c: drei Quellklassen als **Herkunft**, aber keine Vererbung.

    Die Herkunft trägt die Stundenplan-Zuordnung und die Jahrgangsableitung; die
    Mitgliedschaft folgt daraus **nicht** — eine Gruppe über mehreren Klassen ist eine
    Auswahl daraus (Befund Jan, 23.09.2026).
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            fach_id = await _fach(db)
            await _klassen(db, ["10A", "10B", "10C"])
            ergebnis = await lege_gruppe_aus_vorschlag_an(
                db,
                _Vorschlag(fach_id, "anlage-fach", ("10A", "10B", "10C"), "NwT 10"),
                LEHRKRAFT,
            )
            await db.commit()

        async with factory() as db:
            quellen = (await db.execute(
                select(GroupSourceClass.class_group_id).where(
                    GroupSourceClass.group_id == ergebnis.group_id)
            )).scalars().all()
            herkunft = (await db.execute(
                select(GroupMembership.herkunft).where(
                    GroupMembership.group_id == ergebnis.group_id,
                    GroupMembership.pseudonym == LEHRKRAFT)
            )).scalar_one()

        assert len(quellen) == 3, "alle drei Klassenverbände müssen als Herkunft stehen"
        assert sorted(ergebnis.quellklassen) == ["10A", "10B", "10C"]
        assert ergebnis.ohne_treffer == ()
        assert herkunft == "eigen"
        assert ergebnis.erbt is False, (
            "Eine mehrklassige Gruppe darf nicht vererben — sie ist eine Auswahl aus "
            "diesen Klassen, nicht ihre Summe."
        )
    finally:
        await _aufraeumen(factory)


async def test_kursstufe_bekommt_keine_quellklasse(async_engine):
    """⚠️ **Der Kern des Kursstufenfalls.**

    Dort heißt die „Klasse" `11` und bezeichnet einen ganzen Jahrgang. Würde die Gruppe
    daraus erben, säße der komplette Jahrgang in einem Kurs von zwanzig Leuten. Solche
    Gruppen leben vom Beitrittscode — deshalb **keine** Quellklasse, auch wenn zufällig
    eine `school_class` namens `11` existiert.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            fach_id = await _fach(db)
            await _klassen(db, ["11"])
            ergebnis = await lege_gruppe_aus_vorschlag_an(
                db,
                _Vorschlag(fach_id, "anlage-fach", ("11",), "Chemie 2 (11)"),
                LEHRKRAFT,
            )
            await db.commit()

        async with factory() as db:
            quellen = (await db.execute(
                select(GroupSourceClass.class_group_id).where(
                    GroupSourceClass.group_id == ergebnis.group_id)
            )).scalars().all()

        assert ergebnis.kursstufe is True
        assert quellen == [], (
            "Ein Kursstufenkurs darf nicht aus dem Jahrgang erben — sonst ist der "
            "ganze Jahrgang drin."
        )
        assert ergebnis.ohne_treffer == (), "in der Kursstufe wird gar nicht erst gesucht"
    finally:
        await _aufraeumen(factory)


async def test_fehlende_klasse_verhindert_die_anlage_nicht(async_engine):
    """Eine Klasse, die es auf der Plattform nicht gibt, wird **gemeldet**, nicht bestraft.

    Sonst scheiterte das Anlegen an einer fehlenden Klassengruppe — und die Lehrkraft
    stünde ohne Gruppe da, obwohl der Stundenplan sie kennt.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            fach_id = await _fach(db)
            await _klassen(db, ["9A"])          # 9B fehlt bewusst
            ergebnis = await lege_gruppe_aus_vorschlag_an(
                db,
                _Vorschlag(fach_id, "anlage-fach", ("9A", "9B"), "Anlage 9AB"),
                LEHRKRAFT,
            )
            await db.commit()

        assert ergebnis.group_id is not None
        assert ergebnis.quellklassen == ("9A",)
        assert ergebnis.ohne_treffer == ("9B",), "die Lücke gehört benannt"
        # Genau eine gefundene Klasse — also erbt die Gruppe von dort. Dass im
        # Stundenplan eine zweite stand, ändert daran nichts: Über die fehlende Klasse
        # kann die Plattform nichts wissen.
        assert ergebnis.erbt is True
    finally:
        await _aufraeumen(factory)


async def test_namensgleiche_gruppen_bekommen_eigene_slugs(async_engine):
    """Zwei Gruppen desselben Namens dürfen sich nicht am Slug stoßen."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            fach_id = await _fach(db)
            v = _Vorschlag(fach_id, "anlage-fach", (), "Kurs ohne Klasse")
            erste = await lege_gruppe_aus_vorschlag_an(db, v, LEHRKRAFT)
            zweite = await lege_gruppe_aus_vorschlag_an(db, v, LEHRKRAFT)
            await db.commit()

        async with factory() as db:
            slugs = (await db.execute(
                select(Group.slug).where(Group.id.in_([erste.group_id, zweite.group_id]))
            )).scalars().all()
        assert len(set(slugs)) == 2, f"Slugs müssen eindeutig sein: {slugs}"
    finally:
        await _aufraeumen(factory)


async def test_lehrkraft_kann_einzelklasse_als_teilgruppe_anlegen(async_engine):
    """⚠️ **Der Religion-und-Ethik-Fall** (Jan, 23.09.2026).

    Der Stundenplan nennt **eine** Klasse — die Vorbelegung wäre also „erbt". Die Gruppe
    ist trotzdem nur die Hälfte der Klasse. Sagt die Lehrkraft „Teilgruppe", darf nichts
    geerbt werden; die Klasse bleibt als **Herkunft** stehen, weil sie für Zuordnung und
    Jahrgang gebraucht wird.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            fach_id = await _fach(db)
            await _klassen(db, ["7A"])
            ergebnis = await lege_gruppe_aus_vorschlag_an(
                db,
                _Vorschlag(fach_id, "anlage-fach", ("7A",), "Ethik 7a"),
                LEHRKRAFT,
                erbt=False,
            )
            await db.commit()

        async with factory() as db:
            gruppe = await db.get(Group, ergebnis.group_id)
            quellen = (await db.execute(
                select(GroupSourceClass.class_group_id).where(
                    GroupSourceClass.group_id == ergebnis.group_id)
            )).scalars().all()

        assert ergebnis.erbt is False
        assert gruppe.erbt_mitglieder is False, (
            "Die Entscheidung der Lehrkraft muss an der Gruppe stehen — sonst erbt sie "
            "beim nächsten Login doch die ganze Klasse."
        )
        assert len(quellen) == 1, "die Herkunft bleibt, nur die Vererbung nicht"
    finally:
        await _aufraeumen(factory)


async def test_lehrkraft_kann_mehrklassige_gruppe_erben_lassen(async_engine):
    """Die Gegenrichtung: zwei kleine Klassen, vollständig gemeinsam unterrichtet.

    Die Vorbelegung sagt „Teilgruppe", weil mehrklassig fast immer eine Auswahl ist.
    Wer es besser weiß, kann es sagen — und dann erbt die Gruppe aus beiden.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            fach_id = await _fach(db)
            await _klassen(db, ["5A", "5B"])
            ergebnis = await lege_gruppe_aus_vorschlag_an(
                db,
                _Vorschlag(fach_id, "anlage-fach", ("5A", "5B"), "Sport 5ab"),
                LEHRKRAFT,
                erbt=True,
            )
            await db.commit()

        async with factory() as db:
            gruppe = await db.get(Group, ergebnis.group_id)
        assert ergebnis.erbt is True
        assert gruppe.erbt_mitglieder is True
    finally:
        await _aufraeumen(factory)


async def test_ohne_gefundene_klasse_bleibt_es_beim_code(async_engine):
    """„Erben" ohne Klasse ist keine Entscheidung, sondern ein Missverständnis.

    Sagt jemand `erbt=True` für einen Kursstufenkurs, gibt es trotzdem nichts zu erben —
    die Gruppe bliebe leer und niemand wüsste warum. Deshalb wird die Angabe hier
    stillschweigend zu `false`, nicht zu einem Fehler: Die Lehrkraft hat nichts falsch
    gemacht, die Frage war nur nicht anwendbar.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            fach_id = await _fach(db)
            await _klassen(db, ["11"])
            ergebnis = await lege_gruppe_aus_vorschlag_an(
                db,
                _Vorschlag(fach_id, "anlage-fach", ("11",), "Chemie 2 (11)"),
                LEHRKRAFT,
                erbt=True,
            )
            await db.commit()

        async with factory() as db:
            gruppe = await db.get(Group, ergebnis.group_id)
        assert ergebnis.erbt is False
        assert gruppe.erbt_mitglieder is False
    finally:
        await _aufraeumen(factory)


# ── AP5: Verschwindet eine Gruppe aus dem Stundenplan ────────────────────────


async def test_abgleich_ohne_die_lerngruppe_aendert_nichts(async_engine):
    """⚠️ **Die Zusage von AP5: Ein Hinweis ist keine Handlung.**

    Steht eine Gruppe nicht mehr im Stundenplan, bleibt **alles** wie es war — Gruppe,
    Mitgliedschaften, Quellklassen, Vererbungsentscheidung. An einer Unterrichtsgruppe
    hängen Jahresplan, Stundenentwürfe und Konversationen; sie automatisch zu
    archivieren hieße, eine Vier-Wochen-Momentaufnahme über ein Schuljahr entscheiden zu
    lassen.

    Geprüft wird der **Abgleich selbst** (`match_groups` mit leerem Stundenplan), nicht
    der Endpunkt: Hier soll sich zeigen, dass der schreibende Teil gar nicht erst
    angefasst wird.
    """
    from app.calendar.groups import match_groups

    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            fach_id = await _fach(db)
            await _klassen(db, ["6A"])
            ergebnis = await lege_gruppe_aus_vorschlag_an(
                db,
                _Vorschlag(fach_id, "anlage-fach", ("6A",), "Anlage 6a"),
                LEHRKRAFT,
            )
            db.add(GroupMembership(group_id=ergebnis.group_id, pseudonym="schueler-6a",
                                   role_in_group="student", herkunft="geerbt"))
            await db.commit()

        async with factory() as db:
            vorher = await db.get(Group, ergebnis.group_id)
            zustand_vorher = (vorher.name, vorher.slug, vorher.erbt_mitglieder,
                              vorher.subject_id)
            mitglieder_vorher = sorted(
                (m.pseudonym, m.herkunft) for m in (await db.execute(
                    select(GroupMembership).where(
                        GroupMembership.group_id == ergebnis.group_id)
                )).scalars().all()
            )

        # Der Stundenplan gibt nichts mehr her.
        async with factory() as db:
            abgleich = await match_groups(db, [], pseudonym=LEHRKRAFT)
            await db.commit()

        assert ergebnis.group_id in {k.id for k in abgleich.nicht_im_stundenplan}, (
            "Die Gruppe wird nicht als vermisst gemeldet."
        )

        async with factory() as db:
            nachher = await db.get(Group, ergebnis.group_id)
            assert nachher is not None, "Die Gruppe wurde gelöscht"
            assert (nachher.name, nachher.slug, nachher.erbt_mitglieder,
                    nachher.subject_id) == zustand_vorher, "Die Gruppe wurde verändert"
            mitglieder_nachher = sorted(
                (m.pseudonym, m.herkunft) for m in (await db.execute(
                    select(GroupMembership).where(
                        GroupMembership.group_id == ergebnis.group_id)
                )).scalars().all()
            )
            quellen = (await db.execute(
                select(GroupSourceClass.class_group_id).where(
                    GroupSourceClass.group_id == ergebnis.group_id)
            )).scalars().all()
        assert mitglieder_nachher == mitglieder_vorher, "Mitgliedschaften wurden angetastet"
        assert len(quellen) == 1, "Die Quellklasse wurde entfernt"
    finally:
        async with factory() as db:
            await db.execute(delete(GroupMembership).where(
                GroupMembership.pseudonym == "schueler-6a"))
            await db.commit()
        await _aufraeumen(factory)
