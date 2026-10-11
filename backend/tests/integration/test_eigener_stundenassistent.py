"""„Eigenen Stundenassistenten anlegen" (0.15, Plan Schritt 7).

Die Vorlage ist der schulweite Stundenassistent; die Kopie trägt seinen **aktuellen** Prompt,
ist privat, sofort aktiv und kann Stunden planen.

⚠️ **Angelegt wird mit `auth_headers_teacher2`** — einer Lehrkraft ohne Adminrolle. Nur so
zeigt sich, dass die Fähigkeit beim Speichern im Editor stehen bleibt: Den Abschnitt
„Fähigkeiten" sieht und schickt nur ein Admin (`AssistantEditor.svelte`).
"""
import psycopg2
import pytest

from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio

VORLAGE = "ESA Stundenentwurf"
ANDERE = ("ESA Jahresplanung", "ESA Entwurf")


def _verbindung(db_url):
    return psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))


def _assistent(cur, name, prompt, scope, status, tool_groups):
    # `audience` ausdrücklich — die Spaltenvorgabe ist kaputt (siehe test_assistant_lebenszyklus).
    cur.execute(
        "INSERT INTO assistants (name, system_prompt, model, scope, status, audience,"
        " tool_groups, created_by, creator_role)"
        " VALUES (%s, %s, '', %s, %s, 'teacher', %s::jsonb, 'admin-esa', 'admin') RETURNING id",
        (name, prompt, scope, status, tool_groups),
    )
    return cur.fetchone()[0]


def _aufraeumen(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM assistants WHERE name = ANY(%s)", ([VORLAGE, *ANDERE],))
        cur.execute("DELETE FROM assistants WHERE created_by = ANY(%s) AND name LIKE 'Mein Stundenassistent%%'",
                    ([TEACHER1_PSEUDO, TEACHER2_PSEUDO],))
    conn.commit()


FACH = 793


@pytest.fixture
def fach(db_url, run_migrations):
    conn = _verbindung(db_url)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) VALUES (%s, 'esa-fach', 'ESA-Fach', 0)"
                    " ON CONFLICT (id) DO NOTHING", (FACH,))
    conn.commit()
    yield FACH
    _aufraeumen(conn)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM subjects WHERE id = %s", (FACH,))
    conn.commit()
    conn.close()


@pytest.fixture
def vorlage(db_url, run_migrations):
    """Der schulweite Stundenassistent — daneben einer, der keine Vorlage sein darf."""
    conn = _verbindung(db_url)
    _aufraeumen(conn)
    with conn.cursor() as cur:
        vid = _assistent(cur, VORLAGE, "Du planst Stunden. Fassung 1.", "teachers", "active",
                         '["lesson_planning"]')
        _assistent(cur, "ESA Jahresplanung", "Du planst Jahre.", "teachers", "active", '["planning"]')
    conn.commit()
    yield vid
    _aufraeumen(conn)
    conn.close()


@pytest.fixture
def ohne_vorlage(db_url, run_migrations):
    """Kein benutzbarer schulweiter Stundenassistent: einer mit Jahresplanung, einer im Entwurf."""
    conn = _verbindung(db_url)
    _aufraeumen(conn)
    with conn.cursor() as cur:
        _assistent(cur, "ESA Jahresplanung", "Du planst Jahre.", "teachers", "active", '["planning"]')
        _assistent(cur, "ESA Entwurf", "Noch nicht fertig.", "teachers", "draft", '["lesson_planning"]')
    conn.commit()
    yield
    _aufraeumen(conn)
    conn.close()


async def _anlegen(client, headers):
    return await client.post("/assistants/eigener-stundenassistent", headers=headers)


async def test_privat_aktiv_mit_stundenplanung(test_client, auth_headers_teacher2, vorlage):
    resp = await _anlegen(test_client, auth_headers_teacher2)
    assert resp.status_code == 201, resp.text
    a = resp.json()
    assert (a["scope"], a["status"], a["audience"]) == ("private", "active", "teacher")
    assert a["tool_groups"] == ["lesson_planning"]
    assert a["system_prompt"] == "Du planst Stunden. Fassung 1."
    assert a["created_by"] == TEACHER2_PSEUDO
    assert a["name"] == "Mein Stundenassistent 1"
    assert a["subject_id"] is None


async def test_niemand_sonst_sieht_ihn(test_client, auth_headers_teacher2, auth_headers, vorlage):
    """Privat heißt: in der Liste der Erstellerin, in keiner anderen — auch nicht bei einem Admin."""
    eigener = (await _anlegen(test_client, auth_headers_teacher2)).json()["id"]

    def ids(resp):
        return {a["id"] for a in resp.json()["items"]}

    assert eigener in ids(await test_client.get("/assistants", headers=auth_headers_teacher2))
    andere = await test_client.get("/assistants", headers=auth_headers)
    assert vorlage in ids(andere)
    assert eigener not in ids(andere)


