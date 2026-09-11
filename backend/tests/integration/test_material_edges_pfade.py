"""Integrationstests: Jeder Speicherpfad zieht die Materialkanten nach (AP6b, Schritt 2).

Die Entscheidungslogik prüft `tests/unit/test_material_edges.py` ohne Datenbank.
Hier geht es allein um die **Verdrahtung**: Kommt der Abgleich in jedem Pfad an,
der Stundenphasen schreibt?

Der Unterschied verdient eigene Tests. In AP4 war die `valid_until`-Vorbelegung
vollständig gebaut und geprüft — sie hatte nur an den Anlegestellen keinen
Eingang, und null von 19 134 Knoten trugen ein Ablaufdatum. Eine korrekte
Funktion, die niemand ruft, ist von einer, die es nicht gibt, nicht zu
unterscheiden.

Geschrieben wird ausschließlich über die API: `db_session` läuft in einer
zurückgerollten Transaktion und verträgt keine Commits (conftest). Gelesen wird
mit psycopg2 — das umgeht zugleich den Identity-Map-Cache der ORM-Sitzung.

Router-Pfade ohne /api-Präfix (CLAUDE.md: FastAPI sieht /api nie).
"""
import json
import uuid

import psycopg2
import pytest

TEACHER_PSEUDO = "teacher1-pseudo"
SUBJECT_ID = 610
GROUP_ID = 610


@pytest.fixture(scope="module")
def sync_conn(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def seed_material_gruppe(sync_conn):
    """Fach, Unterrichtsgruppe und Mitgliedschaft für die Pfad-Tests."""
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO subjects (id, slug, name, sort_order) "
            "VALUES (%s, 'material-test', 'Materialtest', 0) ON CONFLICT (id) DO NOTHING",
            (SUBJECT_ID,),
        )
        cur.execute(
            "INSERT INTO groups (id, name, slug, type, subject_id) "
            "VALUES (%s, '9c Material', '9c-material-test', 'teaching_group', %s) "
            "ON CONFLICT (id) DO NOTHING",
            (GROUP_ID, SUBJECT_ID),
        )
        cur.execute(
            "INSERT INTO group_memberships (group_id, pseudonym, role_in_group) "
            "VALUES (%s, %s, 'teacher') ON CONFLICT DO NOTHING",
            (GROUP_ID, TEACHER_PSEUDO),
        )
    sync_conn.commit()
    yield
    with sync_conn.cursor() as cur:
        cur.execute("DELETE FROM group_memberships WHERE group_id = %s", (GROUP_ID,))
        cur.execute("DELETE FROM groups WHERE id = %s", (GROUP_ID,))
        cur.execute("DELETE FROM subjects WHERE id = %s", (SUBJECT_ID,))
    sync_conn.commit()


def _neuer_knoten(cur, titel, content_type, category, *, gruppe=None):
    """Legt einen Knoten an; mit `gruppe` als Unterrichtsgruppen-Knoten.

    Die Stunde **braucht** die Gruppe: `patch_lesson` liest sie aus
    `write_scope_group_id` und lehnt sonst mit 422 ab. Material darf privat sein.
    """
    nid = uuid.uuid4()
    scope = "group" if gruppe else "private"
    cur.execute(
        "INSERT INTO context_nodes "
        "(id, category, content_type, title, read_scope, write_scope, "
        " read_scope_group_id, write_scope_group_id, status, metadata) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', '{}')",
        (str(nid), category, content_type, titel, scope, scope, gruppe, gruppe),
    )
    return nid


@pytest.fixture
def knoten(sync_conn, seed_material_gruppe):
    """Eine Stunde (an der Gruppe) und zwei Materialknoten — ohne Kanten."""
    with sync_conn.cursor() as cur:
        stunde = _neuer_knoten(
            cur, "Testsstunde", "unterrichtsstunde", "artifact", gruppe=GROUP_ID
        )
        ab = _neuer_knoten(cur, "Arbeitsblatt Bruchrechnung", "arbeitsblatt", "artifact")
        begriff = _neuer_knoten(cur, "Bruch", "begriff", "concept")
    sync_conn.commit()
    yield stunde, ab, begriff
    # Nach einem gescheiterten Statement ist die Transaktion vergiftet; ohne das
    # Zurückrollen verdeckte ein Aufräumfehler den eigentlichen Testfehler.
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        cur.execute("DELETE FROM context_edges WHERE from_node_id = %s", (str(stunde),))
        cur.execute(
            "DELETE FROM slot_plan_snapshots WHERE group_id = %s", (GROUP_ID,)
        )
        for n in (stunde, ab, begriff):
            cur.execute("DELETE FROM context_nodes WHERE id = %s", (str(n),))
    sync_conn.commit()


