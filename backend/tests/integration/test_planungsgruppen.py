"""`GET /planning/groups` — die eigenen Unterrichtsgruppen für Zugangstoken (G1).

Plan *Unterrichtsgruppen-Liste-Plattform-Plan* (04.10.2026): Das Obsidian-Plugin soll
seine Gruppen auf Knopfdruck anbieten (Ordnername aus Fach, Klasse, Jahrgang), statt
sie über die `group_id` von Hand eingerichtet zu bekommen.

Teacher1 hat aus anderen Testmodulen weitere Gruppen; geprüft wird deshalb nur, was in
diesem Modul angelegt wird (Kennungen 3400–3419).
"""
from datetime import timedelta

import psycopg2
import pytest
from sqlalchemy import event

from app.groups.jahrgang import leite_jahrgang_ab
from app.planning.calendar import load_school_year

T1, T2 = "teacher1-pseudo", "teacher2-pseudo"
BEREICH = range(3400, 3420)

FACH_CH, FACH_NWT = 3400, 3401
# Unterrichtsgruppen, in denen T1 Lehrkraft ist
CH_9D, NWT_9, ABI, FESTGELEGT, FRUEHER, OHNE_FACH = 3400, 3401, 3402, 3403, 3404, 3405
# Was T1 **nicht** sehen darf
KLASSE_9D, KLASSE_9A, KLASSE_9C, FACHSCHAFT, ALS_SCHUELER, FREMD = 3410, 3411, 3412, 3413, 3414, 3415


@pytest.fixture(scope="module")
def gruppen(db_url, run_migrations):
    cfg = load_school_year()
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        # Ein eigenes Kürzel: `fach_code` ist eindeutig, und spätere Module legen „CH" an.
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order, fach_code) VALUES "
                    "(3400, 'chemie-g1', 'Chemie G1', 0, 'G1CH'), "
                    "(3401, 'nwt-g1', 'NwT G1', 0, NULL) ON CONFLICT (id) DO NOTHING")

        def gruppe(gid, name, typ="teaching_group", fach=None, anzeige=None, jahrgang=None,
                   angelegt=None):
            cur.execute(
                "INSERT INTO groups (id, name, slug, type, subject_id, display_name, jahrgang, "
                "created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, COALESCE(%s, now())) "
                "ON CONFLICT (id) DO NOTHING",
                (gid, name, f"g1-{gid}", typ, fach, anzeige, jahrgang, angelegt),
            )

        gruppe(CH_9D, "ch-9d", fach=FACH_CH)
        gruppe(NWT_9, "nwt-tl-9ac", fach=FACH_NWT, anzeige="NwT 9")
        gruppe(ABI, "ch-tl-abi28", fach=FACH_CH)
        gruppe(FESTGELEGT, "ch-9d-zusatz", fach=FACH_CH, jahrgang=7)
        gruppe(FRUEHER, "ch-9c-vorjahr", fach=FACH_CH, angelegt=cfg.beginn - timedelta(days=30))
        gruppe(OHNE_FACH, "ag-robotik-8")
        gruppe(KLASSE_9D, "9D", typ="school_class")
        gruppe(KLASSE_9A, "9A", typ="school_class")
        gruppe(KLASSE_9C, "9C", typ="school_class")
        gruppe(FACHSCHAFT, "fs.chemie-g1", typ="subject_department", fach=FACH_CH)
        gruppe(ALS_SCHUELER, "ch-schuelersicht", fach=FACH_CH)
        gruppe(FREMD, "ch-kollegin", fach=FACH_CH)

        for gid in (CH_9D, NWT_9, ABI, FESTGELEGT, FRUEHER, OHNE_FACH):
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                        "VALUES (%s, %s, 'teacher', 'eigen') ON CONFLICT DO NOTHING", (gid, T1))
        for gid, rolle in ((KLASSE_9D, "teacher"), (FACHSCHAFT, "teacher"), (ALS_SCHUELER, "student")):
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                        "VALUES (%s, %s, %s, 'eigen') ON CONFLICT DO NOTHING", (gid, T1, rolle))
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (%s, %s, 'teacher', 'eigen') ON CONFLICT DO NOTHING", (FREMD, T2))

        for gid, klasse in ((CH_9D, KLASSE_9D), (NWT_9, KLASSE_9C), (NWT_9, KLASSE_9A),
                            (FESTGELEGT, KLASSE_9D), (FRUEHER, KLASSE_9C)):
            cur.execute("INSERT INTO group_source_classes (group_id, class_group_id) VALUES (%s, %s) "
                        "ON CONFLICT DO NOTHING", (gid, klasse))

        # Ein Termin im laufenden Schuljahr, einer davor — gezählt wird nur der erste.
        cur.execute("DELETE FROM lesson_slots WHERE group_id = %s", (CH_9D,))
        for datum in (cfg.beginn, cfg.beginn - timedelta(days=10)):
            cur.execute("INSERT INTO lesson_slots (group_id, date, start_period, periods, halbjahr, "
                        "kategorie) VALUES (%s, %s, 1, 1, 1, 'unterricht')", (CH_9D, datum))
    conn.commit()
    yield cfg

    # Aufräumen: Klassen namens „9D" oder eine weitere Gruppe von teacher1 sollen kein
    # späteres Modul überraschen.
    with conn.cursor() as cur:
        cur.execute("DELETE FROM groups WHERE id BETWEEN %s AND %s", (BEREICH.start, BEREICH.stop - 1))
        cur.execute("DELETE FROM subjects WHERE id IN (%s, %s)", (FACH_CH, FACH_NWT))
    conn.commit()
    conn.close()


