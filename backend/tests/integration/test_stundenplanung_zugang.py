"""Stundenplanung ohne Gruppenbezug: Den Zugang prüft das Werkzeug (0.15, Schritt 1).

`lesson_planning` greift an der Lehrkraft-Rolle, nicht an der Gruppe der Konversation
(`tools_for`) — welche Stunde gemeint ist, sagt allein das Modell. Diese Tests halten
fest, dass eine Kennung allein nichts öffnet: nicht ohne Gruppenbezug, nicht aus einer
Konversation in der fremden Gruppe, nicht als Schüler:in der Gruppe.
"""
from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg2
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.chat.tools import ToolContext
from app.db.models import LessonSlot, SlotPlanSnapshot
from app.planning.assistant_tools import (
    _handle_get_lesson_detail,
    _handle_get_unit_detail,
    _handle_update_lesson_phases,
)
from tests.integration.conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO, TEACHER2_PSEUDO

EIGENE = 746   # teacher1 unterrichtet, student1 ist Schüler:in
FREMDE = 747   # nur teacher2
ARCHIV = 748   # teacher1 legt an, verliert dann die Mitgliedschaft
GRUPPEN = (EIGENE, FREMDE, ARCHIV)

NICHT_GEFUNDEN = {"error": "Stunde nicht gefunden"}


@pytest.fixture(scope="module")
def gruppen(db_url, run_migrations):
    """Fächer, Gruppen, Mitgliedschaften — und danach wieder weg.

    Das Wegräumen ist nötig: Gruppen von teacher1 mit Slots träfen sonst die
    Tagesauswertungen in `test_planning_api.py` (vgl. `test_optimistisches_sperren.py`).
    """
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        for gid in GRUPPEN:
            cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                        "VALUES (%s, %s, %s, 0) ON CONFLICT (id) DO NOTHING",
                        (gid, f"stundenzugang-{gid}", f"Stundenzugang {gid}"))
            cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                        "VALUES (%s, %s, %s, 'teaching_group', %s) ON CONFLICT (id) DO NOTHING",
                        (gid, f"9z Zugang {gid}", f"zugang-{gid}", gid))
        for gid, pseudonym, rolle in ((EIGENE, TEACHER1_PSEUDO, "teacher"),
                                      (EIGENE, STUDENT_PSEUDO, "student"),
                                      (FREMDE, TEACHER2_PSEUDO, "teacher"),
                                      (ARCHIV, TEACHER1_PSEUDO, "teacher")):
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                        "VALUES (%s, %s, %s, 'eigen') ON CONFLICT DO NOTHING", (gid, pseudonym, rolle))
    conn.commit()
    yield conn
    with conn.cursor() as cur:
        # Erst die Planungsknoten — beim Löschen der Gruppe würde ihr Scope NULL.
        cur.execute("DELETE FROM context_nodes WHERE read_scope_group_id = ANY(%s)", (list(GRUPPEN),))
        # Slots, Mitgliedschaften und Snapshots gehen per Kaskade mit.
        cur.execute("DELETE FROM groups WHERE id = ANY(%s)", (list(GRUPPEN),))
        cur.execute("DELETE FROM subjects WHERE id = ANY(%s)", (list(GRUPPEN),))
    conn.commit()
    conn.close()


