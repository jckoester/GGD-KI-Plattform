"""Begriffe einer Fachschaft: auf der Fachseite sichtbar, von der Fachschaft änderbar (0.15.2).

Zwei Fehler, die nur sah, wer nicht Admin ist — oder wer in den Tab schaute:

1. **„weiterer Kontext" zeigte keine Begriffe.** Der Fachfilter (`subject_slug`) ließ
   schulweite Knoten nur durch, wenn sie zur Kategorie `knowledge` gehörten; Begriffe
   und Stoffsteckbriefe stehen in `concept`.
2. **Die Fachschaft konnte ihre Begriffe nicht ändern.** Import und Editor vergeben
   `write_scope = subject`; die Rechteprüfung kannte nur `group`.

Router-Pfade ohne /api-Präfix (CLAUDE.md: FastAPI sieht /api nie).
"""
import uuid

import psycopg2
import pytest

FACHSCHAFT = "fs-lehrkraft-begriffe"
FREMDE = "fremde-lehrkraft-begriffe"
SCHUELERIN = "schuelerin-begriffe"


@pytest.fixture(scope="module")
def sync_conn(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield conn
    conn.close()


def _knoten(cur, *, category, content_type, title, subject_id, gruppe_id=None,
            write_scope="subject"):
    cur.execute(
        "INSERT INTO context_nodes (category, content_type, title, content, subject_id,"
        " status, read_scope, write_scope, write_scope_group_id)"
        " VALUES (%s,%s,%s,'Text',%s,'active','school',%s,%s) RETURNING id",
        (category, content_type, title, subject_id, write_scope, gruppe_id),
    )
    return str(cur.fetchone()[0])


@pytest.fixture(scope="module")
def bestand(sync_conn):
    """Zwei Fächer mit je einer Fachschaft; eine Lehrkraft in der ersten."""
    k = uuid.uuid4().hex[:8]
    with sync_conn.cursor() as cur:
        faecher, gruppen = [], []
        for name in ("Eigenfach", "Fremdfach"):
            cur.execute(
                "INSERT INTO subjects (slug, name, fach_code) VALUES (%s,%s,%s) RETURNING id",
                (f"{name.lower()}-{k}", name, f"{name[:2].upper()}{k[:4]}"),
            )
            fach_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO groups (name, slug, type, subject_id, sso_group_id)"
                " VALUES (%s,%s,'subject_department',%s,%s) RETURNING id",
                (f"FS {name} {k}", f"fs-{name.lower()}-{k}", fach_id, f"fs-{name.lower()}-{k}"),
            )
            faecher.append(fach_id)
            gruppen.append(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft)"
            " VALUES (%s,%s,'teacher','sso')",
            (gruppen[0], FACHSCHAFT),
        )
        ids = {
            "begriff": _knoten(cur, category="concept", content_type="begriff",
                               title=f"Eigenbegriff {k}", subject_id=faecher[0],
                               gruppe_id=gruppen[0]),
            "stoff": _knoten(cur, category="concept", content_type="stoffsteckbrief",
                             title=f"Eigenstoff {k}", subject_id=faecher[0],
                             gruppe_id=gruppen[0]),
            "fremd": _knoten(cur, category="concept", content_type="begriff",
                             title=f"Fremdbegriff {k}", subject_id=faecher[1],
                             gruppe_id=gruppen[1]),
            "fachlos_concept": _knoten(cur, category="concept", content_type="begriff",
                                       title=f"Fachloser Begriff {k}", subject_id=None,
                                       write_scope="school"),
            "fachlos_methode": _knoten(cur, category="knowledge", content_type="methode",
                                       title=f"Fachlose Methode {k}", subject_id=None,
                                       write_scope="school"),
        }
    sync_conn.commit()
    yield {"slug": f"eigenfach-{k}", "ids": ids, "k": k}
    with sync_conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE id = ANY(%s::uuid[])", (list(ids.values()),))
        cur.execute("DELETE FROM group_memberships WHERE group_id = ANY(%s)", (gruppen,))
        cur.execute("DELETE FROM groups WHERE id = ANY(%s)", (gruppen,))
        cur.execute("DELETE FROM subjects WHERE id = ANY(%s)", (faecher,))
    sync_conn.commit()