async def _liste(client, headers):
    resp = await client.get("/planning/groups", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _hier(items):
    return {g["id"]: g for g in items if g["id"] in BEREICH}


@pytest.mark.asyncio
async def test_nur_eigene_unterrichtsgruppen_als_lehrkraft(test_client, auth_headers, gruppen):
    """⚠️ Der Wächter: Der Filter ist die Zugriffsregel."""
    gesehen = set(_hier(await _liste(test_client, auth_headers)))
    assert gesehen == {CH_9D, NWT_9, ABI, FESTGELEGT, FRUEHER, OHNE_FACH}
    # Klasse und Fachschaft (Mitglied, aber keine Unterrichtsgruppe), Gruppe als
    # Schüler:in, Gruppe der Kollegin
    assert not gesehen & {KLASSE_9D, FACHSCHAFT, ALS_SCHUELER, FREMD}


@pytest.mark.asyncio
async def test_felder(test_client, auth_headers, gruppen):
    cfg = gruppen
    g = _hier(await _liste(test_client, auth_headers))

    assert g[CH_9D]["fach"] == {"id": FACH_CH, "slug": "chemie-g1", "name": "Chemie G1", "fach_code": "G1CH"}
    assert g[NWT_9]["fach"]["fach_code"] is None
    assert g[OHNE_FACH]["fach"] is None

    # Anzeigename, nicht der rohe
    assert g[NWT_9]["name"] == "NwT 9"
    # Klassen sortiert, beim Kurs ohne Klassenverband leer
    assert g[NWT_9]["klassen"] == ["9A", "9C"]
    assert g[CH_9D]["klassen"] == ["9D"]
    assert g[ABI]["klassen"] == []

    # Jahrgang in allen drei Lagen: Festlegung vor Klasse, Klasse, Name
    assert g[FESTGELEGT]["jahrgang"] == 7
    assert g[CH_9D]["jahrgang"] == 9
    assert g[NWT_9]["jahrgang"] == 9
    assert g[ABI]["jahrgang"] == leite_jahrgang_ab("ch-tl-abi28", schuljahr_ende=cfg.ende.year)
    assert g[OHNE_FACH]["jahrgang"] == 8

    # Mit Quellklasse, ohne Beleg, vor Schuljahresbeginn angelegt: früher
    assert g[FRUEHER]["aktuell"] is False
    assert g[CH_9D]["aktuell"] is True  # Termin im laufenden Jahr
    assert g[ABI]["aktuell"] is True    # Kurs ohne Klassenverband

    assert g[CH_9D]["termine"] == 1
    assert g[ABI]["termine"] == 0


@pytest.mark.asyncio
async def test_jahrgang_wie_die_curriculum_auswahl(test_client, auth_headers, gruppen):
    """Eine Regel, nicht zwei — sonst zeigte das Plugin einen anderen Jahrgang."""
    g = _hier(await _liste(test_client, auth_headers))
    for gid in (CH_9D, NWT_9, ABI, FESTGELEGT, FRUEHER):
        resp = await test_client.get(f"/planning/groups/{gid}/curriculum-chapters", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["grade"] == g[gid]["jahrgang"], gid


@pytest.mark.asyncio
async def test_sortiert_nach_anzeigename(test_client, auth_headers, gruppen):
    namen = [g["name"] for g in await _liste(test_client, auth_headers)]
    assert namen == sorted(namen, key=str.casefold)


@pytest.mark.asyncio
async def test_ohne_unterrichtsgruppen_leere_liste(test_client, jwt_service, gruppen):
    token, _ = jwt_service.issue(pseudonym="planungsgruppen-leer", roles=["teacher"], grade=None)
    assert await _liste(test_client, {"Cookie": f"session={token}"}) == []


@pytest.mark.asyncio
async def test_abfragen_wachsen_nicht_mit_den_gruppen(
    test_client, auth_headers, auth_headers_teacher2, async_engine, gruppen
):
    """Teacher1 hat ein Vielfaches der Gruppen von Teacher2 — gleich viele Abfragen."""
    zaehler = {"n": 0}

    def zaehle(*_):
        zaehler["n"] += 1

    event.listen(async_engine.sync_engine, "before_cursor_execute", zaehle)
    try:
        anzahl = {}
        for wer, headers in (("viele", auth_headers), ("wenige", auth_headers_teacher2)):
            zaehler["n"] = 0
            gruppen_gesehen = len(await _liste(test_client, headers))
            anzahl[wer] = (zaehler["n"], gruppen_gesehen)
    finally:
        event.remove(async_engine.sync_engine, "before_cursor_execute", zaehle)

    assert anzahl["viele"][1] > anzahl["wenige"][1] >= 1
    assert anzahl["viele"][0] == anzahl["wenige"][0]
