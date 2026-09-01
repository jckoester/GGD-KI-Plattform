"""Integrationstests für KS-Phase-5 Schritt 1: chat_context_nodes API."""

import pytest
import pytest_asyncio
import psycopg2
from uuid import uuid4

# ── Fixtures ──────────────────────────────────────────────────────────────────

TEACHER1_PSEUDO = "teacher1-pseudo"
TEACHER2_PSEUDO = "teacher2-pseudo"


@pytest_asyncio.fixture
async def node(test_client, auth_headers):
    """Erstellt einen aktiven ContextNode über die API und gibt ihn zurück."""
    resp = await test_client.post(
        "/context/nodes",
        json={
            "category": "concept",
            "content_type": "funktion",
            "title": "Test-Knoten",
            "read_scope": "school",
            "write_scope": "private",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def archived_node(test_client, auth_headers):
    """Erstellt einen Knoten und archiviert ihn danach."""
    resp = await test_client.post(
        "/context/nodes",
        json={
            "category": "concept",
            "content_type": "funktion",
            "title": "Archivierter Knoten",
            "read_scope": "school",
            "write_scope": "private",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]
    patch = await test_client.patch(
        f"/context/nodes/{node_id}",
        json={"status": "archived"},
        headers=auth_headers,
    )
    assert patch.status_code == 200
    return resp.json()


@pytest_asyncio.fixture
async def private_node_other_user(test_client, auth_headers_teacher2):
    """Erstellt einen privaten Knoten als teacher2."""
    resp = await test_client.post(
        "/context/nodes",
        json={
            "category": "concept",
            "content_type": "funktion",
            "title": "Fremder privater Knoten",
            "read_scope": "private",
            "write_scope": "private",
        },
        headers=auth_headers_teacher2,
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def conversation(db_url, run_migrations):
    """Erstellt eine Konversation für teacher1 via psycopg2 (committed)
    und räumt nach dem Test auf."""
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conv_id = str(uuid4())
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversations (id, pseudonym, model_used, title)
            VALUES (%s, %s, 'gpt-4o', 'Test-Konversation')
            """,
            (conv_id, TEACHER1_PSEUDO),
        )
    conn.commit()
    conn.close()

    yield conv_id

    # Cleanup
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE id = %s", (conv_id,))
    conn.commit()
    conn.close()


# ── Tests ────────────────────────────────────────────────────────────────────


def _als_liste(umschlag: dict) -> list[dict]:
    """Den Ergebnisumschlag in Lesereihenfolge flach machen.

    ``/context/search`` liefert seit ADR-017 getrennte Abschnitte statt einer Liste.
    Was diese Tests prüfen — Feldbestand und Reihenfolge —, gilt über die Abschnitte
    hinweg: Namensträger stehen vor den nächstliegenden Bausteinen.
    """
    return [
        *umschlag["identifikation"]["treffer"],
        *umschlag["thematisch"]["treffer"],
    ]


class TestChatContextNodes:
    """Testsuite für /api/context/conversations/{id}/nodes Endpunkte."""

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # GET /api/context/conversations/{id}/nodes
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def test_get_empty_conversation(self, test_client, auth_headers, conversation):
        """Test 1: GET leere Konversation → leere Liste."""
        response = await test_client.get(
            f"/context/conversations/{conversation}/nodes",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_after_post(self, test_client, auth_headers, conversation, node):
        """Test 4: GET nach POST enthält den Knoten."""
        await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers,
        )
        response = await test_client.get(
            f"/context/conversations/{conversation}/nodes",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["node_id"] == node["id"]
        assert data[0]["title"] == node["title"]

    async def test_get_other_users_conversation(
        self, test_client, auth_headers_teacher2, conversation
    ):
        """Test 8: GET fremde Konversation → 403."""
        response = await test_client.get(
            f"/context/conversations/{conversation}/nodes",
            headers=auth_headers_teacher2,
        )
        assert response.status_code == 403

    async def test_get_nonexistent_conversation(self, test_client, auth_headers):
        """GET nicht existierende Konversation → 404."""
        response = await test_client.get(
            f"/context/conversations/{uuid4()}/nodes",
            headers=auth_headers,
        )
        assert response.status_code == 404

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # POST /api/context/conversations/{id}/nodes
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def test_post_valid_node(self, test_client, auth_headers, conversation, node):
        """Test 2: POST gültiger Knoten → 201 mit ChatContextNodeRead."""
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["node_id"] == node["id"]
        assert data["title"] == node["title"]
        assert data["content_type"] == node["content_type"]
        assert "added_at" in data

    async def test_post_idempotent(self, test_client, auth_headers, conversation, node):
        """Test 3: POST nochmals (idempotent) → 201, selbes added_at."""
        r1 = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers,
        )
        assert r1.status_code == 201

        r2 = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers,
        )
        assert r2.status_code == 201
        assert r1.json()["added_at"] == r2.json()["added_at"]

    async def test_post_nonexistent_node(self, test_client, auth_headers, conversation):
        """Test 6: POST nicht-existenter Knoten → 404."""
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": str(uuid4())},
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_post_archived_node(
        self, test_client, auth_headers, conversation, archived_node
    ):
        """Test 7: POST archivierter Knoten → 404."""
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": archived_node["id"]},
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_post_other_users_conversation(
        self, test_client, auth_headers_teacher2, conversation, node
    ):
        """Test 9: POST fremde Konversation → 403."""
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers_teacher2,
        )
        assert response.status_code == 403

    async def test_post_private_node_other_user(
        self, test_client, auth_headers, conversation, private_node_other_user
    ):
        """POST fremder privater Knoten → 403."""
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": private_node_other_user["id"]},
            headers=auth_headers,
        )
        assert response.status_code == 403

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DELETE /api/context/conversations/{id}/nodes/{node_id}
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def test_delete_node(self, test_client, auth_headers, conversation, node):
        """Test 5: DELETE → 204, Knoten danach nicht mehr in GET."""
        await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers,
        )
        response = await test_client.delete(
            f"/context/conversations/{conversation}/nodes/{node['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        get_resp = await test_client.get(
            f"/context/conversations/{conversation}/nodes",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json() == []

    async def test_delete_nonexistent_entry(
        self, test_client, auth_headers, conversation, node
    ):
        """DELETE nicht existierender Eintrag → 404."""
        response = await test_client.delete(
            f"/context/conversations/{conversation}/nodes/{node['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_delete_other_users_conversation(
        self, test_client, auth_headers_teacher2, conversation, node
    ):
        """Test 10: DELETE fremde Konversation → 403."""
        response = await test_client.delete(
            f"/context/conversations/{conversation}/nodes/{node['id']}",
            headers=auth_headers_teacher2,
        )
        assert response.status_code == 403

    async def test_delete_nonexistent_conversation(
        self, test_client, auth_headers, node
    ):
        """DELETE mit nicht existierender Konversation → 404."""
        response = await test_client.delete(
            f"/context/conversations/{uuid4()}/nodes/{node['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestEinordnendeFelder:
    """Fach, Fassung und Nummer reisen mit — sonst kann die Oberflaeche nicht einordnen.

    Ohne Fach ist eine BP-Kompetenz in einer Liste nicht zu bestimmen: `2.1.1`
    gibt es in 24 Faechern, und der Knotentyp steht ohnehin schon in der Nummer.
    """

    @pytest_asyncio.fixture
    async def bp_knoten(self, test_client, auth_headers, db_url):
        """IK-Kompetenz mit Fach, Fassung und Nummer — wie sie der Import anlegt."""
        resp = await test_client.post(
            "/context/nodes",
            json={
                "category": "knowledge",
                "content_type": "ik_kompetenz",
                "title": "Zahlen und Operationen",
                "read_scope": "school",
                "write_scope": "private",
                "metadata": {"kompetenz_nr": "3.1.1(1)", "bp_version": "2016.V3"},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        node = resp.json()

        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute(
                # fach_code bleibt NULL: Die Spalte ist schulweit eindeutig,
                # und diese Fixture committet — ein Kuerzel wuerde andere Tests brechen.
                "INSERT INTO subjects (id, slug, name) VALUES "
                "(9501, 'mathe-anzeige', 'Mathematik') ON CONFLICT (id) DO NOTHING"
            )
            cur.execute(
                "UPDATE context_nodes SET subject_id = 9501, bp_version = '2016.V3' "
                "WHERE id = %s",
                (node["id"],),
            )
        conn.commit()
        conn.close()
        return node

    async def test_post_liefert_fach_fassung_und_nummer(
        self, test_client, auth_headers, conversation, bp_knoten
    ):
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": bp_knoten["id"]},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["subject_id"] == 9501
        assert data["bp_version"] == "2016.V3"
        assert data["nr"] == "3.1.1(1)"

    async def test_get_liefert_dieselben_felder(
        self, test_client, auth_headers, conversation, bp_knoten
    ):
        await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": bp_knoten["id"]},
            headers=auth_headers,
        )
        response = await test_client.get(
            f"/context/conversations/{conversation}/nodes",
            headers=auth_headers,
        )
        assert response.status_code == 200
        eintrag = response.json()[0]
        assert eintrag["subject_id"] == 9501
        assert eintrag["bp_version"] == "2016.V3"
        assert eintrag["nr"] == "3.1.1(1)"

    async def test_erneutes_anheften_liefert_die_felder_ebenfalls(
        self, test_client, auth_headers, conversation, bp_knoten
    ):
        """Der Zweig fuer den bereits angehefteten Knoten baut die Antwort selbst."""
        for _ in range(2):
            response = await test_client.post(
                f"/context/conversations/{conversation}/nodes",
                json={"node_id": bp_knoten["id"]},
                headers=auth_headers,
            )
        assert response.json()["subject_id"] == 9501
        assert response.json()["nr"] == "3.1.1(1)"

    async def test_knoten_ohne_bildungsplanbezug_bleibt_leer(
        self, test_client, auth_headers, conversation, node
    ):
        """Nutzerknoten haben kein Fach und keine Nummer — dann eben `null`."""
        response = await test_client.post(
            f"/context/conversations/{conversation}/nodes",
            json={"node_id": node["id"]},
            headers=auth_headers,
        )
        data = response.json()
        assert data["subject_id"] is None
        assert data["bp_version"] is None
        assert data["nr"] is None
        # Der Knotentyp bleibt die Einordnung, wo es kein Fach gibt.
        assert data["content_type"] == "funktion"


class TestSuchergebnisFelder:
    """`/context/search` speist die Vorschlagsliste und den SSE-Kanal im Chat.

    Der Endpunkt hat **zwei** Pfade: die Embedding-Suche liefert Row-Mappings aus
    rohem SQL, der ILIKE-Fallback ORM-Objekte. Am ORM-Objekt heisst die JSON-Spalte
    `metadata_` — `metadata` waere dort die SQLAlchemy-MetaData. Beide Pfade muessen
    dieselben einordnenden Felder tragen, deshalb wird jeder einzeln geprueft.
    """

    @pytest_asyncio.fixture
    async def bp_knoten(self, test_client, auth_headers, db_url):
        resp = await test_client.post(
            "/context/nodes",
            json={
                "category": "knowledge",
                "content_type": "ik_kompetenz",
                "title": "Bruchrechnung im Suchtest",
                "read_scope": "school",
                "write_scope": "school",
                "metadata": {"kompetenz_nr": "3.1.2(4)", "bp_version": "2016.V2"},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        node = resp.json()

        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO subjects (id, slug, name) VALUES "
                "(9502, 'mathe-suche', 'Mathematik') ON CONFLICT (id) DO NOTHING"
            )
            cur.execute(
                "UPDATE context_nodes SET subject_id = 9502, bp_version = '2016.V2' "
                "WHERE id = %s",
                (node["id"],),
            )
        conn.commit()
        conn.close()
        return node

    def _treffer(self, umschlag, node):
        return next(t for t in _als_liste(umschlag) if t["node_id"] == node["id"])

    async def test_ilike_fallback_traegt_die_felder(
        self, test_client, auth_headers, bp_knoten
    ):
        """Ohne erreichbaren Embedding-Dienst faellt die Suche auf ILIKE zurueck."""
        from unittest.mock import AsyncMock, patch

        with patch(
            "app.context.search.generate_embedding",
            new=AsyncMock(side_effect=RuntimeError("kein Embedding-Dienst")),
        ):
            response = await test_client.post(
                "/context/search",
                json={"query": "Bruchrechnung im Suchtest"},
                headers=auth_headers,
            )
        assert response.status_code == 200, response.text
        treffer = self._treffer(response.json(), bp_knoten)
        assert treffer["subject_id"] == 9502
        assert treffer["bp_version"] == "2016.V2"
        assert treffer["nr"] == "3.1.2(4)"

    async def test_embedding_pfad_traegt_dieselben_felder(
        self, test_client, auth_headers, db_url, bp_knoten
    ):
        from unittest.mock import AsyncMock, patch

        from app.config import settings

        vec = [0.0] * settings.embedding_dimensions
        vec[0] = 1.0
        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE context_nodes SET embedding = %s::vector WHERE id = %s",
                ("[" + ",".join(str(v) for v in vec) + "]", bp_knoten["id"]),
            )
        conn.commit()
        conn.close()

        with patch("app.context.search.generate_embedding",
                   new=AsyncMock(return_value=vec)):
            response = await test_client.post(
                "/context/search",
                # Absichtlich ohne Titeltreffer: Findet die Suche den Knoten
                # trotzdem, kann das nur der Embedding-Pfad gewesen sein.
                json={"query": "zzz-kein-titeltreffer-zzz"},
                headers=auth_headers,
            )
        assert response.status_code == 200, response.text
        treffer = self._treffer(response.json(), bp_knoten)
        assert treffer["subject_id"] == 9502
        assert treffer["bp_version"] == "2016.V2"
        assert treffer["nr"] == "3.1.2(4)"


class TestFachvorzugBeiDerSuche:
    """`/context/search` zieht Treffer aus dem Fach der Konversation vor.

    Vorgezogen, **nicht** gefiltert: Eine Mathematik-Kompetenz kann im Physik-Chat genau
    das Gesuchte sein, und Knoten ganz ohne Fach (Leitperspektiven, schulweite Dokumente)
    dürfen nicht verschwinden. Der Bonus ist deshalb endlich — die Tests prüfen beide
    Seiten: Er muss innerhalb einer Trefferliste umsortieren und darf einen deutlich
    besseren fachfremden Treffer nicht verdrängen.

    Die Abstände sind absichtlich um `_FACHBONUS` (0,05) herum gelegt:

    ==============  =========  ====================
    Knoten          Distanz    mit Fachbonus
    ==============  =========  ====================
    fremd_stark        0,02    0,02  (kein Fach)
    fremd              0,10    0,10  (anderes Fach)
    fach               0,13    0,08
    ==============  =========  ====================
    """

    FACH_ID = 9511
    FREMD_ID = 9512

    @pytest_asyncio.fixture
    async def knoten(self, test_client, auth_headers, db_url):
        """Drei Knoten mit gesetzten Abständen zur Suchanfrage."""
        import math

        from app.config import settings

        def vektor(distanz: float) -> list[float]:
            """Einheitsvektor mit genau dieser Kosinus-Distanz zu ``[1, 0, 0, …]``."""
            v = [0.0] * settings.embedding_dimensions
            v[0] = 1.0 - distanz
            v[1] = math.sqrt(1.0 - v[0] ** 2)
            return v

        ids = {}
        for name, titel in (
            ("fach", "Fachvorzug Knoten im Fach"),
            ("fremd", "Fachvorzug Knoten im anderen Fach"),
            ("fremd_stark", "Fachvorzug Knoten deutlich naeher"),
        ):
            resp = await test_client.post(
                "/context/nodes",
                json={
                    "category": "concept", "content_type": "funktion", "title": titel,
                    "read_scope": "school", "write_scope": "school",
                },
                headers=auth_headers,
            )
            assert resp.status_code == 201, resp.text
            ids[name] = resp.json()["id"]

        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            for sid, slug in ((self.FACH_ID, "fachvorzug-fach"), (self.FREMD_ID, "fachvorzug-fremd")):
                cur.execute(
                    "INSERT INTO subjects (id, slug, name) VALUES (%s, %s, %s) "
                    "ON CONFLICT (id) DO NOTHING", (sid, slug, slug),
                )
            for name, distanz, sid in (
                ("fach", 0.13, self.FACH_ID),
                ("fremd", 0.10, self.FREMD_ID),
                ("fremd_stark", 0.02, None),   # ganz ohne Fach
            ):
                cur.execute(
                    "UPDATE context_nodes SET embedding = %s::vector, subject_id = %s "
                    "WHERE id = %s",
                    (str(vektor(distanz)), sid, ids[name]),
                )
        conn.commit()
        conn.close()
        yield ids

        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute("DELETE FROM context_nodes WHERE id = ANY(%s::uuid[])", (list(ids.values()),))
        conn.commit()
        conn.close()

    @pytest.fixture
    def konversation_im_fach(self, db_url, run_migrations):
        sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        conv_id = str(uuid4())
        conn = psycopg2.connect(sync_url)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO conversations (id, pseudonym, model_used, title, subject_id) "
                "VALUES (%s, %s, 'gpt-4o', 'Fach-Chat', %s)",
                (conv_id, TEACHER1_PSEUDO, self.FACH_ID),
            )
        conn.commit()
        conn.close()
        yield conv_id
        conn = psycopg2.connect(sync_url)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE id = %s", (conv_id,))
        conn.commit()
        conn.close()

    async def _reihenfolge(self, test_client, auth_headers, knoten, **body):
        from unittest.mock import AsyncMock, patch

        from app.config import settings

        anfrage = [0.0] * settings.embedding_dimensions
        anfrage[0] = 1.0
        with patch("app.context.search.generate_embedding",
                   new=AsyncMock(return_value=anfrage)):
            # ⚠️ Die Anfrage darf keinem der Titel **ähneln**. „Fachvorzug" tat es
            # (0,50 gegen „Fachvorzug Knoten im Fach") — der Knoten landete dann als
            # Namensträger in der Identifikation und fehlte im thematischen Abschnitt.
            # Das Embedding ist ohnehin fest vorgegeben; der Text zählt hier nicht.
            resp = await test_client.post(
                "/context/search", json={"query": "beliebige Frage", **body},
                headers=auth_headers,
            )
        assert resp.status_code == 200, resp.text
        nach_id = {v: k for k, v in knoten.items()}
        # Bewusst **nur** der thematische Abschnitt: Dort wirkt der Fachbonus. Über den
        # ganzen Umschlag gemessen schlüge hier die Titel-Teilsuche durch — „Fachvorzug"
        # ähnelt dem Titel „Fachvorzug Knoten im Fach" mit 0,50 und stünde dann als
        # Namensträger vorn. Das ist richtig so, aber es ist eine andere Aussage.
        return [
            nach_id[t["node_id"]]
            for t in resp.json()["thematisch"]["treffer"]
            if t["node_id"] in nach_id
        ]

    async def test_ohne_fachbezug_entscheidet_allein_die_aehnlichkeit(
        self, test_client, auth_headers, knoten
    ):
        """Der unveränderte Fall — und der häufigste: ein Chat ohne Fach."""
        assert await self._reihenfolge(test_client, auth_headers, knoten) == [
            "fremd_stark", "fremd", "fach",
        ]

    async def test_fach_der_konversation_wird_vorgezogen(
        self, test_client, auth_headers, knoten, konversation_im_fach
    ):
        """0,03 Rückstand ist weniger als der Bonus — `fach` überholt `fremd`."""
        assert await self._reihenfolge(
            test_client, auth_headers, knoten, conversation_id=konversation_im_fach
        ) == ["fremd_stark", "fach", "fremd"]

    async def test_deutlich_besserer_fachfremder_treffer_bleibt_oben(
        self, test_client, auth_headers, knoten, konversation_im_fach
    ):
        """Die Gegenprobe zum Filter: `fremd_stark` hat gar kein Fach und bleibt erster.

        Ohne diese Zusage wäre der Bonus ein verkappter Filter — und Leitperspektiven,
        die nie ein Fach tragen, fielen dauerhaft hinten herunter.
        """
        reihenfolge = await self._reihenfolge(
            test_client, auth_headers, knoten, conversation_id=konversation_im_fach
        )
        assert reihenfolge[0] == "fremd_stark"
        assert len(reihenfolge) == 3, "kein Knoten darf herausgefiltert werden"

    async def test_fremde_konversation_gibt_keinen_fachbezug(
        self, test_client, auth_headers_teacher2, knoten, konversation_im_fach
    ):
        """teacher2 nennt die Konversation von teacher1 — die Reihenfolge darf sich
        dadurch nicht ändern, sonst verriete sie deren Fach."""
        assert await self._reihenfolge(
            test_client, auth_headers_teacher2, knoten,
            conversation_id=konversation_im_fach,
        ) == ["fremd_stark", "fremd", "fach"]


class TestNachschlagenInDerSuche:
    """Ein benannter Knoten steht vorn — auch wenn ein anderer semantisch näher liegt.

    Die semantische Suche kann Bedeutung finden, aber keine Namen nachschlagen: „Operator
    nennen" lieferte *erkennen*, *korrigieren*, *berichten*. Vorgezogen wird der exakte
    Titeltreffer deshalb **ohne** die semantischen Treffer zu verdrängen — wer
    „vergleichen" sucht, kann ebenso gut Kompetenzen zum Vergleichen brauchen.
    """

    @pytest_asyncio.fixture
    async def knoten(self, test_client, auth_headers, db_url):
        """Ein Knoten mit dem gesuchten *Namen*, ein anderer semantisch viel näher."""
        from app.config import settings

        def vektor(distanz: float) -> list[float]:
            import math
            v = [0.0] * settings.embedding_dimensions
            v[0] = 1.0 - distanz
            v[1] = math.sqrt(1.0 - v[0] ** 2)
            return v

        ids = {}
        for name, titel in (
            ("benannt", "Zwirbeln"),                     # der gesuchte Name
            ("naeher", "3.1.1(9) etwas ganz anderes"),   # semantisch viel näher
        ):
            resp = await test_client.post(
                "/context/nodes",
                json={"category": "concept", "content_type": "funktion", "title": titel,
                      "read_scope": "school", "write_scope": "school"},
                headers=auth_headers,
            )
            assert resp.status_code == 201, resp.text
            ids[name] = resp.json()["id"]

        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            for name, distanz in (("benannt", 0.40), ("naeher", 0.02)):
                cur.execute("UPDATE context_nodes SET embedding = %s::vector WHERE id = %s",
                            (str(vektor(distanz)), ids[name]))
        conn.commit()
        conn.close()
        yield ids
        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute("DELETE FROM context_nodes WHERE id = ANY(%s::uuid[])",
                        (list(ids.values()),))
        conn.commit()
        conn.close()

    async def _reihenfolge(self, test_client, auth_headers, knoten, frage):
        from unittest.mock import AsyncMock, patch

        from app.config import settings

        anfrage = [0.0] * settings.embedding_dimensions
        anfrage[0] = 1.0
        with patch("app.context.search.generate_embedding",
                   new=AsyncMock(return_value=anfrage)):
            resp = await test_client.post("/context/search", json={"query": frage},
                                          headers=auth_headers)
        assert resp.status_code == 200, resp.text
        nach_id = {v: k for k, v in knoten.items()}
        return [
            nach_id[t["node_id"]]
            for t in _als_liste(resp.json())
            if t["node_id"] in nach_id
        ]

    async def test_benannter_knoten_steht_vorn(self, test_client, auth_headers, knoten):
        """Trotz 0,40 gegen 0,02 Distanz — der Name schlägt die Ähnlichkeit."""
        assert await self._reihenfolge(
            test_client, auth_headers, knoten, "Zwirbeln"
        ) == ["benannt", "naeher"]

    async def test_frageform_aendert_nichts(self, test_client, auth_headers, knoten):
        """Füllwörter dürfen das Nachschlagen nicht verhindern."""
        assert await self._reihenfolge(
            test_client, auth_headers, knoten, "Was bedeutet der Operator Zwirbeln?"
        ) == ["benannt", "naeher"]

    async def test_semantische_treffer_bleiben_erhalten(
        self, test_client, auth_headers, knoten
    ):
        """Vorgezogen, nicht gefiltert: Der nähere Knoten verschwindet nicht."""
        reihenfolge = await self._reihenfolge(
            test_client, auth_headers, knoten, "Zwirbeln"
        )
        assert "naeher" in reihenfolge

    async def test_thematische_anfrage_loest_kein_nachschlagen_aus(
        self, test_client, auth_headers, knoten
    ):
        """Die Gegenprobe: Enthält die Anfrage den Namen nur nebenbei, bleibt es bei der
        Ähnlichkeit — sonst zöge jedes zufällig getroffene Wort einen Knoten nach vorn."""
        assert await self._reihenfolge(
            test_client, auth_headers, knoten,
            "Zwirbeln und Flechten als gestalterische Verfahren im Textilunterricht",
        ) == ["naeher", "benannt"]


class TestNachschlageIndexWirdBenutzt:
    """Der Ausdrucksindex aus Migration 0053 muss tatsächlich greifen.

    Sein Ausfall ist still: Weicht der Ausdruck der Abfrage auch nur in einem Zeichen ab,
    fällt PostgreSQL auf einen vollständigen Durchlauf zurück — dasselbe Ergebnis, aber
    rund 70 statt 0,3 ms, und das bei **jeder** Suche.
    """

    async def test_explain_zeigt_indexnutzung(self, db_url, run_migrations):
        import sqlalchemy as sa
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.context.search import Suchprofil, identifikations_abfrage

        abfrage = identifikations_abfrage("nennen", Suchprofil(pseudonym="p"))
        # `literal_binds`, weil EXPLAIN die Werte braucht: Ein Platzhalter ohne Wert
        # lässt den Planer generisch planen — dann sagt der Plan nichts über den Fall.
        roh = str(abfrage.compile(compile_kwargs={"literal_binds": True}))

        engine = create_async_engine(db_url)
        try:
            async with engine.connect() as con:
                plan = "\n".join(
                    r[0] for r in (await con.execute(sa.text("EXPLAIN " + roh))).all()
                )
        finally:
            await engine.dispose()

        assert "idx_context_nodes_titel_nachschlagen" in plan, (
            f"Der Nachschlage-Index wird nicht benutzt. Plan:\n{plan}"
        )


class TestAufzaehlung:
    """Die Frageklasse „alle, die …" (ADR-017, AP3) gegen eine echte Datenbank.

    Drei Zusagen, die sich nur hier prüfen lassen: dass **vor** dem Limit gezählt wird,
    dass Fassungen derselben Kompetenz einmal zählen, und dass die Zählung niemandem
    verrät, was er nicht sehen darf.
    """

    @pytest_asyncio.fixture
    async def bausteine(self, test_client, auth_headers, db_url):
        """Fünf Knoten desselben Namens: drei sichtbare, zwei Sonderfälle."""
        angelegt = []
        for i in range(3):
            resp = await test_client.post(
                "/context/nodes",
                json={
                    "category": "knowledge",
                    "content_type": "operator",
                    # Gliederungsnummer in BP-Form — sie wird wegnormalisiert, alle
                    # drei Knoten heißen für die Aufzählung „zwirbeln".
                    "title": f"9.9.{i + 1} Zwirbeln",
                    "read_scope": "school",
                    "write_scope": "school",
                },
                headers=auth_headers,
            )
            assert resp.status_code == 201, resp.text
            angelegt.append(resp.json())

        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO subjects (id, slug, name) VALUES "
                "(9503, 'zwirbel-a', 'Zwirbelkunde'), (9504, 'zwirbel-b', 'Zwirbeltechnik') "
                "ON CONFLICT (id) DO NOTHING"
            )
            for node, fach in zip(angelegt, (9503, 9504, 9504)):
                cur.execute(
                    "UPDATE context_nodes SET subject_id = %s WHERE id = %s",
                    (fach, node["id"]),
                )
        conn.commit()
        conn.close()

        yield angelegt

        # Aufräumen ist hier Pflicht, nicht Kosmetik: Die Tests prüfen **Zahlen**.
        # Bleiben die Knoten des einen Falls liegen, zählt der nächste sie mit — und
        # der Fehlschlag zeigt sich nur im Gesamtlauf, nie beim einzelnen Test.
        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM context_nodes WHERE id = ANY(%s::uuid[])",
                ([n["id"] for n in angelegt],),
            )
        conn.commit()
        conn.close()

    async def _zaehle(self, db_session, pseudonym, **filter_felder):
        from app.context.filters import Knotenfilter
        from app.context.search import Suchprofil, aufzaehlung

        return await aufzaehlung(
            Knotenfilter(titel="zwirbeln", **filter_felder),
            Suchprofil(pseudonym=pseudonym, aufzaehlung=1),
            db_session,
            gruppierung="fach",
        )

    async def test_zaehlt_vor_dem_limit(self, bausteine, db_session):
        """Das Budget begrenzt die Lieferung, nicht die Zählung — sonst wäre „x von y"
        nicht zu haben, und genau daran scheiterte die alte Suche (Befund 1)."""
        abschnitt = await self._zaehle(db_session, TEACHER1_PSEUDO)
        assert abschnitt.gesamt == 3
        assert abschnitt.geliefert == 1
        assert abschnitt.vollstaendig is False

    async def test_gruppierung_zaehlt_alle_faecher(self, bausteine, db_session):
        abschnitt = await self._zaehle(db_session, TEACHER1_PSEUDO)
        assert {(g.name, g.anzahl) for g in abschnitt.gruppen} == {
            ("Zwirbelkunde", 1), ("Zwirbeltechnik", 2),
        }

    async def test_fassungen_derselben_kompetenz_zaehlen_einmal(
        self, test_client, auth_headers, db_url, db_session
    ):
        """Zwei BP-Editionen derselben Kompetenz sind ein Baustein, nicht zwei."""
        ids = []
        for fassung in ("2016", "2016.V2"):
            resp = await test_client.post(
                "/context/nodes",
                json={
                    "category": "knowledge",
                    "content_type": "ik_kompetenz",
                    "title": "Doppelte Fassung",
                    "read_scope": "school",
                    "write_scope": "school",
                    "metadata": {"kompetenz_nr": "9.9.9(1)", "bp_version": fassung},
                },
                headers=auth_headers,
            )
            assert resp.status_code == 201, resp.text
            ids.append(resp.json()["id"])

        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            for node_id, fassung in zip(ids, ("2016", "2016.V2")):
                cur.execute(
                    "UPDATE context_nodes SET subject_id = 9503, bp_version = %s "
                    "WHERE id = %s",
                    (fassung, node_id),
                )
        conn.commit()
        conn.close()

        from app.context.filters import Knotenfilter
        from app.context.search import Suchprofil, aufzaehlung

        abschnitt = await aufzaehlung(
            Knotenfilter(titel="doppelte fassung"),
            Suchprofil(pseudonym=TEACHER1_PSEUDO),
            db_session,
        )
        assert abschnitt.gesamt == 1, "beide Fassungen wurden gezählt"

    async def test_fremder_privater_knoten_zaehlt_nicht_mit(
        self, test_client, auth_headers_teacher2, db_session
    ):
        """Die Zählung ist eine Auskunft über den **sichtbaren** Bestand.

        Zählte sie mit, was man nicht lesen darf, verriete schon die Zahl die Existenz
        fremder privater Bausteine — eine Auskunft, die kein Rechtefilter je wieder
        einfängt.
        """
        resp = await test_client.post(
            "/context/nodes",
            json={
                "category": "artifact",
                "content_type": "aufgabe",
                "title": "Heimlich",
                "read_scope": "private",
                "write_scope": "private",
            },
            headers=auth_headers_teacher2,
        )
        assert resp.status_code == 201, resp.text

        from app.context.filters import Knotenfilter
        from app.context.search import Suchprofil, aufzaehlung

        fremd = await aufzaehlung(
            Knotenfilter(titel="heimlich"),
            Suchprofil(pseudonym=TEACHER1_PSEUDO), db_session,
        )
        eigen = await aufzaehlung(
            Knotenfilter(titel="heimlich"),
            Suchprofil(pseudonym=TEACHER2_PSEUDO), db_session,
        )
        assert fremd.gesamt == 0
        assert eigen.gesamt == 1


class TestTeilsucheIndexWirdBenutzt:
    """Der Trigramm-Index aus Migration 0054 muss zur Abfrage passen.

    Sein Ausfall ist **still**: Weicht der Indexausdruck auch nur in einem Zeichen vom
    Ausdruck der Abfrage ab, benutzt PostgreSQL ihn nicht — dasselbe Ergebnis, nur als
    vollständiger Durchlauf über alle Titel, und das bei jeder Suche, weil die
    Identifikation seit AP4 immer läuft.

    ⚠️ **Geprüft wird die Passung, nicht die Planerwahl.** Ob der Planer den Index
    *wählt*, hängt an der Tabellengröße: In der fast leeren Testdatenbank ist ein
    vollständiger Durchlauf billiger als jeder Index, und selbst 3 000 Füllzeilen ändern
    daran nichts. Auf dem Entwicklungsbestand (14 244 Knoten) greift er nachweislich —
    dort steht im Plan `Bitmap Index Scan on idx_context_nodes_titel_trigramm`, 14 ms.
    Deshalb prüft dieser Test das, was reproduzierbar **und** brüchig ist: dass der
    Ausdruck überhaupt indexfähig ist.
    """

    async def test_index_passt_zum_abfrageausdruck(self, db_url, run_migrations):
        import sqlalchemy as sa
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.context.filters import TITEL_NORMALISIERT
        from app.context.search import _TEILTREFFER_SCHWELLE

        # Nur die Trigramm-Bedingung, ohne Sichtbarkeit und Status: Für diese eine
        # Bedingung ist der Trigramm-Index der einzige, der überhaupt in Frage kommt.
        # Passt der Ausdruck, muss PostgreSQL ihn nehmen, sobald der vollständige
        # Durchlauf verboten ist.
        abfrage = sa.select(sa.literal_column("id")).select_from(
            sa.table("context_nodes")
        ).where(sa.literal("anleitung zur verwendung des operators nennen").op("%")(
            TITEL_NORMALISIERT
        ))
        roh = str(abfrage.compile(compile_kwargs={"literal_binds": True}))

        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as con:
                await con.execute(sa.text(
                    f"SET LOCAL pg_trgm.similarity_threshold = {_TEILTREFFER_SCHWELLE}"
                ))
                await con.execute(sa.text("SET LOCAL enable_seqscan = off"))
                plan = "\n".join(
                    r[0] for r in (await con.execute(sa.text("EXPLAIN " + roh))).all()
                )
        finally:
            await engine.dispose()

        assert "idx_context_nodes_titel_trigramm" in plan, (
            "Der Trigramm-Index ist für diese Abfrage nicht verwendbar — vermutlich "
            f"weicht sein Ausdruck von `titel_normalisiert_sql` ab. Plan:\n{plan}"
        )


class TestIdentifikationZweistufig:
    """Exakte Namensträger und ähnlich benannte Bausteine, sauber getrennt (AP4)."""

    @pytest_asyncio.fixture
    async def bausteine(self, test_client, auth_headers, auth_headers_teacher2, db_url):
        """Ein exakt benannter Knoten, zwei beschreibend benannte in fremder Hand."""
        angelegt = {}
        # ⚠️ Die Titel sind so gewählt, dass sie einander **überlappen**. Ein bloß
        # gemeinsames Wort genügt nicht: `similarity('zwirbeln', 'anleitung zum
        # zwirbeln von draht')` ist 0,28 und damit unter der Schwelle — genau deshalb
        # überschwemmt die Teilsuche thematische Anfragen nicht.
        vorgaben = [
            ("exakt_eigen", "Anleitung zum Zwirbeln von Draht", auth_headers),
            ("exakt_fremd", "Anleitung zum Zwirbeln von Draht", auth_headers_teacher2),
            ("beschreibend", "Anleitung zum Zwirbeln von Draht mit der Zange",
             auth_headers_teacher2),
        ]
        for name, titel, header in vorgaben:
            resp = await test_client.post(
                "/context/nodes",
                json={
                    "category": "document",
                    "content_type": "methodenblatt",
                    "title": titel,
                    "read_scope": "school",
                    "write_scope": "private",
                },
                headers=header,
            )
            assert resp.status_code == 201, resp.text
            angelegt[name] = resp.json()

        yield angelegt

        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM context_nodes WHERE id = ANY(%s::uuid[])",
                ([n["id"] for n in angelegt.values()],),
            )
        conn.commit()
        conn.close()

    async def _identifiziere(self, db_session, frage, pseudonym):
        from app.context.search import Suchprofil, identifikation

        return await identifikation(
            frage, Suchprofil(pseudonym=pseudonym, identifikation=8), db_session
        )

    async def test_exakter_treffer_steht_vor_dem_teiltreffer(
        self, bausteine, db_session
    ):
        """Die Reihenfolge ist die Aussage: Was so **heißt**, steht vor dem, was so
        ähnlich heißt."""
        abschnitt = await self._identifiziere(
            db_session, "Anleitung zum Zwirbeln von Draht", TEACHER1_PSEUDO
        )
        arten = [t["treffer_art"] for t in abschnitt.treffer]
        assert arten[0] == "exakt"
        assert "teilweise" in arten, "der längere Titel fehlt"
        assert arten.index("teilweise") > max(
            i for i, a in enumerate(arten) if a == "exakt"
        )

    async def test_nur_exakte_treffer_zaehlen_als_namenstraeger(
        self, bausteine, db_session
    ):
        """Die Zählung trägt die Existenzaussage — Ähnlichkeit darf nicht hineinzählen."""
        abschnitt = await self._identifiziere(
            db_session, "Anleitung zum Zwirbeln von Draht", TEACHER1_PSEUDO
        )
        assert abschnitt.gesamt == 2, "zwei Bausteine tragen diesen Namen"
        assert abschnitt.geliefert == 3, "der ähnlich benannte kommt hinzu"

    async def test_kurze_anfrage_holt_keinen_langen_titel_heran(
        self, bausteine, db_session
    ):
        """Die Gegenprobe zur Schwelle 0,50: Ein einzelnes gemeinsames Wort reicht
        nicht. Ohne diese Grenze bekäme jede thematische Anfrage einen Block
        ähnlich benannter Bausteine vorangestellt."""
        abschnitt = await self._identifiziere(db_session, "Zwirbeln", TEACHER1_PSEUDO)
        assert abschnitt.treffer == []

    async def test_beschreibender_titel_wird_ueber_teilwortlaut_gefunden(
        self, bausteine, db_session
    ):
        """Der S2-Leitfall: verkürzte Anfrage, längerer Titel, kein exakter Name."""
        abschnitt = await self._identifiziere(
            db_session, "Anleitung Zwirbeln Draht Zange", TEACHER1_PSEUDO
        )
        assert abschnitt.gesamt == 0, "das ist kein exakter Name"
        assert bausteine["beschreibend"]["id"] in [t["node_id"] for t in abschnitt.treffer]

    async def test_eigenes_steht_vor_fremdem(self, bausteine, db_session):
        """Zwei gleichnamige Handreichungen — die eigene zuerst, die fremde bleibt."""
        abschnitt = await self._identifiziere(
            db_session, "Anleitung zum Zwirbeln von Draht", TEACHER1_PSEUDO
        )
        ids = [t["node_id"] for t in abschnitt.treffer]
        eigen, fremd = bausteine["exakt_eigen"]["id"], bausteine["exakt_fremd"]["id"]
        assert eigen in ids and fremd in ids, "kein Knoten darf herausfallen"
        assert ids.index(eigen) < ids.index(fremd)

    async def test_umgekehrt_fuer_die_andere_lehrkraft(self, bausteine, db_session):
        """Die Gegenprobe — sonst wäre es kein Vorrang, sondern eine feste Reihenfolge."""
        abschnitt = await self._identifiziere(
            db_session, "Anleitung zum Zwirbeln von Draht", TEACHER2_PSEUDO
        )
        ids = [t["node_id"] for t in abschnitt.treffer]
        assert ids.index(bausteine["exakt_fremd"]["id"]) < ids.index(
            bausteine["exakt_eigen"]["id"]
        )

    async def test_schwelle_gilt_in_der_transaktion(self, bausteine, db_session):
        """⚠️ Die pg_trgm-Schwelle ist eine Sitzungseinstellung.

        Gesetzt wird sie über ``set_config(…, is_local := true)`` und gilt damit nur bis
        zum Ende der Transaktion; ein einfaches ``SET`` wanderte im gepoolten Betrieb mit
        der Verbindung zum nächsten Request und veränderte dort eine Suche, die nie darum
        gebeten hat. Hier wird geprüft, dass sie überhaupt ankommt — die Transaktions-
        bindung selbst ist eine Zusage von PostgreSQL.
        """
        import sqlalchemy as sa

        from app.context.search import _TEILTREFFER_SCHWELLE

        await self._identifiziere(db_session, "Anleitung zum Zwirbeln", TEACHER1_PSEUDO)
        wert = (await db_session.execute(
            sa.text("SHOW pg_trgm.similarity_threshold")
        )).scalar_one()
        assert float(wert) == _TEILTREFFER_SCHWELLE


class TestSuchseitenProfil:
    """`POST /context/search` bedient zwei Profile: Vorschlagsfenster und Suchseite."""

    @pytest_asyncio.fixture
    async def bausteine(self, test_client, auth_headers, db_url):
        angelegt = []
        for titel, typ in (
            ("Suchseite Alpha", "methode"),
            ("Suchseite Beta", "methode"),
            ("Suchseite Gamma", "konvention"),
        ):
            resp = await test_client.post(
                "/context/nodes",
                json={
                    "category": "knowledge" if typ == "methode" else "document",
                    "content_type": typ,
                    "title": titel,
                    "content": "Inhalt zur Suchseite",
                    "read_scope": "school",
                    "write_scope": "school",
                },
                headers=auth_headers,
            )
            assert resp.status_code == 201, resp.text
            angelegt.append(resp.json())

        yield angelegt

        conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM context_nodes WHERE id = ANY(%s::uuid[])",
                ([n["id"] for n in angelegt],),
            )
        conn.commit()
        conn.close()

    async def _suche(self, test_client, auth_headers, **koerper):
        from unittest.mock import AsyncMock, patch

        from app.config import settings

        vektor = [0.0] * settings.embedding_dimensions
        vektor[0] = 1.0
        with patch("app.context.search.generate_embedding",
                   new=AsyncMock(return_value=vektor)):
            resp = await test_client.post(
                "/context/search", json={"query": "Suchseite Alpha", **koerper},
                headers=auth_headers,
            )
        assert resp.status_code == 200, resp.text
        return resp.json()

    async def test_ohne_facette_keine_aufzaehlung(
        self, test_client, auth_headers, bausteine
    ):
        """Ohne Filterbedingung ist die Frage keine Aufzählungsfrage — dann gibt es auch
        keinen Abschnitt, der eine Gesamtzahl behauptet."""
        umschlag = await self._suche(test_client, auth_headers)
        assert umschlag["aufzaehlung"] is None

    async def test_facette_bringt_die_gezaehlte_aufzaehlung(
        self, test_client, auth_headers, bausteine
    ):
        umschlag = await self._suche(
            test_client, auth_headers, content_type=["methode"], limit=25
        )
        aufzaehlung = umschlag["aufzaehlung"]
        assert aufzaehlung is not None
        titel = {t["title"] for t in aufzaehlung["treffer"]}
        assert {"Suchseite Alpha", "Suchseite Beta"} <= titel
        assert "Suchseite Gamma" not in titel, "der Typfilter greift nicht"
        assert aufzaehlung["gesamt"] >= 2
        assert aufzaehlung["gruppen"] is not None

    async def test_trefferart_reist_mit(self, test_client, auth_headers, bausteine):
        """Die Suchseite trennt exakte Namensträger von ähnlich benannten — dafür muss
        sie am Treffer ablesen können, welcher Stufe er entstammt."""
        umschlag = await self._suche(test_client, auth_headers)
        arten = {t["treffer_art"] for t in umschlag["identifikation"]["treffer"]}
        assert arten <= {"exakt", "teilweise"}
        assert "exakt" in arten, "der gleichnamige Knoten fehlt"

    async def test_limit_gilt_je_abschnitt(self, test_client, auth_headers, bausteine):
        umschlag = await self._suche(test_client, auth_headers, limit=1)
        assert len(umschlag["thematisch"]["treffer"]) <= 1
