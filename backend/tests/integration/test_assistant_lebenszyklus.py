"""Der Lebenszyklus eines Assistenten über die echte Schnittstelle (Paket 7, AP4).

Die Regeln selbst stehen in `tests/unit/test_assistant_lebenszyklus.py` — hier geht es um
das, was nur der ganze Weg zeigt: dass eine **Lehrkraft ohne Adminrolle** ihren eigenen
Gruppen-Assistenten wirklich ändern, abschalten und löschen kann, und dass der
Löschantrag den schulweiten Assistenten **nicht** abschaltet.

⚠️ **Mit `auth_headers_teacher2`, nicht `auth_headers`.** Letztere trägt `["teacher",
"admin"]` — mit ihr ginge alles, und der Test bewiese nichts. Genau daran lag es, dass
der Fehler ein halbes Jahr unbemerkt blieb: Wer beim Testen zugleich Admin ist, trifft
die Sperre nie.
"""
import psycopg2
import pytest

from tests.integration.conftest import TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio

NAMEN = ("LZ Gruppe", "LZ Schulweit", "LZ Eingereicht")


@pytest.fixture
def assistenten(db_url, run_migrations):
    """Drei eigene Assistenten von teacher2 — je einer pro Lage."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    ids = {}
    with conn.cursor() as cur:
        for name, scope, status in (
            ("LZ Gruppe", "teaching_group", "active"),
            ("LZ Schulweit", "all", "active"),
            ("LZ Eingereicht", "all", "pending_review"),
        ):
            # ⚠️ `audience` ausdrücklich — die Spaltenvorgabe in der Datenbank ist
            # doppelt gequotet (`'''student'''`) und verletzt damit ihre eigene
            # CHECK-Bedingung. Eigener Todo; hier nur umgangen.
            cur.execute(
                "INSERT INTO assistants (name, system_prompt, model, scope, status,"
                " audience, created_by, creator_role)"
                " VALUES (%s, 'P', 'm', %s, %s, 'all', %s, 'teacher') RETURNING id",
                (name, scope, status, TEACHER2_PSEUDO),
            )
            ids[name] = cur.fetchone()[0]
    conn.commit()
    yield ids, conn
    with conn.cursor() as cur:
        cur.execute("DELETE FROM assistants WHERE name = ANY(%s)", (list(NAMEN),))
    conn.commit()
    conn.close()


def _stand(conn, aid):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, deletion_requested_at, deletion_reason FROM assistants"
            " WHERE id = %s",
            (aid,),
        )
        return cur.fetchone()


async def test_lehrkraft_aendert_ihren_gruppenassistenten(
    test_client, auth_headers_teacher2, assistenten
):
    """⚠️ **Der Fehler, um den es ging.** Vorher: 409, obwohl die Oberfläche das Feld anbot."""
    ids, _ = assistenten
    resp = await test_client.patch(
        f"/assistants/{ids['LZ Gruppe']}",
        json={"name": "LZ Gruppe"},
        headers=auth_headers_teacher2,
    )
    assert resp.status_code == 200, resp.text


async def test_schulweiter_assistent_bleibt_gesperrt(
    test_client, auth_headers_teacher2, assistenten
):
    """Die Gegenprobe: Ohne sie hätte die Lockerung auch die Freigabe ausgehebelt."""
    ids, _ = assistenten
    resp = await test_client.patch(
        f"/assistants/{ids['LZ Schulweit']}",
        json={"name": "Neuer Name"},
        headers=auth_headers_teacher2,
    )
    assert resp.status_code == 409, resp.text


async def test_abschalten_und_wieder_freigeben(
    test_client, auth_headers_teacher2, assistenten
):
    ids, conn = assistenten
    aid = ids["LZ Gruppe"]
    assert (
        await test_client.post(f"/assistants/{aid}/disable", headers=auth_headers_teacher2)
    ).status_code == 200
    assert _stand(conn, aid)[0] == "disabled"
    assert (
        await test_client.post(f"/assistants/{aid}/enable", headers=auth_headers_teacher2)
    ).status_code == 200
    assert _stand(conn, aid)[0] == "active"


async def test_schulweiten_schaltet_die_lehrkraft_nicht_ab(
    test_client, auth_headers_teacher2, assistenten
):
    """Dort hängen Kolleg:innen dran, die von der Abschaltung nichts wüssten."""
    ids, _ = assistenten
    resp = await test_client.post(
        f"/assistants/{ids['LZ Schulweit']}/disable", headers=auth_headers_teacher2
    )
    assert resp.status_code == 409


async def test_einreichung_zurueckziehen(test_client, auth_headers_teacher2, assistenten):
    """Der Rückweg fehlte ganz — es blieb nur Löschen und neu schreiben."""
    ids, conn = assistenten
    resp = await test_client.post(
        f"/assistants/{ids['LZ Eingereicht']}/withdraw", headers=auth_headers_teacher2
    )
    assert resp.status_code == 200, resp.text
    assert _stand(conn, ids["LZ Eingereicht"])[0] == "draft"


async def test_loeschantrag_schaltet_nichts_ab(
    test_client, auth_headers_teacher2, assistenten
):
    """⚠️ **Die Entscheidung vom 25.09.2026 in einer Zeile.**

    Ein Antrag ist eine Bitte, keine Handlung: Der Assistent bleibt `active`, bis die
    Administration entscheidet. Genau deshalb ist es ein Feld und kein Status — ein
    Statuswert `deletion_requested` müsste überall wie `active` behandelt werden.
    """
    ids, conn = assistenten
    aid = ids["LZ Schulweit"]
    resp = await test_client.post(
        f"/assistants/{aid}/request-deletion",
        json={"reason": "Wird nicht mehr gebraucht"},
        headers=auth_headers_teacher2,
    )
    assert resp.status_code == 200, resp.text
    status, beantragt, grund = _stand(conn, aid)
    assert status == "active"
    assert beantragt is not None
    assert grund == "Wird nicht mehr gebraucht"


async def test_loeschantrag_laesst_sich_zuruecknehmen(
    test_client, auth_headers_teacher2, assistenten
):
    ids, conn = assistenten
    aid = ids["LZ Schulweit"]
    await test_client.post(
        f"/assistants/{aid}/request-deletion", json={"reason": None},
        headers=auth_headers_teacher2,
    )
    resp = await test_client.delete(
        f"/assistants/{aid}/request-deletion", headers=auth_headers_teacher2
    )
    assert resp.status_code == 200, resp.text
    assert _stand(conn, aid)[1] is None


async def test_fuer_eigene_gruppen_gibt_es_keinen_antrag(
    test_client, auth_headers_teacher2, assistenten
):
    """Wer selbst löschen darf, soll nicht beantragen — sonst wartet jemand auf nichts."""
    ids, _ = assistenten
    resp = await test_client.post(
        f"/assistants/{ids['LZ Gruppe']}/request-deletion",
        json={"reason": None},
        headers=auth_headers_teacher2,
    )
    assert resp.status_code == 409


async def test_lehrkraft_loescht_ihren_gruppenassistenten(
    test_client, auth_headers_teacher2, assistenten
):
    """Die Chats bleiben — `assistant_id` steht auf `ON DELETE SET NULL`."""
    ids, conn = assistenten
    resp = await test_client.delete(
        f"/assistants/{ids['LZ Gruppe']}", headers=auth_headers_teacher2
    )
    assert resp.status_code == 204, resp.text
    assert _stand(conn, ids["LZ Gruppe"]) is None


async def test_freigegebenen_schulweiten_loescht_sie_nicht(
    test_client, auth_headers_teacher2, assistenten
):
    ids, _ = assistenten
    resp = await test_client.delete(
        f"/assistants/{ids['LZ Schulweit']}", headers=auth_headers_teacher2
    )
    assert resp.status_code == 409
