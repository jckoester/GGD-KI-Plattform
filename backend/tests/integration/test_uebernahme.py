"""Artefakt → Baustein über die Schnittstelle (AP8, Schritt 1).

Was hier steht und nicht in den Unit-Tests: alles, was Zeilen braucht — die
Eigentümerprüfung, die Fassungskette mit `supersedes`, der erzwungene Scope bei
Schüler:innen und die Idempotenz beim zweiten identischen Übernehmen.
"""
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.artifacts import store
from app.db.models import ContextEdge, ContextNode
from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

SCHUELER_PSEUDO = "schueler-ap8-pseudo"


@pytest.fixture(autouse=True)
def artefakt_ablage(tmp_path, monkeypatch):
    """Artefakt-Bytes in ein Wegwerf-Verzeichnis, nicht in `backend/data/`."""
    monkeypatch.setattr(store.settings, "artifact_storage_dir", str(tmp_path))


@pytest.fixture
def schueler_headers(jwt_service):
    token, _ = jwt_service.issue(pseudonym=SCHUELER_PSEUDO, roles=["student"], grade="8")
    return {"Cookie": f"session={token}"}


@pytest_asyncio.fixture
async def dokument(db_session, auth_headers, test_client):
    """Ein Dokument in der Bibliothek von teacher1."""
    resp = await test_client.post(
        "/artifacts/document",
        json={"title": "Sätze am Kreis", "markdown": "# Sätze am Kreis\n\nThalessatz …"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _aufraeumen(db_session, node_ids):
    for nid in node_ids:
        await db_session.execute(sa.delete(ContextNode).where(ContextNode.id == nid))
    await db_session.commit()


class TestVorschlag:
    async def test_dokument_ist_uebernehmbar(self, test_client, auth_headers, dokument):
        resp = await test_client.get(
            f"/artifacts/{dokument['id']}/baustein", headers=auth_headers
        )
        assert resp.status_code == 200
        daten = resp.json()
        assert daten["uebernehmbar"] is True
        assert "arbeitsblatt" in daten["typen"]
        assert daten["scopes_erzwungen"] is None
        assert daten["vorhandener_baustein_id"] is None

    async def test_schueler_bekommt_erzwungene_sichtbarkeit(
        self, test_client, auth_headers, schueler_headers, dokument
    ):
        """Das Dokument gehört teacher1 — die Schüler:in darf es gar nicht erst sehen."""
        resp = await test_client.get(
            f"/artifacts/{dokument['id']}/baustein", headers=schueler_headers
        )
        assert resp.status_code == 403

    async def test_fremdes_artefakt_bleibt_verschlossen(
        self, test_client, auth_headers_teacher2, dokument
    ):
        resp = await test_client.get(
            f"/artifacts/{dokument['id']}/baustein", headers=auth_headers_teacher2
        )
        assert resp.status_code == 403


class TestUebernahme:
    async def test_dokument_wird_baustein(
        self, test_client, auth_headers, db_session, dokument
    ):
        resp = await test_client.post(
            f"/artifacts/{dokument['id']}/baustein",
            json={"content_type": "lerntext", "title": "Sätze am Kreis"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        daten = resp.json()
        assert daten["created"] is True
        assert daten["ersetzt_node_id"] is None

        node = await db_session.get(ContextNode, uuid.UUID(daten["node_id"]))
        assert node.content_type == "lerntext"
        assert node.owner_pseudonym == TEACHER1_PSEUDO
        assert node.content.startswith("# Sätze am Kreis")
        # Die Herkunft — sie füttert den Chip in „Meine Bausteine".
        assert node.metadata_["source_artifact_id"] == dokument["id"]
        await _aufraeumen(db_session, [node.id])

    async def test_zweimal_dasselbe_erzeugt_keine_zweite_fassung(
        self, test_client, auth_headers, db_session, dokument
    ):
        nutzlast = {"content_type": "lerntext", "title": "Sätze am Kreis"}
        erst = await test_client.post(
            f"/artifacts/{dokument['id']}/baustein", json=nutzlast, headers=auth_headers
        )
        zweit = await test_client.post(
            f"/artifacts/{dokument['id']}/baustein", json=nutzlast, headers=auth_headers
        )
        assert zweit.status_code == 201
        assert zweit.json()["node_id"] == erst.json()["node_id"]
        assert zweit.json()["created"] is False
        await _aufraeumen(db_session, [uuid.UUID(erst.json()["node_id"])])

    async def test_geaenderter_titel_erzeugt_eine_fassung_mit_supersedes(
        self, test_client, auth_headers, db_session, dokument
    ):
        """Der Kern der Entscheidung: neue Fassung statt Zweitknoten.

        Der alte Baustein wandert ins Archiv und bleibt über `supersedes` erreichbar —
        genau die Kante, die `GET /nodes/{id}/archived-references` als Nachfolger
        vorschlägt. Ein In-place-Überschreiben nähme dieser Mechanik ihre Grundlage.
        """
        erst = await test_client.post(
            f"/artifacts/{dokument['id']}/baustein",
            json={"content_type": "lerntext", "title": "Sätze am Kreis"},
            headers=auth_headers,
        )
        alt_id = uuid.UUID(erst.json()["node_id"])

        zweit = await test_client.post(
            f"/artifacts/{dokument['id']}/baustein",
            json={"content_type": "lerntext", "title": "Satzgruppe am Kreis"},
            headers=auth_headers,
        )
        assert zweit.status_code == 201
        neu_id = uuid.UUID(zweit.json()["node_id"])
        assert neu_id != alt_id
        assert zweit.json()["ersetzt_node_id"] == str(alt_id)

        db_session.expire_all()
        alt = await db_session.get(ContextNode, alt_id)
        assert alt.status == "archived"
        assert alt.archived_at is not None, "ohne archived_at fasst der Löschlauf ihn nie an"

        kante = await db_session.execute(
            sa.select(ContextEdge).where(
                ContextEdge.from_node_id == neu_id,
                ContextEdge.to_node_id == alt_id,
                ContextEdge.relation == "supersedes",
            )
        )
        assert kante.scalar_one_or_none() is not None
        await _aufraeumen(db_session, [neu_id, alt_id])

    async def test_planungsobjekt_wird_abgewiesen(
        self, test_client, auth_headers, dokument
    ):
        resp = await test_client.post(
            f"/artifacts/{dokument['id']}/baustein",
            json={"content_type": "unterrichtsstunde"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_fremdes_artefakt_laesst_sich_nicht_uebernehmen(
        self, test_client, auth_headers_teacher2, dokument
    ):
        resp = await test_client.post(
            f"/artifacts/{dokument['id']}/baustein",
            json={"content_type": "lerntext"},
            headers=auth_headers_teacher2,
        )
        assert resp.status_code == 403
        assert TEACHER2_PSEUDO  # nur zur Dokumentation, wer hier klopft

    async def test_sichtbarkeit_ohne_traegergruppe_wird_abgewiesen(
        self, test_client, auth_headers, db_session, dokument
    ):
        """Dieselbe Prüfung wie beim Anlegen eines Knotens, nicht eine zweite Meinung.

        `read_scope: group` ohne Gruppe kann die Datenbank gar nicht speichern — ohne
        `pruefe_scopes` käme statt einer Meldung ein Constraint-Fehler als 500 zurück.
        """
        resp = await test_client.post(
            f"/artifacts/{dokument['id']}/baustein",
            json={"content_type": "arbeitsblatt", "read_scope": "group"},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        # Und nichts ist hängen geblieben.
        offen = await db_session.execute(
            sa.select(sa.func.count())
            .select_from(ContextNode)
            .where(
                ContextNode.metadata_["source_artifact_id"].astext == dokument["id"]
            )
        )
        assert offen.scalar_one() == 0


class TestSchuelerUebernahme:
    """Der eigentliche Zweck von AP8: Schüler:innen bekommen ihre vier Bausteinarten."""

    @pytest_asyncio.fixture
    async def schueler_dokument(self, test_client, schueler_headers):
        resp = await test_client.post(
            "/artifacts/document",
            json={"title": "Mein Lernplan", "markdown": "- Woche 1: Vokabeln"},
            headers=schueler_headers,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    async def test_vorschlag_nennt_nur_die_vier_arten(
        self, test_client, schueler_headers, schueler_dokument
    ):
        resp = await test_client.get(
            f"/artifacts/{schueler_dokument['id']}/baustein", headers=schueler_headers
        )
        assert resp.status_code == 200
        daten = resp.json()
        assert set(daten["typen"]) == {
            "schuelertext", "lernplan", "schuelerpraesentation", "strukturierung",
        }
        assert daten["scopes_erzwungen"] == ["private", "private"]

    async def test_scope_wird_erzwungen_und_nicht_geglaubt(
        self, test_client, schueler_headers, db_session, schueler_dokument
    ):
        """Der Client darf `school` schicken — der Server macht trotzdem `private`.

        Das ist der Unterschied zwischen einem Formular ohne Feld und einer Zusage:
        Nur die serverseitige Klammer hält auch dann, wenn jemand am Formular vorbeigeht.
        """
        resp = await test_client.post(
            f"/artifacts/{schueler_dokument['id']}/baustein",
            json={
                "content_type": "lernplan",
                "read_scope": "school",
                "write_scope": "school",
            },
            headers=schueler_headers,
        )
        assert resp.status_code == 201, resp.text
        node = await db_session.get(ContextNode, uuid.UUID(resp.json()["node_id"]))
        assert (node.read_scope, node.write_scope) == ("private", "private")
        assert node.owner_pseudonym == SCHUELER_PSEUDO
        await _aufraeumen(db_session, [node.id])

    async def test_lehrkraft_arten_bleiben_verschlossen(
        self, test_client, schueler_headers, schueler_dokument
    ):
        resp = await test_client.post(
            f"/artifacts/{schueler_dokument['id']}/baustein",
            json={"content_type": "klausur"},
            headers=schueler_headers,
        )
        assert resp.status_code == 422


class TestMermaid:
    async def test_mermaid_wird_als_diagramm_uebernommen(
        self, test_client, auth_headers, db_session
    ):
        """Der Zaun muss mit: Sonst steht in der Knotenansicht Code statt eines Bildes."""
        gespeichert = await test_client.post(
            "/artifacts/from-diagram",
            json={
                "kind": "mermaid",
                "source": "graph TD; A[Start]-->B[Ende];",
                "svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                "title": "Ablauf",
            },
            headers=auth_headers,
        )
        assert gespeichert.status_code == 200, gespeichert.text

        resp = await test_client.post(
            f"/artifacts/{gespeichert.json()['id']}/baustein",
            json={"content_type": "strukturierung", "title": "Ablauf"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        node = await db_session.get(ContextNode, uuid.UUID(resp.json()["node_id"]))
        assert node.content.startswith("```mermaid")
        await _aufraeumen(db_session, [node.id])

    async def test_bild_wird_abgewiesen(self, test_client, auth_headers, db_session):
        """Ein Bildknoten trüge außer dem Titel nichts — die Bibliothek ist sein Ort."""
        artefakt = await store.save_artifact(
            db_session,
            owner_pseudonym=TEACHER1_PSEUDO,
            roles=["teacher"],
            grade=None,
            kind="image",
            mime_type="image/png",
            data=b"PNG",
            title="Würfel",
            source="ein roter Würfel",
        )
        resp = await test_client.get(
            f"/artifacts/{artefakt.id}/baustein", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["uebernehmbar"] is False
        assert "Mermaid" in resp.json()["grund"]

        abgelehnt = await test_client.post(
            f"/artifacts/{artefakt.id}/baustein",
            json={"content_type": "lerntext"},
            headers=auth_headers,
        )
        assert abgelehnt.status_code == 422
