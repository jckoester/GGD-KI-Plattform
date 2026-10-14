"""Fachbegriffe in jedes Fach — der Admin-Weg (0.15.2, Admin-Seite `/settings/fachbegriffe`).

Bis 0.15.1 übersprang der Import jede Datei eines Fachs ohne Fachschaftsgruppe — auch für
Admins. Auf Dev hatten Biologie, Physik und BNT keine; Begriffe, die NwT aus diesen
Fächern braucht, ließen sich so gar nicht einspielen. Jetzt:

- Ein **Admin** spielt auch ohne Fachschaft ein; die Einträge ändern dann vorerst nur
  Admins (`write_scope = private`, ohne Eigentümer).
- Eine **Lehrkraft** kommt ohne Fachschaft weiterhin nicht durch (403).
- Gibt es die Fachschaft später, hängt ein **erneuter Import** die Knoten an sie — auch
  wenn sich die Datei nicht geändert hat.
- Auf der Admin-Seite kommt **das Fach aus der Datei** (`fach_aus_datei`): Ein Lauf darf
  mehrere Fächer enthalten; das gewählte Fach ist nur die Vorgabe für Dateien ohne
  `fach:`, ohne Vorgabe werden sie übersprungen. Die Fachseite bleibt gebunden.

Router-Pfade ohne /api-Präfix (CLAUDE.md: FastAPI sieht /api nie).
"""
import uuid

import psycopg2
import pytest

PFAD = "/context/fachbegriffe/import"
ADMIN = "admin-fachbegriffe"
LEHRKRAFT = "lehrkraft-fachbegriffe"


def _md(titel: str, fach: str | None = None, zusatz: str = "") -> bytes:
    kopf = f"fach: {fach}\n" if fach else ""
    return (
        f"---\nknotentyp: begriff\ntitel: {titel}\n{kopf}{zusatz}---\n\n"
        f"Ein Text über {titel}.\n"
    ).encode("utf-8")


def _datei(name: str, inhalt: bytes):
    return ("dateien", (name, inhalt, "application/octet-stream"))


def _kopf(jwt_service, pseudonym, rollen):
    token, _ = jwt_service.issue(pseudonym=pseudonym, roles=rollen, grade=None)
    return {"Cookie": f"session={token}"}


@pytest.fixture
def sync_conn(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield conn
    conn.close()


@pytest.fixture
def ohne_fachschaft(sync_conn):
    """Ein Fach ohne Fachschaftsgruppe — je Test neu, weil ein Test eine anlegt."""
    k = uuid.uuid4().hex[:8]
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO subjects (slug, name, fach_code) VALUES (%s,%s,%s) RETURNING id",
            (f"ohnefach-{k}", f"Ohnefach {k}", f"OF{k[:4]}"),
        )
        fach_id = cur.fetchone()[0]
    sync_conn.commit()
    yield {"id": fach_id, "slug": f"ohnefach-{k}", "k": k}
    with sync_conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE subject_id = %s", (fach_id,))
        cur.execute("DELETE FROM group_memberships WHERE group_id IN"
                    " (SELECT id FROM groups WHERE subject_id = %s)", (fach_id,))
        cur.execute("DELETE FROM groups WHERE subject_id = %s", (fach_id,))
        cur.execute("DELETE FROM subjects WHERE id = %s", (fach_id,))
    sync_conn.commit()


def _knoten(sync_conn, fach_id):
    with sync_conn.cursor() as cur:
        cur.execute(
            "SELECT id, write_scope, write_scope_group_id, owner_pseudonym, read_scope"
            " FROM context_nodes WHERE subject_id = %s", (fach_id,),
        )
        return cur.fetchall()


async def _importiere(test_client, kopf, fach, dateien, probelauf=False, aus_datei=False):
    params = {"probelauf": str(probelauf).lower()}
    if fach:
        params["fach"] = fach
    if aus_datei:
        params["fach_aus_datei"] = "true"
    return await test_client.post(PFAD, params=params, files=dateien, headers=kopf)


@pytest.fixture
def mit_fachschaft(sync_conn):
    """Ein zweites Fach, diesmal mit Fachschaftsgruppe."""
    k = uuid.uuid4().hex[:8]
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO subjects (slug, name, fach_code) VALUES (%s,%s,%s) RETURNING id",
            (f"mitfach-{k}", f"Mitfach {k}", f"MF{k[:4]}"),
        )
        fach_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO groups (name, slug, type, subject_id, sso_group_id)"
            " VALUES (%s,%s,'subject_department',%s,%s) RETURNING id",
            (f"FS Mitfach {k}", f"fs-mitfach-{k}", fach_id, f"fs-mitfach-{k}"),
        )
        gruppe_id = cur.fetchone()[0]
    sync_conn.commit()
    yield {"id": fach_id, "slug": f"mitfach-{k}", "name": f"Mitfach {k}", "gruppe": gruppe_id}
    with sync_conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE subject_id = %s", (fach_id,))
        cur.execute("DELETE FROM groups WHERE id = %s", (gruppe_id,))
        cur.execute("DELETE FROM subjects WHERE id = %s", (fach_id,))
    sync_conn.commit()