def _sitzungen(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


def _ctx(db, sub, group_id=None):
    return ToolContext(db=db, user=SimpleNamespace(sub=sub), group_id=group_id, conversation_id=None)


async def _einheit_und_stunde(client, h, gruppe, titel="Zahnräder"):
    ue = (await client.post(f"/planning/groups/{gruppe}/units", headers=h,
                            json={"titel": titel, "farbe": 0})).json()["id"]
    stunde = (await client.post(f"/planning/units/{ue}/lessons", headers=h,
                                json={"titel": titel})).json()["id"]
    resp = await client.patch(f"/planning/lessons/{stunde}", headers=h, json={"phasen": [
        {"name": "Einstieg", "dauer_min": 10}, {"name": "Erarbeitung", "dauer_min": 25},
    ]})
    assert resp.status_code == 200, resp.text
    return ue, stunde


async def _rufe(async_engine, handler, args, sub, group_id=None):
    async with _sitzungen(async_engine)() as db:
        return await handler(args, _ctx(db, sub, group_id))


async def _phasennamen(client, h, stunde):
    return [p["name"] for p in (await client.get(f"/planning/lessons/{stunde}", headers=h)).json()["phasen"]]


async def _snapshots(async_engine, gruppe):
    async with _sitzungen(async_engine)() as db:
        return (await db.execute(
            sa.select(sa.func.count()).select_from(SlotPlanSnapshot).where(
                SlotPlanSnapshot.group_id == gruppe, SlotPlanSnapshot.reason == "assistant")
        )).scalar_one()


# ── Die eigene Stunde: ohne Gruppenbezug lesen und schreiben ─────────────────


@pytest.mark.asyncio
async def test_eigene_stunde_ohne_gruppenbezug(test_client, auth_headers, gruppen, async_engine):
    _, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE)

    gelesen = await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": stunde}, TEACHER1_PSEUDO)
    assert [p["name"] for p in gelesen["phasen"]] == ["Einstieg", "Erarbeitung"]

    vorher = await _snapshots(async_engine, EIGENE)
    aus = await _rufe(async_engine, _handle_update_lesson_phases, {"node_id": stunde, "phasen": [
        {"id": gelesen["phasen"][0]["id"], "name": "Einstieg", "dauer_min": 5},
        {"name": "Sicherung", "dauer_min": 10},
    ]}, TEACHER1_PSEUDO)
    assert aus.get("ok") is True, aus
    assert await _phasennamen(test_client, auth_headers, stunde) == ["Einstieg", "Sicherung"]
    # Rückgängig gehört der Gruppe der Stunde — die Konversation hat hier keine.
    assert await _snapshots(async_engine, EIGENE) == vorher + 1


# ── Wächter: eine fremde Kennung öffnet nichts ───────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("gruppe_der_konversation", [None, EIGENE, FREMDE])
async def test_fremde_stunde_weder_lesen_noch_schreiben(
    test_client, auth_headers, auth_headers_teacher2, gruppen, async_engine, gruppe_der_konversation,
):
    """Auch nicht aus einer Konversation, die in der fremden Gruppe steht."""
    _, fremd = await _einheit_und_stunde(test_client, auth_headers_teacher2, FREMDE)

    assert await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": fremd},
                       TEACHER1_PSEUDO, gruppe_der_konversation) == NICHT_GEFUNDEN
    assert await _rufe(async_engine, _handle_update_lesson_phases, {
        "node_id": fremd, "phasen": [{"name": "Übernommen", "dauer_min": 45}],
    }, TEACHER1_PSEUDO, gruppe_der_konversation) == NICHT_GEFUNDEN
    assert await _phasennamen(test_client, auth_headers_teacher2, fremd) == ["Einstieg", "Erarbeitung"]


@pytest.mark.asyncio
async def test_schuelerin_der_gruppe_kommt_nicht_an_die_stunde(test_client, auth_headers, gruppen, async_engine):
    """Mitglied der Gruppe heißt nicht Lehrkraft der Gruppe."""
    _, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE)

    assert await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": stunde},
                       STUDENT_PSEUDO, EIGENE) == NICHT_GEFUNDEN
    assert await _rufe(async_engine, _handle_update_lesson_phases, {
        "node_id": stunde, "phasen": [{"name": "Weg", "dauer_min": 45}],
    }, STUDENT_PSEUDO, EIGENE) == NICHT_GEFUNDEN
    assert await _phasennamen(test_client, auth_headers, stunde) == ["Einstieg", "Erarbeitung"]


