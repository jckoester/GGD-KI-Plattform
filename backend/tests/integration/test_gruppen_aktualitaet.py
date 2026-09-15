"""Aktuelle und frühere Unterrichtsgruppen (AP8 Schritt 1 des Fachseiten-Plans).

Die Regel selbst ist rein und in `test_groups_router.py` geprüft. Hier geht es um das,
was nur eine echte Datenbank zeigt: ob `gruppen_mit_beleg` die beiden Belege — Stunden im
laufenden Schuljahr und Planung mit passendem `schuljahr` — in **einer** Abfrage
zusammenbringt, und ob das Kennzeichen durch die Antwort trägt.
"""
import pytest
import pytest_asyncio
from datetime import timedelta
from sqlalchemy import delete, insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ContextNode, Group, GroupMembership, LessonSlot
from app.planning.calendar import load_school_year
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio

JAHR = load_school_year()


@pytest_asyncio.fixture
async def welt(async_engine):
    """Fünf Gruppen, in allen bin ich Lehrkraft — sie unterscheiden sich nur im Beleg."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    daten = {}
    async with factory() as s:
        res = await s.execute(text(
            "INSERT INTO subjects (name, slug) VALUES ('AP8-Fach', 'ap8-fach') RETURNING id"
        ))
        fach = res.scalar_one()
        daten["fach"] = fach

        # `created_at` bewusst vor dem Schuljahresbeginn: Sonst wären alle schon deshalb
        # aktuell, und die beiden Belege blieben ungeprüft.
        vorjahr = JAHR.beginn - timedelta(days=30)
        for kuerzel, sso in (
            ("mit_stunden", None),
            ("mit_planung", None),
            ("ohne_beleg", None),
            ("aus_dem_sso", "unterricht.ap8-ks"),
            ("frisch", None),
        ):
            res = await s.execute(text(
                "INSERT INTO groups (name, slug, type, subject_id, sso_group_id, created_at) "
                "VALUES (:n, :sl, 'teaching_group', :f, :sso, :ts) RETURNING id"
            ), {"n": f"AP8 {kuerzel}", "sl": f"ap8-{kuerzel}", "f": fach, "sso": sso,
                "ts": JAHR.beginn if kuerzel == "frisch" else vorjahr})
            daten[kuerzel] = res.scalar_one()
            await s.execute(insert(GroupMembership).values(
                group_id=daten[kuerzel], pseudonym=TEACHER1_PSEUDO, role_in_group="teacher"
            ))

        s.add(LessonSlot(
            group_id=daten["mit_stunden"], date=JAHR.beginn + timedelta(days=1),
            start_period=1, periods=1, halbjahr=1, kategorie="unterricht",
        ))
        # Eine Stunde im VORJAHR — sie darf nicht zählen.
        s.add(LessonSlot(
            group_id=daten["ohne_beleg"], date=JAHR.beginn - timedelta(days=60),
            start_period=1, periods=1, halbjahr=2, kategorie="unterricht",
        ))
        s.add(ContextNode(
            category="artifact", content_type="jahresplan", title="AP8 Plan",
            owner_pseudonym=TEACHER1_PSEUDO, read_scope="group", write_scope="group",
            read_scope_group_id=daten["mit_planung"],
            write_scope_group_id=daten["mit_planung"],
            subject_id=fach, schuljahr=JAHR.schuljahr, status="active",
        ))
        await s.commit()

    yield daten

    async with factory() as s:
        gids = [daten[k] for k in
                ("mit_stunden", "mit_planung", "ohne_beleg", "aus_dem_sso", "frisch")]
        await s.execute(delete(LessonSlot).where(LessonSlot.group_id.in_(gids)))
        await s.execute(delete(ContextNode).where(
            ContextNode.write_scope_group_id.in_(gids)))
        await s.execute(delete(GroupMembership).where(GroupMembership.group_id.in_(gids)))
        await s.execute(delete(Group).where(Group.id.in_(gids)))
        await s.execute(text("DELETE FROM subjects WHERE slug = 'ap8-fach'"))
        await s.commit()


async def _meine(client, headers) -> dict:
    resp = await client.get("/groups/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return {g["name"]: g["aktuell"] for g in resp.json()["items"]}


async def test_beide_belege_zaehlen(test_client, auth_headers, welt):
    """Stunden und Planung entstehen zu verschiedenen Zeitpunkten — der Jahresplan beim
    ersten Öffnen der Planung, die Stunden erst mit dem Stundenraster. Wer nur einen
    prüfte, übersähe die halbe Wirklichkeit."""
    aktuell = await _meine(test_client, auth_headers)
    assert aktuell["AP8 mit_stunden"] is True
    assert aktuell["AP8 mit_planung"] is True


async def test_stunden_aus_dem_vorjahr_zaehlen_nicht(test_client, auth_headers, welt):
    aktuell = await _meine(test_client, auth_headers)
    assert aktuell["AP8 ohne_beleg"] is False


async def test_gruppe_aus_dem_schulkonto_bleibt_aktuell(test_client, auth_headers, welt):
    """Ohne jeden Beleg und vor dem Schuljahr angelegt — für sie entscheidet der Spiegel."""
    aktuell = await _meine(test_client, auth_headers)
    assert aktuell["AP8 aus_dem_sso"] is True


async def test_frisch_angelegte_gruppe_bleibt_aktuell(test_client, auth_headers, welt):
    aktuell = await _meine(test_client, auth_headers)
    assert aktuell["AP8 frisch"] is True