@pytest.mark.asyncio
async def test_admin_spielt_ohne_fachschaft_ein(test_client, jwt_service, sync_conn, ohne_fachschaft):
    antwort = await _importiere(
        test_client, _kopf(jwt_service, ADMIN, ["teacher", "admin"]), ohne_fachschaft["slug"],
        [_datei("Fotosynthese.md", _md("Fotosynthese"))],
    )
    assert antwort.status_code == 200, antwort.text
    bericht = antwort.json()
    assert bericht["neu"] == 1
    assert any("keine Fachschaftsgruppe" in w for w in bericht["warnungen"])

    [(knoten_id, write_scope, gruppe, owner, read_scope)] = _knoten(sync_conn, ohne_fachschaft["id"])
    assert (write_scope, gruppe, owner, read_scope) == ("private", None, None, "school")


@pytest.mark.asyncio
async def test_nur_admins_aendern_dann(test_client, jwt_service, sync_conn, ohne_fachschaft):
    await _importiere(
        test_client, _kopf(jwt_service, ADMIN, ["teacher", "admin"]), ohne_fachschaft["slug"],
        [_datei("Zelle.md", _md("Zelle"))],
    )
    [(knoten_id, *_)] = _knoten(sync_conn, ohne_fachschaft["id"])
    lehrkraft = await test_client.patch(
        f"/context/nodes/{knoten_id}", json={"title": "x"},
        headers=_kopf(jwt_service, LEHRKRAFT, ["teacher"]),
    )
    assert lehrkraft.status_code == 403
    admin = await test_client.patch(
        f"/context/nodes/{knoten_id}", json={"title": "Zelle (neu)"},
        headers=_kopf(jwt_service, ADMIN, ["teacher", "admin"]),
    )
    assert admin.status_code == 200


@pytest.mark.asyncio
async def test_lehrkraft_ohne_fachschaft_bleibt_draussen(test_client, jwt_service, sync_conn, ohne_fachschaft):
    antwort = await _importiere(
        test_client, _kopf(jwt_service, LEHRKRAFT, ["teacher"]), ohne_fachschaft["slug"],
        [_datei("Zelle.md", _md("Zelle"))],
    )
    assert antwort.status_code == 403
    assert _knoten(sync_conn, ohne_fachschaft["id"]) == []


@pytest.mark.asyncio
async def test_fremdes_fach_in_der_datei_bleibt_uebersprungen(test_client, jwt_service, sync_conn, ohne_fachschaft):
    """Auch für Admins: Was die Datei nennt, wird nicht stillschweigend umgehängt.

    ⚠️ Das andere Fach hat **keine** Fachschaft — mit Absicht. Für Admins ist das seit
    0.15.2 kein Grund mehr zum Überspringen; fehlte die Bindung an das gewählte Fach,
    entstünde der Knoten also dort. Genau das muss die Gegenprobe sehen können.
    """
    k = ohne_fachschaft["k"]
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO subjects (slug, name, fach_code) VALUES (%s,%s,%s) RETURNING id",
            (f"anderes-{k}", f"Anderes {k}", f"AF{k[:4]}"),
        )
        anderes_id = cur.fetchone()[0]
    sync_conn.commit()
    try:
        antwort = await _importiere(
            test_client, _kopf(jwt_service, ADMIN, ["teacher", "admin"]), ohne_fachschaft["slug"],
            [_datei("Fremd.md", _md("Fremd", fach=f"anderes-{k}"))],
        )
        assert antwort.status_code == 200
        assert antwort.json()["neu"] == 0
        assert any("importiert wird nach" in w for w in antwort.json()["warnungen"])
        assert _knoten(sync_conn, ohne_fachschaft["id"]) == []
        assert _knoten(sync_conn, anderes_id) == []
    finally:
        with sync_conn.cursor() as cur:
            cur.execute("DELETE FROM context_nodes WHERE subject_id = %s", (anderes_id,))
            cur.execute("DELETE FROM subjects WHERE id = %s", (anderes_id,))
        sync_conn.commit()


@pytest.mark.asyncio
async def test_erneuter_import_haengt_an_die_neue_fachschaft(test_client, jwt_service, sync_conn, ohne_fachschaft):
    kopf = _kopf(jwt_service, ADMIN, ["teacher", "admin"])
    datei = [_datei("Atmung.md", _md("Atmung"))]
    await _importiere(test_client, kopf, ohne_fachschaft["slug"], datei)

    k = ohne_fachschaft["k"]
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO groups (name, slug, type, subject_id, sso_group_id)"
            " VALUES (%s,%s,'subject_department',%s,%s) RETURNING id",
            (f"FS Ohnefach {k}", f"fs-ohnefach-{k}", ohne_fachschaft["id"], f"fs-ohnefach-{k}"),
        )
        gruppe_id = cur.fetchone()[0]
    sync_conn.commit()

    # Dieselbe Datei, unverändert — der Zweig „unverändert" kehrt früh zurück.
    antwort = await _importiere(test_client, kopf, ohne_fachschaft["slug"], datei)
    assert antwort.json()["unveraendert"] == 1

    [(_, write_scope, gruppe, owner, _)] = _knoten(sync_conn, ohne_fachschaft["id"])
    assert (write_scope, gruppe, owner) == ("subject", gruppe_id, None)