@pytest.mark.asyncio
async def test_fremd_und_unbekannt_sind_nicht_zu_unterscheiden(
    test_client, auth_headers_teacher2, gruppen, async_engine,
):
    """Sonst verriete das Werkzeug, welche Kennungen es gibt."""
    _, fremd = await _einheit_und_stunde(test_client, auth_headers_teacher2, FREMDE)
    fremd_gelesen = await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": fremd}, TEACHER1_PSEUDO)
    unbekannt = await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": str(uuid4())}, TEACHER1_PSEUDO)
    assert fremd_gelesen == unbekannt == NICHT_GEFUNDEN


@pytest.mark.asyncio
async def test_ohne_mitgliedschaft_nur_lesen(test_client, auth_headers, gruppen, async_engine):
    """Der Archiv-Fall aus `zugang_zur_stunde`: Die Eigentümerin liest, ändert aber nicht."""
    _, stunde = await _einheit_und_stunde(test_client, auth_headers, ARCHIV)
    with gruppen.cursor() as cur:
        cur.execute("DELETE FROM group_memberships WHERE group_id = %s AND pseudonym = %s",
                    (ARCHIV, TEACHER1_PSEUDO))
    gruppen.commit()

    gelesen = await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": stunde}, TEACHER1_PSEUDO)
    assert gelesen.get("titel") == "Zahnräder", gelesen
    aus = await _rufe(async_engine, _handle_update_lesson_phases, {
        "node_id": stunde, "phasen": [{"name": "Neu", "dauer_min": 45}],
    }, TEACHER1_PSEUDO)
    assert aus == {"error": "Stunde nur lesbar: keine Lehrkraft der Gruppe"}

    async with _sitzungen(async_engine)() as db:
        nochmal = await _handle_get_lesson_detail({"node_id": stunde}, _ctx(db, TEACHER1_PSEUDO))
    assert [p["name"] for p in nochmal["phasen"]] == ["Einstieg", "Erarbeitung"]


# ── Die Einheit: dieselbe Regel ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_einheit_ohne_gruppenbezug_mit_den_slots_ihrer_gruppe(
    test_client, auth_headers, gruppen, async_engine,
):
    ue, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE, titel="Hebel")
    async with _sitzungen(async_engine)() as db:
        db.add(LessonSlot(id=uuid4(), group_id=EIGENE, date=date(2031, 3, 3), halbjahr=2,
                          periods=1, start_period=3, kategorie="unterricht", ue_node_id=UUID(ue)))
        await db.commit()

    aus = await _rufe(async_engine, _handle_get_unit_detail, {"unit_node_id": ue}, TEACHER1_PSEUDO)
    assert aus["titel"] == "Hebel", aus
    assert [s["date"] for s in aus["slots"]] == ["2031-03-03"]
    assert [s["id"] for s in aus["stunden"]] == [stunde]


@pytest.mark.asyncio
@pytest.mark.parametrize("gruppe_der_konversation", [None, EIGENE, FREMDE])
async def test_fremde_einheit_bleibt_zu(
    test_client, auth_headers_teacher2, gruppen, async_engine, gruppe_der_konversation,
):
    ue, _ = await _einheit_und_stunde(test_client, auth_headers_teacher2, FREMDE, titel="Geheim")
    aus = await _rufe(async_engine, _handle_get_unit_detail, {"unit_node_id": ue},
                      TEACHER1_PSEUDO, gruppe_der_konversation)
    assert aus == {"error": "UE nicht gefunden"}


# ── Das Vokabular kommt mit dem Entwurf (Messung 1 zu Schritt 6) ─────────────