def _kopf(jwt_service, pseudonym, rollen, grade=None):
    token, _ = jwt_service.issue(pseudonym=pseudonym, roles=rollen, grade=grade)
    return {"Cookie": f"session={token}"}


# ── 1. Fachseite „weiterer Kontext" ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_fachseite_zeigt_begriffe_und_stoffsteckbriefe_des_fachs(test_client, jwt_service, bestand):
    antwort = await test_client.get(
        "/context/nodes",
        params={"subject_slug": bestand["slug"], "status": "active", "limit": 500},
        headers=_kopf(jwt_service, FREMDE, ["teacher"]),
    )
    assert antwort.status_code == 200
    ids = {n["id"] for n in antwort.json()}
    assert bestand["ids"]["begriff"] in ids
    assert bestand["ids"]["stoff"] in ids


@pytest.mark.asyncio
async def test_fachseite_ohne_fremde_und_fachlose_begriffe(test_client, jwt_service, bestand):
    """Fachlose bleiben auf `knowledge` beschränkt — sonst stünden sie in jedem Fach."""
    antwort = await test_client.get(
        "/context/nodes",
        params={"subject_slug": bestand["slug"], "status": "active", "limit": 500},
        headers=_kopf(jwt_service, FREMDE, ["teacher"]),
    )
    ids = {n["id"] for n in antwort.json()}
    assert bestand["ids"]["fremd"] not in ids
    assert bestand["ids"]["fachlos_concept"] not in ids
    assert bestand["ids"]["fachlos_methode"] in ids


# ── 2. Schreibrecht der Fachschaft ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_fachschaft_darf_ihre_begriffe_aendern(test_client, jwt_service, bestand):
    kopf = _kopf(jwt_service, FACHSCHAFT, ["teacher"])
    liste = await test_client.get(
        "/context/nodes",
        params={"subject_slug": bestand["slug"], "status": "active", "limit": 500},
        headers=kopf,
    )
    rechte = {n["id"]: n["darf_schreiben"] for n in liste.json()}
    assert rechte[bestand["ids"]["begriff"]] is True
    assert rechte[bestand["ids"]["fachlos_methode"]] is False

    neu = f"Eigenbegriff geändert {bestand['k']}"
    antwort = await test_client.patch(
        f"/context/nodes/{bestand['ids']['begriff']}", json={"title": neu}, headers=kopf
    )
    assert antwort.status_code == 200, antwort.text
    assert antwort.json()["title"] == neu


@pytest.mark.asyncio
async def test_fachschaft_darf_fremde_begriffe_nicht_aendern(test_client, jwt_service, bestand):
    kopf = _kopf(jwt_service, FACHSCHAFT, ["teacher"])
    antwort = await test_client.patch(
        f"/context/nodes/{bestand['ids']['fremd']}", json={"title": "x"}, headers=kopf
    )
    assert antwort.status_code == 403
    einzeln = await test_client.get(f"/context/nodes/{bestand['ids']['fremd']}", headers=kopf)
    assert einzeln.json()["darf_schreiben"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("pseudonym,rollen,grade", [
    (FREMDE, ["teacher"], None),            # Lehrkraft, nicht in der Fachschaft
    (FACHSCHAFT, ["student"], "8"),         # Mitgliedschaft ohne Lehrkraft-Rolle
    (SCHUELERIN, ["student"], "8"),
])
async def test_ohne_fachschaft_kein_schreibrecht(test_client, jwt_service, bestand,
                                                 pseudonym, rollen, grade):
    antwort = await test_client.patch(
        f"/context/nodes/{bestand['ids']['begriff']}", json={"title": "x"},
        headers=_kopf(jwt_service, pseudonym, rollen, grade),
    )
    assert antwort.status_code == 403