def _phase(phase_id, *node_ids):
    return {
        "id": phase_id,
        "name": "Erarbeitung",
        "dauer_min": 15,
        "prio": "kern",
        "material": [
            {"typ": "node", "node_id": str(n), "titel": "Material"} for n in node_ids
        ],
    }


def _materialkanten(conn, stunde_id) -> dict[str, list]:
    """Ziel → Phasenliste, nur die abgeleiteten Kanten."""
    conn.rollback()  # frischer Snapshot: die API hat in einer anderen Sitzung committet
    with conn.cursor() as cur:
        cur.execute(
            "SELECT to_node_id, metadata->'phasen' FROM context_edges "
            "WHERE from_node_id = %s AND relation = 'used_with' "
            "AND metadata->>'via' = 'material'",
            (str(stunde_id),),
        )
        return {str(ziel): phasen for ziel, phasen in cur.fetchall()}


def _alle_used_with(conn, stunde_id) -> list[str]:
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT metadata->>'via' FROM context_edges "
            "WHERE from_node_id = %s AND relation = 'used_with'",
            (str(stunde_id),),
        )
        return sorted(via for (via,) in cur.fetchall())


# ── Pfad 1: Editor (PATCH /planning/lessons/{id}) ────────────────────────────

@pytest.mark.asyncio
async def test_editor_legt_kanten_an_und_raeumt_sie_wieder_ab(
    test_client, sync_conn, auth_headers, knoten
):
    stunde, ab, begriff = knoten

    resp = await test_client.patch(
        f"/planning/lessons/{stunde}",
        json={"phasen": [_phase("p1", ab, begriff)]},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert _materialkanten(sync_conn, stunde) == {
        str(ab): ["p1"],
        str(begriff): ["p1"],
    }

    # Material herausgenommen → die Kante muss verschwinden, nicht stehen bleiben.
    resp = await test_client.patch(
        f"/planning/lessons/{stunde}",
        json={"phasen": [_phase("p1", begriff)]},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert _materialkanten(sync_conn, stunde) == {str(begriff): ["p1"]}


@pytest.mark.asyncio
async def test_editor_fuehrt_dasselbe_material_aus_zwei_phasen_zusammen(
    test_client, sync_conn, auth_headers, knoten
):
    stunde, ab, _ = knoten

    resp = await test_client.patch(
        f"/planning/lessons/{stunde}",
        json={"phasen": [_phase("p1", ab), _phase("p2", ab)]},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert _materialkanten(sync_conn, stunde) == {str(ab): ["p1", "p2"]}, (
        "eine Kante, beide Phasen — nicht zwei Kanten"
    )


@pytest.mark.asyncio
async def test_freitext_material_erzeugt_keine_kante(
    test_client, sync_conn, auth_headers, knoten
):
    stunde, _, _ = knoten

    resp = await test_client.patch(
        f"/planning/lessons/{stunde}",
        json={
            "phasen": [
                {
                    "id": "p1",
                    "name": "Erarbeitung",
                    "dauer_min": 15,
                    "prio": "kern",
                    "material": [{"typ": "text", "wert": "Buch S. 42"}],
                }
            ]
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert _materialkanten(sync_conn, stunde) == {}


@pytest.mark.asyncio
async def test_editor_laesst_fremde_used_with_kanten_in_ruhe(
    test_client, sync_conn, auth_headers, knoten
):
    """Von Hand gezogene Verbindungen dürfen der Ableitung nicht zum Opfer fallen.

    Ohne die `via`-Marke im Abgleich löschte der nächste Speichervorgang jede
    `used_with`-Kante, die nicht aus den Phasen stammt.
    """
    stunde, ab, begriff = knoten
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO context_edges (from_node_id, to_node_id, relation, metadata) "
            "VALUES (%s, %s, 'used_with', %s)",
            (str(stunde), str(begriff), json.dumps({"via": "handarbeit"})),
        )
    sync_conn.commit()

    resp = await test_client.patch(
        f"/planning/lessons/{stunde}",
        json={"phasen": [_phase("p1", ab)]},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert _alle_used_with(sync_conn, stunde) == ["handarbeit", "material"]


# ── Pfad 2: Snapshot-Rückweg (POST /planning/snapshots/{id}/restore) ─────────

@pytest.mark.asyncio
async def test_snapshot_rueckweg_zieht_die_kanten_nach(
    test_client, sync_conn, auth_headers, knoten
):
    """Ein Rückweg tauscht die Phasen vollständig aus — die Kanten müssen folgen."""
    stunde, ab, begriff = knoten

    # Zustand „vorher" herstellen und als Snapshot festhalten.
    resp = await test_client.patch(
        f"/planning/lessons/{stunde}",
        json={"phasen": [_phase("p1", ab)]},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    snapshot_id = uuid.uuid4()
    with sync_conn.cursor() as cur:
        # `reason` ist per CHECK auf eine feste Liste beschränkt (models.py).
        cur.execute(
            "INSERT INTO slot_plan_snapshots (id, group_id, reason, payload, created_by) "
            "VALUES (%s, %s, 'manual', %s, %s)",
            (
                str(snapshot_id),
                GROUP_ID,
                json.dumps(
                    {"slots": [], "stunden_phasen": {str(stunde): [_phase("p1", str(ab))]}}
                ),
                TEACHER_PSEUDO,
            ),
        )
    sync_conn.commit()

    # Zustand „jetzt": stattdessen der Begriff in einer anderen Phase.
    resp = await test_client.patch(
        f"/planning/lessons/{stunde}",
        json={"phasen": [_phase("p9", begriff)]},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert _materialkanten(sync_conn, stunde) == {str(begriff): ["p9"]}

    resp = await test_client.post(
        f"/planning/snapshots/{snapshot_id}/restore", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text

    assert _materialkanten(sync_conn, stunde) == {str(ab): ["p1"]}, (
        "nach dem Rückweg muss das Material des Snapshots gelten, nicht das aktuelle"
    )


# ── Pfad 3: Phasen-Übertragung (apply_operations) ────────────────────────────

@pytest.mark.asyncio
async def test_uebertragung_zieht_beide_stunden_nach(
    async_engine, sync_conn, seed_material_gruppe
):
    """Der einzige Pfad, bei dem **zwei** Knoten betroffen sind.

    `TransferPhases` verschiebt Phasen von der Quelle zur Zielstunde — die Quelle
    verliert Material, das Ziel gewinnt es. Ein Abgleich nur für die Zielstunde
    ließe an der Quelle eine Kante stehen, die einen Einsatz behauptet, den es dort
    nicht mehr gibt. Deshalb synchronisiert `apply_operations` **alle** beteiligten
    Stunden, nicht nur die der jeweiligen Operation.

    Kein `db_session`: `apply_operations` committet selbst, und die Fixture läuft
    in einer zurückgerollten Transaktion.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db.models import ContextNode
    from app.planning.material_edges import synchronisiere_materialkanten
    from app.planning.operations import TransferPhases, apply_operations

    with sync_conn.cursor() as cur:
        quelle = _neuer_knoten(cur, "Quelle", "unterrichtsstunde", "artifact", gruppe=GROUP_ID)
        ziel = _neuer_knoten(cur, "Ziel", "unterrichtsstunde", "artifact", gruppe=GROUP_ID)
        ab = _neuer_knoten(cur, "Arbeitsblatt", "arbeitsblatt", "artifact")
        cur.execute(
            "UPDATE context_nodes SET metadata = %s WHERE id = %s",
            (json.dumps({"phasen": [_phase("p1", str(ab))]}), str(quelle)),
        )
        cur.execute(
            "UPDATE context_nodes SET metadata = %s WHERE id = %s",
            (json.dumps({"phasen": []}), str(ziel)),
        )
    sync_conn.commit()

    try:
        session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
        async with session_factory() as session:
            # Ausgangslage: die Kante hängt an der Quelle.
            node = await session.get(ContextNode, quelle)
            await synchronisiere_materialkanten(session, quelle, node.metadata_)
            await session.commit()
        assert _materialkanten(sync_conn, quelle) == {str(ab): ["p1"]}
        assert _materialkanten(sync_conn, ziel) == {}

        async with session_factory() as session:
            res = await apply_operations(
                session,
                GROUP_ID,
                [TransferPhases(op="transfer_phases", from_lesson_id=quelle,
                                to_lesson_id=ziel, phase_ids=["p1"])],
                summary="Test-Übertragung",
                created_by=TEACHER_PSEUDO,
            )
        assert res.errors == [], res.errors

        assert _materialkanten(sync_conn, quelle) == {}, "Quelle muss die Kante verlieren"
        assert _materialkanten(sync_conn, ziel) == {str(ab): ["p1"]}, "Ziel muss sie bekommen"
    finally:
        sync_conn.rollback()
        with sync_conn.cursor() as cur:
            for n in (quelle, ziel):
                cur.execute("DELETE FROM context_edges WHERE from_node_id = %s", (str(n),))
            cur.execute("DELETE FROM slot_plan_snapshots WHERE group_id = %s", (GROUP_ID,))
            for n in (quelle, ziel, ab):
                cur.execute("DELETE FROM context_nodes WHERE id = %s", (str(n),))
        sync_conn.commit()