@pytest.mark.asyncio
async def test_entwurf_bringt_das_lesbare_vokabular_mit(test_client, auth_headers, gruppen, async_engine):
    """Schulweit und eigen ja, samt Aliasen; fremd-privat und fremdes Fach nein."""
    from app.context.taxonomy import CONTENT_TYPE_TO_CATEGORY
    from app.db.models import ContextNode, NodeAlias

    _, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE, titel="Vokabular")
    async with _sitzungen(async_engine)() as db:
        fach_der_stunde = (await db.get(ContextNode, UUID(stunde))).subject_id

        def knoten(titel, art="methode", **kw):
            n = ContextNode(category=CONTENT_TYPE_TO_CATEGORY[art], content_type=art,
                            title=f"Zugang-Vokabular {titel}", status="active", metadata_={},
                            read_scope=kw.pop("read_scope", "school"),
                            write_scope=kw.pop("write_scope", "school"), **kw)
            db.add(n)
            return n

        schulweit = knoten("Unterrichtsgespräch")
        sozialform = knoten("Einzelarbeit", art="sozialform")
        eigen = knoten("Meine Methode", read_scope="private", write_scope="private",
                       owner_pseudonym=TEACHER1_PSEUDO)
        knoten("Fremde Methode", read_scope="private", write_scope="private",
               owner_pseudonym=TEACHER2_PSEUDO)
        # Fachgebunden, schulweit lesbar — es geht um den Fachfilter, nicht um den Scope.
        knoten("Andere Fachschaft", subject_id=FREMDE)            # Fach 747 ≠ Fach der Stunde
        knoten("Eigene Fachschaft", subject_id=fach_der_stunde)
        await db.flush()
        db.add(NodeAlias(node_id=schulweit.id, alias="LSG"))
        db.add(NodeAlias(node_id=sozialform.id, alias="EA"))
        await db.commit()

    try:
        detail = await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": stunde}, TEACHER1_PSEUDO)
        methoden = {m["titel"].removeprefix("Zugang-Vokabular "): m for m in detail["vokabular"]["methoden"]
                    if m["titel"].startswith("Zugang-Vokabular ")}
        sozialformen = {s["titel"].removeprefix("Zugang-Vokabular "): s for s in detail["vokabular"]["sozialformen"]
                        if s["titel"].startswith("Zugang-Vokabular ")}
        assert set(methoden) == {"Unterrichtsgespräch", "Meine Methode", "Eigene Fachschaft"}
        assert methoden["Unterrichtsgespräch"]["aliase"] == ["LSG"]
        assert methoden["Unterrichtsgespräch"]["node_id"] == str(schulweit.id)
        assert sozialformen["Einzelarbeit"]["aliase"] == ["EA"]
        assert "aliase" not in methoden["Meine Methode"]
        assert str(eigen.id) in {m["node_id"] for m in methoden.values()}
    finally:
        with gruppen.cursor() as cur:
            cur.execute("DELETE FROM context_nodes WHERE title LIKE 'Zugang-Vokabular %%'")
        gruppen.commit()


# ── Der Zusammenhang kommt mit dem Entwurf (0.15, A1) ────────────────────────
#
# Ohne ihn suchte das Modell blind (Untersuchung „Kompetenz vorschlagen"): Der Entwurf
# nannte weder Fach noch Jahrgang noch Einheit, das Modell riet die Stufe und mischte
# Kurs- und Mittelstufe.

PRAEFIX = "Zugang-Curriculum "


