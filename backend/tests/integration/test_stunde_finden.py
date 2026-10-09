"""Die Stunde im Chat finden und wählen (0.15, Päckchen A Schritt 3).

`finde_stunde` sucht nur in Unterrichtsgruppen, in denen die Person Lehrkraft ist — das ist
die Zugriffsregel. `waehle_stunde` macht den Termin zur Bezugsstunde und legt einen Entwurf
nur mit `anlegen=true` an.

Alle Termine liegen im März 2031 und gehören Gruppen, die das Modul am Ende wieder entfernt:
Stunden von teacher1 in heutigen Wochen träfen sonst die Tagesauswertungen in
`test_planning_api.py` (vgl. `test_optimistisches_sperren.py`).
"""
from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.chat.tools import ToolContext
from app.db.models import LessonSlot
from app.planning.assistant_tools import _handle_finde_stunde, _handle_waehle_stunde
from app.planning.stunde_finden import Suche, finde_stunden
from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

CHEMIE_9D = 781    # teacher1 unterrichtet
CHEMIE_9E = 782    # teacher2 unterrichtet — die Kollegin
PHYSIK_9D = 783    # teacher1 ist dort Schüler:in
KLASSE_9D = 784    # teacher1 ist Lehrkraft, aber es ist eine Klasse
BIO_10A = 785      # teacher1 unterrichtet
GRUPPEN = (CHEMIE_9D, CHEMIE_9E, PHYSIK_9D, KLASSE_9D, BIO_10A)
FAECHER = (781, 782, 783)

MITTWOCH = date(2031, 3, 5)


