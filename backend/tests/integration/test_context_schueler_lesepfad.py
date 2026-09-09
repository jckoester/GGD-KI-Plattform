"""Der Lesepfad des Kontextspeichers für Schüler:innen (AP4, ADR-019 F8).

Seit 09/2026 hängen `GET /context/nodes`, `…/neighborhood` und
`…/archived-references` an `get_current_user` statt an der Lehrkraft-Rolle. Was
sichtbar ist, entscheidet **allein** `read_scope_clause`
(`app/context/visibility.py`) — dieselbe Regel, die Suche und Detailansicht
benutzen.

Diese Tests halten die Regel an der Liste fest, je ein Fall pro Scope. Sie sind der
Ersatz für die Rollenschranke, die vorher hier stand: Fällt die Sichtbarkeitsregel
aus, öffnet sich der Lesepfad — und niemand merkt es an einem 403.
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, select, text

from app.db.models import ContextNode, Group, GroupMembership
from tests.integration.conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio

# Ein eigenes Fach, damit die Tests nicht am Bestand der Test-DB hängen.
FACH_NAME = "AP4-Testfach"


@pytest_asyncio.fixture
async def welt(async_engine):
    """Legt Knoten aller Scopes an und räumt hinterher auf.

    Bewusst **nicht** die transaktionale `db_session`: Der TestClient benutzt eine
    eigene Session; was in einer offenen Transaktion steckt, sieht er nicht.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    ids: dict[str, str] = {}
    async with factory() as s:
        # Fach
        res = await s.execute(text(
            "INSERT INTO subjects (name, slug) VALUES (:n, :sl) RETURNING id"
        ), {"n": FACH_NAME, "sl": "ap4-testfach"})
        fach_id = res.scalar_one()

        # Zwei Gruppen: in einer ist die Schülerin, in der anderen nicht.
        gruppen = {}
        for kuerzel, typ in (("meine", "teaching_group"), ("fremde", "teaching_group"),
                             ("fachschaft", "subject_department")):
            res = await s.execute(text(
                "INSERT INTO groups (name, slug, type, subject_id) "
                "VALUES (:n, :sl, :t, :f) RETURNING id"
            ), {"n": f"AP4 {kuerzel}", "sl": f"ap4-{kuerzel}", "t": typ, "f": fach_id})
            gruppen[kuerzel] = res.scalar_one()
        await s.execute(insert(GroupMembership).values(
            group_id=gruppen["meine"], pseudonym=STUDENT_PSEUDO, role_in_group="student"
        ))

        faelle = [
            ("school", dict(read_scope="school", owner_pseudonym=TEACHER1_PSEUDO)),
            ("global", dict(read_scope="global", owner_pseudonym=TEACHER1_PSEUDO)),
            # `subject` verlangt die Fachschaftsgruppe (CHECK
            # `check_context_nodes_read_group_id`) — auch wenn die Sichtbarkeitsregel
            # den Scope für alle Angemeldeten öffnet, ohne die Gruppe zu prüfen.
            ("subject", dict(read_scope="subject", owner_pseudonym=TEACHER1_PSEUDO,
                             read_scope_group_id=gruppen["fachschaft"])),
            ("fremd_privat", dict(read_scope="private", owner_pseudonym=TEACHER1_PSEUDO)),
            ("eigen_privat", dict(read_scope="private", owner_pseudonym=STUDENT_PSEUDO)),
            ("gruppe_meine", dict(read_scope="group", owner_pseudonym=TEACHER1_PSEUDO,
                                  read_scope_group_id=gruppen["meine"])),
            ("gruppe_fremde", dict(read_scope="group", owner_pseudonym=TEACHER1_PSEUDO,
                                   read_scope_group_id=gruppen["fremde"])),
        ]
        for name, felder in faelle:
            node = ContextNode(
                category="concept", content_type="begriff", title=f"AP4 {name}",
                content="Testinhalt", subject_id=fach_id, write_scope="private",
                **felder,
            )
            s.add(node)
            await s.flush()
            ids[name] = str(node.id)
        await s.commit()

    yield {"fach_id": fach_id, "ids": ids, "gruppen": gruppen}

    async with factory() as s:
        await s.execute(delete(ContextNode).where(
            ContextNode.id.in_(list(ids.values()))
        ))
        await s.execute(delete(GroupMembership).where(
            GroupMembership.group_id.in_(list(gruppen.values()))
        ))
        await s.execute(delete(Group).where(Group.id.in_(list(gruppen.values()))))
        await s.execute(text("DELETE FROM subjects WHERE slug = 'ap4-testfach'"))
        await s.commit()


async def _titel(client, headers, fach_id):
    resp = await client.get(f"/context/nodes?subject_id={fach_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return {n["title"] for n in resp.json()}


async def test_liste_ist_fuer_schueler_erreichbar(test_client, auth_headers_student, welt):
    """Vorher 403 — die Rollenschranke war der einzige Grund."""
    resp = await test_client.get(
        f"/context/nodes?subject_id={welt['fach_id']}", headers=auth_headers_student
    )
    assert resp.status_code == 200


async def test_offene_scopes_sind_sichtbar(test_client, auth_headers_student, welt):
    titel = await _titel(test_client, auth_headers_student, welt["fach_id"])
    assert {"AP4 school", "AP4 global", "AP4 subject"} <= titel


async def test_fremdes_privates_bleibt_verborgen(test_client, auth_headers_student, welt):
    titel = await _titel(test_client, auth_headers_student, welt["fach_id"])
    assert "AP4 fremd_privat" not in titel
    # Das eigene private sehr wohl — `owner_pseudonym` sticht den Scope.
    assert "AP4 eigen_privat" in titel


async def test_gruppenknoten_nur_bei_mitgliedschaft(test_client, auth_headers_student, welt):
    """Der Fall, der im Suchpfad einmal falsch war (Audit #1) und Inhalt ans Modell gab."""
    titel = await _titel(test_client, auth_headers_student, welt["fach_id"])
    assert "AP4 gruppe_meine" in titel
    assert "AP4 gruppe_fremde" not in titel


async def test_detail_und_nachbarschaft_folgen_derselben_regel(
    test_client, auth_headers_student, welt
):
    ids = welt["ids"]
    for name, erwartet in (("school", 200), ("fremd_privat", 403), ("gruppe_fremde", 403)):
        detail = await test_client.get(
            f"/context/nodes/{ids[name]}", headers=auth_headers_student
        )
        assert detail.status_code == erwartet, f"{name}: {detail.status_code}"

        nachbarn = await test_client.get(
            f"/context/nodes/{ids[name]}/neighborhood", headers=auth_headers_student
        )
        assert nachbarn.status_code == erwartet, f"{name}/neighborhood: {nachbarn.status_code}"


async def test_schreibpfade_bleiben_der_lehrkraft_vorbehalten(
    test_client, auth_headers_student, welt
):
    """Geöffnet wurde das **Lesen**. Anlegen und Ändern bleiben, wo sie waren."""
    anlegen = await test_client.post("/context/nodes", headers=auth_headers_student, json={
        "category": "concept", "content_type": "begriff", "title": "AP4 verboten",
    })
    assert anlegen.status_code == 403

    aendern = await test_client.patch(
        f"/context/nodes/{welt['ids']['school']}",
        headers=auth_headers_student, json={"title": "umbenannt"},
    )
    assert aendern.status_code == 403