async def _curriculum_mit_kapitel(db, *, read_scope="school", owner=None):
    """Curriculum (Kl. 9, Fach der Gruppe EIGENE) → Kapitel → zwei Lernsequenzen mit
    IK-Kompetenzen. Die zuletzt angelegte und alphabetisch letzte Sequenz kommt laut
    `reihenfolge` zuerst — sonst prüfte der Test die Sortierung nicht."""
    from app.db.models import ContextEdge, ContextNode

    def knoten(art, titel, **kw):
        n = ContextNode(category="knowledge", content_type=art, title=PRAEFIX + titel,
                        status="active", read_scope=read_scope, write_scope=read_scope,
                        owner_pseudonym=owner, **kw)
        db.add(n)
        return n

    cur = knoten("curriculum", "M Kl. 9", subject_id=EIGENE, min_grade=9, max_grade=9,
                 metadata_={"jahrgangsstufe": "9", "bp_version": "2016.V2"})
    kap = knoten("kapitel", "Potenzen", subject_id=EIGENE, metadata_={"reihenfolge": 1, "std": 20})
    spaeter = knoten("lernsequenz", "Potenzfunktionen", subject_id=EIGENE,
                     metadata_={"reihenfolge": 2, "std": 6})
    frueher = knoten("lernsequenz", "Zahlen in Normdarstellung", subject_id=EIGENE,
                     metadata_={"reihenfolge": 1, "std": 4})
    ik_a = ContextNode(category="knowledge", content_type="ik_kompetenz", status="active",
                       read_scope="global", write_scope="global",
                       title=PRAEFIX + "3.3.1(1) Zahlen in Normdarstellung angeben",
                       metadata_={"kompetenz_nr": "3.3.1(1)"})
    ik_b = ContextNode(category="knowledge", content_type="ik_kompetenz", status="active",
                       read_scope="global", write_scope="global",
                       title=PRAEFIX + "3.3.4(1) Graphen der Potenzfunktionen beschreiben",
                       metadata_={"kompetenz_nr": "3.3.4(1)"})
    db.add_all([ik_a, ik_b])
    await db.flush()
    db.add_all([
        ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of"),
        ContextEdge(from_node_id=frueher.id, to_node_id=kap.id, relation="part_of"),
        ContextEdge(from_node_id=spaeter.id, to_node_id=kap.id, relation="part_of"),
        ContextEdge(from_node_id=frueher.id, to_node_id=ik_a.id, relation="references",
                    metadata_={"partiell": "true"}),
        ContextEdge(from_node_id=spaeter.id, to_node_id=ik_b.id, relation="references",
                    metadata_={"partiell": "false"}),
    ])
    await db.flush()
    return kap, ik_a, ik_b


async def _verknuepfe(async_engine, ue, kapitel_id):
    from app.db.models import ContextEdge
    async with _sitzungen(async_engine)() as db:
        db.add(ContextEdge(from_node_id=UUID(ue), to_node_id=kapitel_id, relation="references"))
        await db.commit()


def _aufraeumen(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE title LIKE %s", (PRAEFIX + "%",))
    conn.commit()


@pytest.mark.asyncio
async def test_entwurf_bringt_einheit_kapitel_und_kompetenzen_mit(
    test_client, auth_headers, gruppen, async_engine,
):
    ue, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE, titel="Potenzen")
    try:
        async with _sitzungen(async_engine)() as db:
            kap, ik_a, ik_b = await _curriculum_mit_kapitel(db)
            await db.commit()
        await _verknuepfe(async_engine, ue, kap.id)

        z = (await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": stunde},
                         TEACHER1_PSEUDO))["zusammenhang"]
        assert z["fach"] == f"Stundenzugang {EIGENE}"
        assert z["gruppe"] == f"9z Zugang {EIGENE}"
        assert z["jahrgang"] == 9
        assert z["einheit"] == {"id": ue, "titel": "Potenzen"}
        k = z["kapitel"]
        assert (k["curriculum"], k["bildungsplan"], k["jahrgangsstufe"], k["std"]) == (
            PRAEFIX + "M Kl. 9", "2016.V2", "9", 20)
        # In der Reihenfolge des Curriculums, nicht nach Titel oder Anlage.
        assert [(s["titel"], s["std"]) for s in k["lernsequenzen"]] == [
            (PRAEFIX + "Zahlen in Normdarstellung", 4), (PRAEFIX + "Potenzfunktionen", 6)]
        # In der Form von `refs` — nach Zustimmung unverändert zu übernehmen.
        assert k["lernsequenzen"][0]["kompetenzen"] == [{
            "node_id": str(ik_a.id), "typ": "ik", "code": "3.3.1(1)",
            "titel": ik_a.title, "partiell": True,
        }]
        assert k["lernsequenzen"][1]["kompetenzen"] == [{
            "node_id": str(ik_b.id), "typ": "ik", "code": "3.3.4(1)", "titel": ik_b.title,
        }]
        assert "curricula" not in z

        # Dasselbe Kapitel über die Einheit — bis 0.15 dort immer ohne Lernsequenzen.
        einheit = await _rufe(async_engine, _handle_get_unit_detail, {"unit_node_id": ue}, TEACHER1_PSEUDO)
        assert einheit["kapitel"] == k
    finally:
        _aufraeumen(gruppen)