async def test_kopiert_den_aktuellen_prompt(test_client, auth_headers_teacher2, auth_headers, vorlage):
    """Nach einer Änderung im Editor die neue Fassung — die erste Kopie bleibt, wie sie war."""
    erste = (await _anlegen(test_client, auth_headers_teacher2)).json()

    resp = await test_client.patch(f"/assistants/{vorlage}", headers=auth_headers,
                                   json={"system_prompt": "Du planst Stunden. Fassung 2."})
    assert resp.status_code == 200, resp.text

    zweite = (await _anlegen(test_client, auth_headers_teacher2)).json()
    assert zweite["system_prompt"] == "Du planst Stunden. Fassung 2."
    assert zweite["name"] == "Mein Stundenassistent 2"
    erste_jetzt = (await test_client.get(f"/assistants/{erste['id']}", headers=auth_headers_teacher2)).json()
    assert erste_jetzt["system_prompt"] == "Du planst Stunden. Fassung 1."


async def test_speichern_im_editor_behaelt_die_faehigkeit(test_client, auth_headers_teacher2, vorlage):
    """Plan 1a.2: Die Lehrkraft schickt `tool_groups` nicht mit — die Fähigkeit bleibt."""
    a = (await _anlegen(test_client, auth_headers_teacher2)).json()
    # So speichert der Editor einer Lehrkraft: alle Felder außer `tool_groups`, `image_kinds`,
    # `sort_order` (`AssistantEditor.svelte`, `buildPayload`).
    resp = await test_client.patch(f"/assistants/{a['id']}", headers=auth_headers_teacher2, json={
        "name": "Chemie-Stunden", "description": None, "subject_id": None,
        "system_prompt": a["system_prompt"] + "\n\nMeine Phasen: Einstieg, Erarbeitung, Sicherung.",
        "model": a["model"], "temperature": None, "max_tokens": None,
        "audience": "teacher", "scope": "private", "scope_group_id": None,
        "min_grade": None, "max_grade": None, "tags": [],
        "available_from": None, "available_until": None, "disabled_augmentations": [],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["tool_groups"] == ["lesson_planning"]
    assert resp.json()["status"] == "active"


async def test_umbenannte_zaehlen_nicht(test_client, auth_headers_teacher2, vorlage):
    a = (await _anlegen(test_client, auth_headers_teacher2)).json()
    await test_client.patch(f"/assistants/{a['id']}", headers=auth_headers_teacher2, json={"name": "Chemie"})
    assert (await _anlegen(test_client, auth_headers_teacher2)).json()["name"] == "Mein Stundenassistent 1"


async def test_fach_aus_der_entwurfsansicht(test_client, auth_headers_teacher2, vorlage, fach):
    """Aus einer Stunde heraus angelegt, trägt die Kopie deren Fach — änderbar im Editor."""
    resp = await test_client.post("/assistants/eigener-stundenassistent",
                                  headers=auth_headers_teacher2, json={"subject_id": fach})
    assert resp.status_code == 201, resp.text
    assert resp.json()["subject_id"] == fach


async def test_unbekanntes_fach(test_client, auth_headers_teacher2, vorlage):
    resp = await test_client.post("/assistants/eigener-stundenassistent",
                                  headers=auth_headers_teacher2, json={"subject_id": 987654})
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("wer", ["lehrkraft", "admin"])
async def test_die_kopie_laesst_sich_loeschen(test_client, auth_headers_teacher2, auth_headers, vorlage, wer):
    """Aktiv und privat — löschbar, auch für einen Admin (Rollenmodell: dort eine Lehrkraft)."""
    headers = auth_headers_teacher2 if wer == "lehrkraft" else auth_headers
    a = (await _anlegen(test_client, headers)).json()
    resp = await test_client.delete(f"/assistants/{a['id']}", headers=headers)
    assert resp.status_code == 204, resp.text


async def test_schuelerin_darf_nicht(test_client, auth_headers_student, vorlage):
    resp = await _anlegen(test_client, auth_headers_student)
    assert resp.status_code == 403, resp.text


async def test_ohne_schulweiten_ein_verstaendlicher_fehler(test_client, auth_headers_teacher2, ohne_vorlage):
    resp = await _anlegen(test_client, auth_headers_teacher2)
    assert resp.status_code == 404, resp.text
    assert "kein schulweiter Stundenassistent" in resp.json()["detail"]