@pytest.fixture(scope="module")
def welt(db_url, run_migrations):
    """Gruppen und Termine. Gibt {thema: slot_id} zurück."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        for sid, name in ((781, "Chemie Finden"), (782, "Physik Finden"), (783, "Biologie Finden")):
            cur.execute("INSERT INTO subjects (id, slug, name, sort_order) VALUES (%s, %s, %s, 0) "
                        "ON CONFLICT (id) DO NOTHING", (sid, name.lower().replace(" ", "-"), name))
        for gid, name, typ, fach in ((CHEMIE_9D, "Ch 9d", "teaching_group", 781),
                                     (CHEMIE_9E, "Ch 9e", "teaching_group", 781),
                                     (PHYSIK_9D, "Ph 9d", "teaching_group", 782),
                                     (KLASSE_9D, "9d", "school_class", None),
                                     (BIO_10A, "Bio 10a", "teaching_group", 783)):
            cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) VALUES (%s, %s, %s, %s, %s) "
                        "ON CONFLICT (id) DO NOTHING", (gid, name, f"finden-{gid}", typ, fach))
        for gid, pseudonym, rolle in ((CHEMIE_9D, TEACHER1_PSEUDO, "teacher"),
                                      (CHEMIE_9E, TEACHER2_PSEUDO, "teacher"),
                                      (PHYSIK_9D, TEACHER1_PSEUDO, "student"),
                                      (KLASSE_9D, TEACHER1_PSEUDO, "teacher"),
                                      (BIO_10A, TEACHER1_PSEUDO, "teacher")):
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                        "VALUES (%s, %s, %s, 'eigen') ON CONFLICT DO NOTHING", (gid, pseudonym, rolle))
        termine = {}
        for gid, tag, start, dauer, thema in ((CHEMIE_9D, 3, 3, 1, "Redoxreihe"),
                                              (CHEMIE_9D, 5, 1, 1, "Elektrolyse"),
                                              (CHEMIE_9D, 6, 3, 2, "Galvanik"),
                                              (CHEMIE_9D, 13, 3, 1, "Akkus"),
                                              (CHEMIE_9E, 6, 2, 1, "Fremdes Thema"),
                                              (PHYSIK_9D, 6, 5, 1, "Als Schüler"),
                                              (KLASSE_9D, 6, 6, 1, "Klassenstunde"),
                                              (BIO_10A, 7, 2, 1, "Zellen")):
            kennung = uuid4()
            cur.execute("INSERT INTO lesson_slots (id, group_id, date, halbjahr, periods, start_period, "
                        "kategorie, thema) VALUES (%s, %s, %s, 2, %s, %s, 'unterricht', %s)",
                        (str(kennung), gid, date(2031, 3, tag), dauer, start, thema))
            termine[thema] = str(kennung)
    conn.commit()
    yield SimpleNamespace(conn=conn, termine=termine)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE pseudonym IN (%s, %s) AND group_id = ANY(%s)",
                    (TEACHER1_PSEUDO, TEACHER2_PSEUDO, list(GRUPPEN)))
        cur.execute("DELETE FROM conversations WHERE title = 'finden-test'")
        cur.execute("DELETE FROM context_nodes WHERE read_scope_group_id = ANY(%s)", (list(GRUPPEN),))
        cur.execute("DELETE FROM groups WHERE id = ANY(%s)", (list(GRUPPEN),))
        cur.execute("DELETE FROM subjects WHERE id = ANY(%s)", (list(FAECHER),))
    conn.commit()
    conn.close()


def _sitzungen(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def _finde(async_engine, pseudonym=TEACHER1_PSEUDO, heute=MITTWOCH, **suche):
    async with _sitzungen(async_engine)() as db:
        return await finde_stunden(db, pseudonym, Suche(**suche), heute=heute)


def _themen(antwort):
    return [t["thema"] for t in antwort["treffer"]]


# ── finde_stunde ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_nur_eigene_unterrichtsgruppen(welt, async_engine):
    """⚠️ Der Wächter: nicht die Gruppe der Kollegin, nicht die eigene als Schüler:in, keine
    Klasse — auch nicht, wenn die Termine genau in den Zeitraum fallen."""
    antwort = await _finde(async_engine, wann="diese_woche")
    assert _themen(antwort) == ["Redoxreihe", "Elektrolyse", "Galvanik", "Zellen"]


@pytest.mark.asyncio
@pytest.mark.parametrize("gruppe", ["9d", "ch-9d", "CH 9D"])
async def test_gruppe_per_teiltreffer(welt, async_engine, gruppe):
    antwort = await _finde(async_engine, wann="naechste", gruppe=gruppe)
    assert _themen(antwort) == ["Elektrolyse"]


@pytest.mark.asyncio
async def test_naechste_je_gruppe_ein_termin(welt, async_engine):
    antwort = await _finde(async_engine, wann="naechste")
    assert _themen(antwort) == ["Elektrolyse", "Zellen"]


@pytest.mark.asyncio
async def test_am_donnerstag(welt, async_engine):
    antwort = await _finde(async_engine, wann="naechste", wochentag="do")
    assert _themen(antwort) == ["Galvanik"]
    treffer = antwort["treffer"][0]
    assert (treffer["datum"], treffer["wochentag"], treffer["stunde"]) == ("2031-03-06", "Do", "3.–4.")
    assert (treffer["gruppe"], treffer["fach"], treffer["slot_id"]) == (
        "Ch 9d", "Chemie Finden", welt.termine["Galvanik"])


@pytest.mark.asyncio
async def test_fach_und_datum(welt, async_engine):
    assert _themen(await _finde(async_engine, wann="naechste_woche", fach="chemie")) == ["Akkus"]
    assert _themen(await _finde(async_engine, wann="datum", datum="13.3.")) == ["Akkus"]
    assert _themen(await _finde(async_engine, wann="letzte_woche")) == []


@pytest.mark.asyncio
async def test_thema_auch_aus_dem_stundentitel(welt, async_engine, test_client, auth_headers):
    slot = welt.termine["Galvanik"]
    resp = await test_client.post(f"/planning/slots/{slot}/lesson", headers=auth_headers)
    assert resp.status_code == 201, resp.text
    with welt.conn.cursor() as cur:
        cur.execute("UPDATE context_nodes SET title = 'Kupfer abscheiden' WHERE id = %s",
                    (resp.json()["id"],))
    welt.conn.commit()

    antwort = await _finde(async_engine, wann="diese_woche", thema="kupfer")
    assert _themen(antwort) == ["Galvanik"]
    assert antwort["treffer"][0]["hat_entwurf"] is True


@pytest.mark.asyncio
async def test_kein_treffer_sagt_wonach_gesucht_wurde(welt, async_engine):
    antwort = await _finde(async_engine, wann="diese_woche", gruppe="10b")
    assert antwort["treffer"] == [] and antwort["gesamt"] == 0
    assert "Gruppe „10b“" in antwort["gesucht"] and "2031-03-03 bis 2031-03-09" in antwort["gesucht"]
    assert antwort["heute"] == "Mi 2031-03-05"


@pytest.mark.asyncio
async def test_unbrauchbare_angaben(welt, async_engine):
    assert "error" in await _finde(async_engine, wann="uebermorgen")
    assert "error" in await _finde(async_engine, wann="datum", datum="irgendwann")
    assert "error" in await _finde(async_engine, wann="naechste", wochentag="xx")


@pytest.mark.asyncio
async def test_das_werkzeug(welt, async_engine):
    """Durch den Handler — mit ganzem Datum, damit „heute" keine Rolle spielt."""
    async with _sitzungen(async_engine)() as db:
        ctx = ToolContext(db=db, user=SimpleNamespace(sub=TEACHER1_PSEUDO), group_id=None,
                          conversation_id=None)
        antwort = await _handle_finde_stunde({"wann": "datum", "datum": "2031-03-06"}, ctx)
    assert _themen(antwort) == ["Galvanik"]