@pytest.mark.asyncio
async def test_ohne_einheit_die_curricula_der_gruppe(test_client, auth_headers, gruppen, async_engine):
    """Ohne Jahresplan wenigstens Stufe und Fassung — der Fall der Kursstufe in der
    Untersuchung, deren Gruppe keine Einheiten hatte."""
    _, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE, titel="Lose")
    async with _sitzungen(async_engine)() as db:
        from app.db.models import ContextEdge
        await db.execute(sa.delete(ContextEdge).where(
            ContextEdge.from_node_id == UUID(stunde), ContextEdge.relation == "part_of"))
        await _curriculum_mit_kapitel(db)
        await db.commit()
    try:
        z = (await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": stunde},
                         TEACHER1_PSEUDO))["zusammenhang"]
        assert z["einheit"] is None and z["kapitel"] is None
        assert z["jahrgang"] == 9
        assert {"titel": PRAEFIX + "M Kl. 9", "jahrgangsstufe": "9", "bildungsplan": "2016.V2"} in z["curricula"]
    finally:
        _aufraeumen(gruppen)


@pytest.mark.asyncio
async def test_fremdes_privates_kapitel_bleibt_zu(test_client, auth_headers, gruppen, async_engine):
    """Die Einheit gehört der Gruppe; das Kapitel, auf das sie zeigt, prüft seine eigene
    Sichtbarkeit."""
    ue, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE, titel="Privat")
    try:
        async with _sitzungen(async_engine)() as db:
            kap, _, _ = await _curriculum_mit_kapitel(db, read_scope="private", owner=TEACHER2_PSEUDO)
            await db.commit()
        await _verknuepfe(async_engine, ue, kap.id)

        z = (await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": stunde},
                         TEACHER1_PSEUDO))["zusammenhang"]
        assert z["einheit"]["id"] == ue
        assert z["kapitel"] is None
        einheit = await _rufe(async_engine, _handle_get_unit_detail, {"unit_node_id": ue}, TEACHER1_PSEUDO)
        assert einheit["kapitel"] is None
    finally:
        _aufraeumen(gruppen)


# ── Kompetenzen beim Schreiben prüfen (0.15) ─────────────────────────────────
#
# Bis 0.15 landeten `refs` ungeprüft in den Metadaten. Ein unbekannter `typ` verschwand
# still aus der Kompetenzleiste (sie filtert nach ik/pk), eine erfundene Kennung stand
# als Kompetenz ohne Knoten da.


async def _kompetenzen_der_stunde(client, h, stunde):
    return (await client.get(f"/planning/lessons/{stunde}", headers=h)).json()["refs"]


@pytest.mark.asyncio
async def test_kompetenzen_mit_dem_wortlaut_des_knotens(test_client, auth_headers, gruppen, async_engine):
    """Titel und Nummer kommen aus dem Knoten, nicht vom Modell; Doppelte entfallen."""
    _, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE, titel="Refs")
    try:
        async with _sitzungen(async_engine)() as db:
            _, ik_a, ik_b = await _curriculum_mit_kapitel(db)
            await db.commit()
        gelesen = await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": stunde}, TEACHER1_PSEUDO)
        phasen = [{"id": p["id"], "name": p["name"], "dauer_min": p["dauer_min"]} for p in gelesen["phasen"]]

        aus = await _rufe(async_engine, _handle_update_lesson_phases, {"node_id": stunde, "phasen": phasen, "refs": [
            {"node_id": str(ik_a.id), "typ": "ik", "code": "9.9(9)", "titel": "Erfundener Wortlaut", "partiell": True},
            {"node_id": str(ik_b.id), "typ": "ik"},
            {"node_id": str(ik_a.id), "typ": "ik"},
        ]}, TEACHER1_PSEUDO)
        assert aus.get("ok") is True, aus
        assert await _kompetenzen_der_stunde(test_client, auth_headers, stunde) == [
            {"node_id": str(ik_a.id), "typ": "ik", "code": "3.3.1(1)", "titel": ik_a.title, "partiell": True},
            {"node_id": str(ik_b.id), "typ": "ik", "code": "3.3.4(1)", "titel": ik_b.title, "partiell": False},
        ]
    finally:
        _aufraeumen(gruppen)