# ── Fach aus der Datei (Admin-Seite) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_fach_aus_der_datei_ueber_mehrere_faecher(
    test_client, jwt_service, sync_conn, ohne_fachschaft, mit_fachschaft
):
    antwort = await _importiere(
        test_client, _kopf(jwt_service, ADMIN, ["teacher", "admin"]), None,
        [
            _datei("Fotosynthese.md", _md("Fotosynthese", fach=ohne_fachschaft["slug"])),
            _datei("Sensor.md", _md("Sensor", fach=mit_fachschaft["slug"])),
            _datei("Ohne.md", _md("Ohne")),
        ],
        aus_datei=True,
    )
    assert antwort.status_code == 200, antwort.text
    bericht = antwort.json()
    assert bericht["neu"] == 2
    # Die Vorschau führt Dateinamen ohne `.md` — so nennt sie auch `ueberschreiben`.
    zeilen = {z["datei"]: z for z in bericht["dateien"]}
    assert zeilen["Sensor"]["fach"] == mit_fachschaft["name"]
    assert zeilen["Ohne"]["zustand"] == "uebergangen"
    assert any("Ohne: keine Fachangabe" in w for w in bericht["warnungen"])

    [(_, ws_ohne, *_)] = _knoten(sync_conn, ohne_fachschaft["id"])
    [(_, ws_mit, gruppe, *_)] = _knoten(sync_conn, mit_fachschaft["id"])
    assert ws_ohne == "private"
    assert (ws_mit, gruppe) == ("subject", mit_fachschaft["gruppe"])


@pytest.mark.asyncio
async def test_gewaehltes_fach_ist_nur_vorgabe(
    test_client, jwt_service, sync_conn, ohne_fachschaft, mit_fachschaft
):
    """Ohne Angabe ins gewählte Fach — mit Angabe dorthin, wo die Datei es sagt."""
    antwort = await _importiere(
        test_client, _kopf(jwt_service, ADMIN, ["teacher", "admin"]), ohne_fachschaft["slug"],
        [
            _datei("Ohne.md", _md("Ohne")),
            _datei("Sensor.md", _md("Sensor", fach=mit_fachschaft["slug"])),
        ],
        aus_datei=True,
    )
    assert antwort.json()["neu"] == 2
    assert len(_knoten(sync_conn, ohne_fachschaft["id"])) == 1
    assert len(_knoten(sync_conn, mit_fachschaft["id"])) == 1


@pytest.mark.asyncio
async def test_verweis_ueber_die_fachgrenze_im_selben_lauf(
    test_client, jwt_service, sync_conn, ohne_fachschaft, mit_fachschaft
):
    """Verweise sucht der Lauf unter all seinen Dateien — auch über Fächer hinweg."""
    await _importiere(
        test_client, _kopf(jwt_service, ADMIN, ["teacher", "admin"]), None,
        [
            _datei("Fotosynthese.md", _md("Fotosynthese", fach=ohne_fachschaft["slug"])),
            _datei("Pflanzensensor.md", _md(
                "Pflanzensensor", fach=mit_fachschaft["slug"],
                zusatz='verwandt: ["[[Fotosynthese]]"]\n',
            )),
        ],
        aus_datei=True,
    )
    with sync_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM context_edges e"
            " JOIN context_nodes a ON a.id = e.from_node_id"
            " JOIN context_nodes b ON b.id = e.to_node_id"
            " WHERE a.subject_id = %s AND b.subject_id = %s AND e.relation = 'related_to'",
            (mit_fachschaft["id"], ohne_fachschaft["id"]),
        )
        assert cur.fetchone()[0] == 1


@pytest.mark.asyncio
async def test_fach_aus_der_datei_nur_fuer_admins(test_client, jwt_service, sync_conn, mit_fachschaft):
    antwort = await _importiere(
        test_client, _kopf(jwt_service, LEHRKRAFT, ["teacher"]), None,
        [_datei("Sensor.md", _md("Sensor", fach=mit_fachschaft["slug"]))],
        aus_datei=True,
    )
    assert antwort.status_code == 403
    assert _knoten(sync_conn, mit_fachschaft["id"]) == []


@pytest.mark.asyncio
async def test_ohne_fach_und_ohne_fach_aus_datei_422(test_client, jwt_service):
    antwort = await _importiere(
        test_client, _kopf(jwt_service, ADMIN, ["teacher", "admin"]), None,
        [_datei("Sensor.md", _md("Sensor"))],
    )
    assert antwort.status_code == 422