# ── waehle_stunde ────────────────────────────────────────────────────────────


def _konversation(conn, pseudonym=TEACHER1_PSEUDO):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO conversations (pseudonym, model_used, title) "
                    "VALUES (%s, 'chat-standard', 'finden-test') RETURNING id", (pseudonym,))
        kennung = cur.fetchone()[0]
    conn.commit()
    return kennung


def _stand(conn, konversation):
    with conn.cursor() as cur:
        cur.execute("SELECT group_id, subject_id, stunde_node_id FROM conversations WHERE id = %s",
                    (konversation,))
        group_id, subject_id, stunde = cur.fetchone()
    return group_id, subject_id, str(stunde) if stunde else None


def _entwurf_am_slot(conn, slot):
    with conn.cursor() as cur:
        cur.execute("SELECT stunde_node_id FROM lesson_slots WHERE id = %s", (slot,))
        wert = cur.fetchone()[0]
    return str(wert) if wert else None


async def _waehle(async_engine, konversation, slot, anlegen=False, pseudonym=TEACHER1_PSEUDO):
    async with _sitzungen(async_engine)() as db:
        ctx = ToolContext(db=db, user=SimpleNamespace(sub=pseudonym), group_id=None,
                          conversation_id=UUID(str(konversation)))
        antwort = await _handle_waehle_stunde({"slot_id": slot, "anlegen": anlegen}, ctx)
    return antwort, ctx


@pytest.mark.asyncio
@pytest.mark.parametrize("thema", ["Fremdes Thema", "Als Schüler", "Klassenstunde", None])
async def test_fremder_termin(welt, async_engine, thema):
    konversation = _konversation(welt.conn)
    slot = welt.termine[thema] if thema else str(uuid4())
    antwort, ctx = await _waehle(async_engine, konversation, slot, anlegen=True)
    assert antwort == {"error": "Termin nicht gefunden"}
    assert _stand(welt.conn, konversation) == (None, None, None)
    if thema:
        assert _entwurf_am_slot(welt.conn, slot) is None, "Für einen fremden Termin angelegt"


@pytest.mark.asyncio
async def test_ohne_entwurf_nur_mit_zustimmung(welt, async_engine):
    konversation = _konversation(welt.conn)
    slot = welt.termine["Elektrolyse"]

    antwort, _ = await _waehle(async_engine, konversation, slot)
    assert antwort["hat_entwurf"] is False and "anlegen=true" in antwort["hinweis"]
    assert _entwurf_am_slot(welt.conn, slot) is None
    assert _stand(welt.conn, konversation) == (None, None, None)

    antwort, ctx = await _waehle(async_engine, konversation, slot, anlegen=True)
    assert antwort["bezugsstunde_gesetzt"] is True and antwort["neu_angelegt"] is True
    assert antwort["titel"] == "Elektrolyse"
    stunde = _entwurf_am_slot(welt.conn, slot)
    assert stunde == antwort["id"]
    # Die Konversation trägt Stunde **und** Gruppe — und der Kontext dieser Anfrage auch.
    assert _stand(welt.conn, konversation) == (CHEMIE_9D, 781, stunde)
    assert (str(ctx.stunde_node_id), ctx.group_id) == (stunde, CHEMIE_9D)


@pytest.mark.asyncio
async def test_vorhandener_entwurf_wird_nicht_verdoppelt(welt, async_engine, test_client, auth_headers):
    slot = welt.termine["Redoxreihe"]
    resp = await test_client.post(f"/planning/slots/{slot}/lesson", headers=auth_headers)
    vorhanden = resp.json()["id"]
    konversation = _konversation(welt.conn)

    antwort, _ = await _waehle(async_engine, konversation, slot, anlegen=True)
    assert antwort["id"] == vorhanden and antwort["neu_angelegt"] is False
    assert _entwurf_am_slot(welt.conn, slot) == vorhanden
    assert _stand(welt.conn, konversation)[2] == vorhanden


@pytest.mark.asyncio
async def test_fremde_konversation(welt, async_engine):
    konversation = _konversation(welt.conn, pseudonym=TEACHER2_PSEUDO)
    antwort, _ = await _waehle(async_engine, konversation, welt.termine["Zellen"], anlegen=True)
    assert "error" in antwort
    assert _entwurf_am_slot(welt.conn, welt.termine["Zellen"]) is None