@pytest.mark.asyncio
@pytest.mark.parametrize("refs, im_fehler", [
    ("keine Liste", "Liste"),
    ([{"typ": "ik"}], "node_id"),
    ([{"node_id": "kein-uuid", "typ": "ik"}], "node_id"),
    ([{"node_id": "IK_A", "typ": "kompetenz"}], "typ muss"),
    ([{"node_id": "IK_A", "typ": "pk"}], "keine passende Kompetenz"),          # IK als PK
    ([{"node_id": str(uuid4()), "typ": "ik"}], "keine passende Kompetenz"),    # erfunden
])
async def test_falsche_kompetenzen_werden_abgewiesen(
    test_client, auth_headers, gruppen, async_engine, refs, im_fehler,
):
    """Abgewiesen wird der ganze Aufruf — vor dem Snapshot, also ohne Rückgängig-Schritt."""
    _, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE, titel="Refs falsch")
    try:
        async with _sitzungen(async_engine)() as db:
            _, ik_a, _ = await _curriculum_mit_kapitel(db)
            await db.commit()
        if isinstance(refs, list):
            refs = [{**r, "node_id": str(ik_a.id)} if r.get("node_id") == "IK_A" else r for r in refs]
        vorher = await _snapshots(async_engine, EIGENE)

        aus = await _rufe(async_engine, _handle_update_lesson_phases, {
            "node_id": stunde, "phasen": [{"name": "Neu", "dauer_min": 45}], "refs": refs,
        }, TEACHER1_PSEUDO)
        assert im_fehler in aus.get("error", ""), aus
        assert await _phasennamen(test_client, auth_headers, stunde) == ["Einstieg", "Erarbeitung"]
        assert await _snapshots(async_engine, EIGENE) == vorher
    finally:
        _aufraeumen(gruppen)


@pytest.mark.asyncio
async def test_fremde_private_kompetenz_ist_keine(test_client, auth_headers, gruppen, async_engine):
    from app.db.models import ContextNode
    _, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE, titel="Refs privat")
    try:
        async with _sitzungen(async_engine)() as db:
            fremd = ContextNode(category="concept", content_type="begriff", title=PRAEFIX + "Privatbegriff",
                                status="active", read_scope="private", write_scope="private",
                                owner_pseudonym=TEACHER2_PSEUDO, metadata_={})
            db.add(fremd)
            await db.commit()
        aus = await _rufe(async_engine, _handle_update_lesson_phases, {
            "node_id": stunde, "phasen": [{"name": "Neu", "dauer_min": 45}],
            "refs": [{"node_id": str(fremd.id), "typ": "concept"}],
        }, TEACHER1_PSEUDO)
        # Seit 0.17 weist ein unpassender Begriff den Aufruf nicht ab: Er bleibt draußen und
        # wird gemeldet (Plan „Fachbegriffe der Stunde" § 16, A1).
        assert aus.get("ok") is True and aus.get("nicht_eingetragen"), aus
        refs = (await test_client.get(f"/planning/lessons/{stunde}", headers=auth_headers)).json()["refs"]
        assert refs == []
    finally:
        _aufraeumen(gruppen)


# ── Nachbereitete Phasen gehen nicht verloren (0.15) ─────────────────────────
#
# Beim Zusammenlegen schrieb das Modell die neue Phase in 10 von 10 Läufen ohne Kennung —
# auch gegen ausdrückliche Anweisung. Bei einer nachbereiteten Stunde wäre damit der Status
# still weg; Reflow und Kompetenzverlauf hängen daran.


async def _mit_status(async_engine, stunde, status_je_name: dict):
    from app.db.models import ContextNode
    async with _sitzungen(async_engine)() as db:
        knoten = await db.get(ContextNode, UUID(stunde))
        meta = dict(knoten.metadata_)
        meta["phasen"] = [{**p, "status": status_je_name[p["name"]]} if p["name"] in status_je_name else p
                          for p in meta["phasen"]]
        knoten.metadata_ = meta
        await db.commit()
        return {p["name"]: p["id"] for p in meta["phasen"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("schreibe", [
    lambda ids: [{"id": ids["Einstieg"], "name": "Einstieg", "dauer_min": 10}],                 # weggelassen
    lambda ids: [{"id": ids["Einstieg"], "name": "Einstieg", "dauer_min": 10},
                 {"name": "Erarbeitung", "dauer_min": 25}],                                     # ohne Kennung neu
    lambda ids: [{"id": ids["Einstieg"], "name": "Einstieg & Erarbeitung", "dauer_min": 35}],  # zusammengelegt
], ids=["weggelassen", "neu_geschrieben", "zusammengelegt"])
async def test_nachbereitete_phase_bleibt(test_client, auth_headers, gruppen, async_engine, schreibe):
    _, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE, titel="Nachbereitet")
    ids = await _mit_status(async_engine, stunde, {"Erarbeitung": "erledigt"})
    vorher = await _snapshots(async_engine, EIGENE)

    aus = await _rufe(async_engine, _handle_update_lesson_phases,
                      {"node_id": stunde, "phasen": schreibe(ids)}, TEACHER1_PSEUDO)
    assert "„Erarbeitung“ (erledigt)" in aus.get("error", ""), aus
    assert await _phasennamen(test_client, auth_headers, stunde) == ["Einstieg", "Erarbeitung"]
    assert await _snapshots(async_engine, EIGENE) == vorher


@pytest.mark.asyncio
async def test_nachbereitete_phase_aendern_geht(test_client, auth_headers, gruppen, async_engine):
    """Mit ihrer Kennung bleibt die Phase änderbar — und behält ihren Status."""
    _, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE, titel="Ändern")
    ids = await _mit_status(async_engine, stunde, {"Erarbeitung": "offen"})

    aus = await _rufe(async_engine, _handle_update_lesson_phases, {"node_id": stunde, "phasen": [
        {"id": ids["Erarbeitung"], "name": "Erarbeitung mit Lösungsblatt", "dauer_min": 20},
    ]}, TEACHER1_PSEUDO)   # „Einstieg" ohne Status darf weg
    assert aus.get("ok") is True, aus
    gelesen = await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": stunde}, TEACHER1_PSEUDO)
    assert [(p["id"], p["name"], p.get("status")) for p in gelesen["phasen"]] == [
        (ids["Erarbeitung"], "Erarbeitung mit Lösungsblatt", "offen")]


@pytest.mark.asyncio
async def test_uebertragene_phase_darf_weg(test_client, auth_headers, gruppen, async_engine):
    """„geplant" setzt das Übertragen, nicht die Nachbereitung — sie zu streichen ist Planung."""
    _, stunde = await _einheit_und_stunde(test_client, auth_headers, EIGENE, titel="Übertragen")
    ids = await _mit_status(async_engine, stunde, {"Erarbeitung": "geplant"})

    aus = await _rufe(async_engine, _handle_update_lesson_phases, {"node_id": stunde, "phasen": [
        {"id": ids["Einstieg"], "name": "Einstieg", "dauer_min": 10}]}, TEACHER1_PSEUDO)
    assert aus.get("ok") is True, aus
    assert await _phasennamen(test_client, auth_headers, stunde) == ["Einstieg"]
