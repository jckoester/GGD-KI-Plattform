"""KS-Phase-4 Integrationstests für neue Filter und Endpunkte."""

import json
import uuid as _uuid

import psycopg2
import pytest
from pathlib import Path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Fixture-Daten
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Test-Pseudonyme
TEACHER1_PSEUDO = "teacher1-pseudo"
TEACHER2_PSEUDO = "teacher2-pseudo"

# Fach- und Gruppendaten
MATH_SUBJECT = {
    "id": 100,
    "name": "Mathematik",
    "slug": "mathematik",
    "description": "Mathematik Fach",
}

PHYSICS_SUBJECT = {
    "id": 101,
    "name": "Physik",
    "slug": "physik",
    "description": "Physik Fach",
}

MATH_GROUP_1 = {
    "id": 200,
    "name": "Mathe 10a",
    "slug": "mathe-10a",
    "type": "teaching_group",
    "subject_id": 100,
}

MATH_GROUP_2 = {
    "id": 201,
    "name": "Mathe 10b", 
    "slug": "mathe-10b",
    "type": "teaching_group",
    "subject_id": 100,
}

PHYSICS_GROUP_1 = {
    "id": 202,
    "name": "Physik 10a",
    "slug": "physik-10a",
    "type": "teaching_group",
    "subject_id": 101,
}


# Knotendaten für Test-Szenarien
# Für subject_slug Filter: Knoten in Math-Gruppen + globale knowledge-Knoten
# Für group_id Filter: Knoten in spezifischer Gruppe
# Für neighborhood: Knoten mit Kanten dazwischen
# Für archived-references: archivierte Knoten mit supersedes-Kante
# Für copy: Quellknoten zum Kopieren


def _generate_node_id():
    """Generiert eine neue UUID für Knoten."""
    return str(_uuid.uuid4())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Seed- und Teardown-Funktionen
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def seed_phase4_data(db_url: str) -> dict:
    """Legt alle Testdaten für Phase-4 an. Gibt Dict mit IDs zurück."""
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    node_ids = {}
    
    try:
        with conn.cursor() as cur:
            # ── Clean slate ───────────────────────────────────────────────────
            # Frühere (committende) Tests im selben Lauf können Fächer mit denselben
            # Slugs hinterlassen (z. B. 'mathematik' aus den Curriculum-Tests). Da der
            # Seed feste IDs UND Slugs nutzt, würde der Insert sonst an der UNIQUE-
            # Constraint subjects_slug_key scheitern. subject_id-FKs sind ON DELETE
            # SET NULL, daher ist das Entfernen unkritisch.
            cur.execute(
                "DELETE FROM groups WHERE id = ANY(%s)",
                ([MATH_GROUP_1["id"], MATH_GROUP_2["id"], PHYSICS_GROUP_1["id"]],),
            )
            cur.execute(
                "DELETE FROM subjects WHERE id = ANY(%s) OR slug = ANY(%s)",
                (
                    [MATH_SUBJECT["id"], PHYSICS_SUBJECT["id"]],
                    [MATH_SUBJECT["slug"], PHYSICS_SUBJECT["slug"]],
                ),
            )

            # ── Fächer anlegen ────────────────────────────────────────────────
            for subject in [MATH_SUBJECT, PHYSICS_SUBJECT]:
                cur.execute("""
                    INSERT INTO subjects (id, name, slug)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                """, (subject["id"], subject["name"], subject["slug"]))
            
            # ── Gruppen anlegen ────────────────────────────────────────────────
            for group in [MATH_GROUP_1, MATH_GROUP_2, PHYSICS_GROUP_1]:
                cur.execute("""
                    INSERT INTO groups (id, name, slug, type, subject_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                """, (group["id"], group["name"], group["slug"], group["type"], group["subject_id"]))
            
            # ── Kontext-Knoten für Filter-Tests ────────────────────────────────
            
            # Knoten in Math Gruppe 1 (aktiv)
            node_ids["math1_active"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, read_scope_group_id,
                   owner_pseudonym, schuljahr)
                VALUES (%s, 'concept', 'thema', 'Math Thema 1 (aktiv)', 'Inhalt Math 1',
                        '{}', 'group', 'private', 'active', %s, %s, '2024/25')
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["math1_active"], MATH_GROUP_1["id"], TEACHER1_PSEUDO))
            
            # Knoten in Math Gruppe 1 (archiviert)
            node_ids["math1_archived"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, read_scope_group_id,
                   owner_pseudonym, archived_at, schuljahr)
                VALUES (%s, 'concept', 'thema', 'Math Thema 1 (archiviert)', 'Inhalt Math 1 alt',
                        '{}', 'group', 'private', 'archived', %s, %s,
                        NOW(), '2023/24')
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["math1_archived"], MATH_GROUP_1["id"], TEACHER1_PSEUDO))
            
            # Knoten in Math Gruppe 2 (aktiv)
            node_ids["math2_active"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, read_scope_group_id,
                   owner_pseudonym, schuljahr)
                VALUES (%s, 'concept', 'thema', 'Math Thema 2 (aktiv)', 'Inhalt Math 2',
                        '{}', 'group', 'private', 'active', %s, %s, '2024/25')
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["math2_active"], MATH_GROUP_2["id"], TEACHER1_PSEUDO))
            
            # Knoten in Math Gruppe 2 (archiviert, gehört TEACHER2)
            node_ids["math2_archived_teacher2"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, read_scope_group_id,
                   owner_pseudonym, archived_at, schuljahr)
                VALUES (%s, 'concept', 'thema', 'Math Thema 2 alt (teacher2)', 'Inhalt Math 2 alt',
                        '{}', 'group', 'private', 'archived', %s, %s,
                        NOW(), '2023/24')
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["math2_archived_teacher2"], MATH_GROUP_2["id"], TEACHER2_PSEUDO))
            
            # Knoten in Physik Gruppe 1 (aktiv)
            node_ids["physics_active"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, read_scope_group_id,
                   owner_pseudonym, schuljahr)
                VALUES (%s, 'concept', 'thema', 'Physik Thema 1', 'Inhalt Physik 1',
                        '{}', 'group', 'private', 'active', %s, %s, '2024/25')
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["physics_active"], PHYSICS_GROUP_1["id"], TEACHER1_PSEUDO))
            
            # Globaler knowledge-Knoten (aktiv)
            node_ids["global_knowledge"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, owner_pseudonym, schuljahr)
                VALUES (%s, 'knowledge', 'themengebiet', 'Globaler Wissensknoten', 'Globaler Inhalt',
                        '{}', 'global', 'global', 'active', %s, '2024/25')
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["global_knowledge"], TEACHER1_PSEUDO))
            
            # Schulweiter knowledge-Knoten (aktiv)
            node_ids["school_knowledge"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, owner_pseudonym, schuljahr)
                VALUES (%s, 'knowledge', 'themengebiet', 'Schulweiter Wissensknoten', 'Schulweiter Inhalt',
                        '{}', 'school', 'school', 'active', %s, '2024/25')
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["school_knowledge"], TEACHER1_PSEUDO))
            
            # Privater Knoten von TEACHER1 (aktiv)
            node_ids["private_teacher1"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, owner_pseudonym, schuljahr)
                VALUES (%s, 'concept', 'thema', 'Privater Knoten Teacher1', 'Privat Inhalt',
                        '{}', 'private', 'private', 'active', %s, '2024/25')
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["private_teacher1"], TEACHER1_PSEUDO))
            
            # Privater Knoten von TEACHER2 (aktiv)
            node_ids["private_teacher2"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, owner_pseudonym, schuljahr)
                VALUES (%s, 'concept', 'thema', 'Privater Knoten Teacher2', 'Privat Inhalt 2',
                        '{}', 'private', 'private', 'active', %s, '2024/25')
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["private_teacher2"], TEACHER2_PSEUDO))
            
            # ── Knoten für Neighborhood-Tests ─────────────────────────────────
            # Knoten A (Zentrum)
            node_ids["neighborhood_a"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, owner_pseudonym)
                VALUES (%s, 'concept', 'thema', 'Neighborhood Zentrum', 'Zentrum',
                        '{}', 'school', 'school', 'active', %s)
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["neighborhood_a"], TEACHER1_PSEUDO))
            
            # Knoten B (direkter Nachbar von A)
            node_ids["neighborhood_b"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, owner_pseudonym)
                VALUES (%s, 'concept', 'unterthema', 'Nachbar B', 'Nachbar B Inhalt',
                        '{}', 'school', 'school', 'active', %s)
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["neighborhood_b"], TEACHER1_PSEUDO))
            
            # Knoten C (direkter Nachbar von A)
            node_ids["neighborhood_c"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, owner_pseudonym)
                VALUES (%s, 'concept', 'unterthema', 'Nachbar C', 'Nachbar C Inhalt',
                        '{}', 'school', 'school', 'active', %s)
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["neighborhood_c"], TEACHER1_PSEUDO))
            
            # Knoten D (2 Hops von A entfernt: A -> B -> D)
            node_ids["neighborhood_d"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, owner_pseudonym)
                VALUES (%s, 'concept', 'unterthema', 'Nachbar D', 'Nachbar D Inhalt',
                        '{}', 'school', 'school', 'active', %s)
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["neighborhood_d"], TEACHER1_PSEUDO))
            
            # Knoten E (archiviert, für archived-references Test)
            node_ids["archived_source"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, owner_pseudonym, archived_at)
                VALUES (%s, 'concept', 'thema', 'Alter Knoten', 'Alter Inhalt',
                        '{}', 'school', 'school', 'archived', %s, NOW())
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["archived_source"], TEACHER1_PSEUDO))
            
            # Knoten F (neuer Nachfolger von E, active)
            node_ids["archived_successor"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, owner_pseudonym)
                VALUES (%s, 'concept', 'thema', 'Neuer Knoten (Nachfolger)', 'Neuer Inhalt',
                        '{}', 'school', 'school', 'active', %s)
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["archived_successor"], TEACHER1_PSEUDO))
            
            # Knoten für Copy-Test
            node_ids["copy_source"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, owner_pseudonym,
                   read_scope_group_id, schuljahr, valid_until)
                VALUES (%s, 'knowledge', 'themengebiet', 'Copy-Quelle', 'Inhalt zum Kopieren',
                        '{"test": "value"}', 'subject', 'private', 'active', %s,
                        %s, '2024/25', '2025-06-30')
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["copy_source"], TEACHER1_PSEUDO, MATH_GROUP_1["id"]))
            
            # Archivierter Knoten zum Kopieren
            node_ids["copy_source_archived"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, owner_pseudonym,
                   read_scope_group_id, schuljahr, archived_at)
                VALUES (%s, 'knowledge', 'themengebiet', 'Copy-Quelle (archiviert)', 'Archivierter Inhalt',
                        '{"archived": true}', 'subject', 'private', 'archived', %s,
                        %s, '2023/24', NOW())
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["copy_source_archived"], TEACHER1_PSEUDO, MATH_GROUP_1["id"]))
            
            # ── Kanten für Neighborhood-Tests ─────────────────────────────────
            # A -> B (references)
            cur.execute("""
                INSERT INTO context_edges (from_node_id, to_node_id, relation, metadata)
                VALUES (%s, %s, 'references', '{}')
                ON CONFLICT (from_node_id, to_node_id, relation) DO NOTHING
            """, (node_ids["neighborhood_a"], node_ids["neighborhood_b"]))
            
            # A <- C (references, also C -> A)
            cur.execute("""
                INSERT INTO context_edges (from_node_id, to_node_id, relation, metadata)
                VALUES (%s, %s, 'references', '{}')
                ON CONFLICT (from_node_id, to_node_id, relation) DO NOTHING
            """, (node_ids["neighborhood_c"], node_ids["neighborhood_a"]))
            
            # B -> D (references)
            cur.execute("""
                INSERT INTO context_edges (from_node_id, to_node_id, relation, metadata)
                VALUES (%s, %s, 'references', '{}')
                ON CONFLICT (from_node_id, to_node_id, relation) DO NOTHING
            """, (node_ids["neighborhood_b"], node_ids["neighborhood_d"]))
            
            # D -> C (part_of)
            cur.execute("""
                INSERT INTO context_edges (from_node_id, to_node_id, relation, metadata)
                VALUES (%s, %s, 'part_of', '{}')
                ON CONFLICT (from_node_id, to_node_id, relation) DO NOTHING
            """, (node_ids["neighborhood_d"], node_ids["neighborhood_c"]))
            
            # ── Kanten für archived-references Test ────────────────────────────
            # archived_source -> archived_target (references)
            # archived_target ist archiviert
            node_ids["archived_target"] = _generate_node_id()
            cur.execute("""
                INSERT INTO context_nodes
                  (id, category, content_type, title, content, metadata,
                   read_scope, write_scope, status, owner_pseudonym, archived_at)
                VALUES (%s, 'concept', 'thema', 'Ziel archiviert', 'Ziel Inhalt',
                        '{}', 'school', 'school', 'archived', %s, NOW())
                ON CONFLICT (id) DO NOTHING
            """, (node_ids["archived_target"], TEACHER1_PSEUDO))
            
            cur.execute("""
                INSERT INTO context_edges (from_node_id, to_node_id, relation, metadata)
                VALUES (%s, %s, 'references', '{}')
                ON CONFLICT (from_node_id, to_node_id, relation) DO NOTHING
            """, (node_ids["archived_source"], node_ids["archived_target"]))
            
            # archived_target -> archived_successor (supersedes)
            cur.execute("""
                INSERT INTO context_edges (from_node_id, to_node_id, relation, metadata)
                VALUES (%s, %s, 'supersedes', '{}')
                ON CONFLICT (from_node_id, to_node_id, relation) DO NOTHING
            """, (node_ids["archived_successor"], node_ids["archived_target"]))
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
    
    return node_ids



def teardown_phase4_data(db_url: str, node_ids: dict) -> None:
    """Löscht alle Testdaten für Phase-4."""
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    
    try:
        with conn.cursor() as cur:
            # Alle erstellten Knoten löschen (CASCADE löscht auch Kanten)
            # Zuerst alle Knoten löschen, die unsere Testgruppen referenzieren
            # (auch Überbleibsel aus fehlgeschlagenen Vorrunden)
            group_ids = [MATH_GROUP_1["id"], MATH_GROUP_2["id"], PHYSICS_GROUP_1["id"]]
            cur.execute(
                "DELETE FROM context_nodes WHERE read_scope_group_id = ANY(%s)",
                (group_ids,),
            )
            # Dann nach ID (für nicht-gruppengebundene Testknoten)
            all_node_ids = list(node_ids.values())
            if all_node_ids:
                cur.execute("""
                    DELETE FROM context_nodes
                    WHERE id = ANY(%s::uuid[])
                """, (all_node_ids,))

            # Gruppen löschen
            for group in [MATH_GROUP_1, MATH_GROUP_2, PHYSICS_GROUP_1]:
                cur.execute("""
                    DELETE FROM groups
                    WHERE id = %s
                """, (group["id"],))
            
            # Fächer löschen
            for subject in [MATH_SUBJECT, PHYSICS_SUBJECT]:
                cur.execute("""
                    DELETE FROM subjects
                    WHERE id = %s
                """, (subject["id"],))
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pytest Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.fixture(scope="session")
def phase4_node_ids(db_url, run_migrations):
    """Legt alle Phase-4 Testdaten einmalig an und räumt danach wieder auf.

    Der Teardown verhindert, dass die committeten Fächer/Gruppen/Knoten (feste IDs)
    in nachfolgende Testdateien leaken.
    """
    node_ids = seed_phase4_data(db_url)
    yield node_ids
    teardown_phase4_data(db_url, node_ids)



@pytest.fixture(scope="session", autouse=True)
def cleanup_phase4(db_url, phase4_node_ids):
    """Bereinigt Phase-4 Daten am Ende der Session."""
    yield
    teardown_phase4_data(db_url, phase4_node_ids)



@pytest.fixture(scope="session")
def teacher_headers(jwt_service):
    """HTTP-Header für teacher1-pseudo."""
    token, _ = jwt_service.issue(pseudonym=TEACHER1_PSEUDO, roles=["teacher"], grade=None)
    return {"Cookie": f"session={token}"}



@pytest.fixture(scope="session")
def teacher2_headers(jwt_service):
    """HTTP-Header für teacher2-pseudo."""
    token, _ = jwt_service.issue(pseudonym=TEACHER2_PSEUDO, roles=["teacher"], grade=None)
    return {"Cookie": f"session={token}"}



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestListNodesFilters:
    """Tests für die neuen Filter in GET /context/nodes."""

    @pytest.mark.asyncio
    async def test_list_nodes_subject_slug_filter(self, test_client, teacher_headers, phase4_node_ids):
        """Nur Knoten der richtigen Gruppe + schulweite/globale knowledge-Knoten."""
        resp = await test_client.get(
            "/context/nodes?subject_slug=mathematik",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Sollte Knoten aus Math-Gruppen enthalten
        titles = [n["title"] for n in data]
        assert "Math Thema 1 (aktiv)" in titles
        assert "Math Thema 2 (aktiv)" in titles
        
        # Sollte globale knowledge-Knoten enthalten
        assert "Globaler Wissensknoten" in titles
        assert "Schulweiter Wissensknoten" in titles
        
        # Sollte Physik-Knoten NICHT enthalten
        assert "Physik Thema 1" not in titles
        
        # Sollte private Knoten von teacher1 NICHT enthalten (die haben keine group_id)
        assert "Privater Knoten Teacher1" not in titles

    @pytest.mark.asyncio
    async def test_list_nodes_group_id_filter(self, test_client, teacher_headers, phase4_node_ids):
        """Nur Knoten mit genau dieser read_scope_group_id."""
        resp = await test_client.get(
            f"/context/nodes?group_id={MATH_GROUP_1['id']}",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Sollte Knoten aus Gruppe 200 enthalten
        titles = [n["title"] for n in data]
        assert "Math Thema 1 (aktiv)" in titles
        # "Math Thema 1 (archiviert)" not returned without status=archived

        # Sollte Knoten aus Gruppe 201 NICHT enthalten
        assert "Math Thema 2 (aktiv)" not in titles
        
        # Sollte globale Knoten NICHT enthalten
        assert "Globaler Wissensknoten" not in titles

    @pytest.mark.asyncio
    async def test_list_nodes_owner_me_archived(self, test_client, teacher_headers, phase4_node_ids):
        """status=archived&owner=me liefert nur eigene archivierte Knoten."""
        resp = await test_client.get(
            "/context/nodes?status=archived&owner=me",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Sollte archivierte Knoten von teacher1 enthalten
        titles = [n["title"] for n in data]
        assert "Math Thema 1 (archiviert)" in titles
        assert "Copy-Quelle (archiviert)" in titles
        
        # Sollte archivierte Knoten von teacher2 NICHT enthalten
        assert "Math Thema 2 alt (teacher2)" not in titles
        
        # Sollte aktive Knoten NICHT enthalten
        assert "Math Thema 1 (aktiv)" not in titles

    @pytest.mark.asyncio
    async def test_list_nodes_owner_not_me_rejected(self, test_client, teacher_headers):
        """owner=anderes_pseudonym → 400."""
        resp = await test_client.get(
            "/context/nodes?owner=someone_else",
            headers=teacher_headers,
        )
        assert resp.status_code == 400
        assert "owner muss 'me' sein" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_nodes_status_archived(self, test_client, teacher_headers, phase4_node_ids):
        """status=archived liefert alle archivierten Knoten (mit Sichtbarkeitsfilter)."""
        resp = await test_client.get(
            "/context/nodes?status=archived",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        
        titles = [n["title"] for n in data]
        # Sollte archivierte Knoten enthalten (Math Thema 1 gehört teacher1 → über Owner sichtbar)
        assert "Math Thema 1 (archiviert)" in titles
        assert "Copy-Quelle (archiviert)" in titles
        # teacher2's Gruppen-Knoten (MATH_GROUP_2) ist für teacher1 NICHT sichtbar: teacher1 ist
        # kein Mitglied dieser Gruppe → group-Knoten nur für Mitglieder (Sicherheits-Audit #1).
        assert "Math Thema 2 alt (teacher2)" not in titles

        # Sollte aktive Knoten NICHT enthalten
        assert "Math Thema 1 (aktiv)" not in titles

    @pytest.mark.asyncio
    async def test_list_nodes_status_active_default(self, test_client, teacher_headers, phase4_node_ids):
        """Ohne status-Parameter: nur aktive Knoten (Default-Verhalten)."""
        resp = await test_client.get(
            "/context/nodes",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        
        titles = [n["title"] for n in data]
        # Sollte aktive Knoten enthalten
        assert "Math Thema 1 (aktiv)" in titles
        assert "Math Thema 2 (aktiv)" in titles
        
        # Sollte archivierte Knoten NICHT enthalten
        assert "Math Thema 1 (archiviert)" not in titles



class TestNeighborhood:
    """Tests für GET /context/nodes/{id}/neighborhood."""

    @pytest.mark.asyncio
    async def test_neighborhood_depth1(self, test_client, teacher_headers, phase4_node_ids):
        """depth=1 liefert nur direkte Nachbarn, kein transitives Hop."""
        node_a_id = phase4_node_ids["neighborhood_a"]
        resp = await test_client.get(
            f"/context/nodes/{node_a_id}/neighborhood?depth=1",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Sollte Knoten A, B, C enthalten (A ist Zentrum, B und C sind direkte Nachbarn)
        node_titles = {n["title"] for n in data["nodes"]}
        assert "Neighborhood Zentrum" in node_titles
        assert "Nachbar B" in node_titles
        assert "Nachbar C" in node_titles
        
        # Sollte Knoten D NICHT enthalten (2 Hops entfernt)
        assert "Nachbar D" not in node_titles
        
        # Sollte Kanten zwischen A-B und A-C enthalten
        edge_count = len(data["edges"])
        assert edge_count >= 2  # A->B und C->A

    @pytest.mark.asyncio
    async def test_neighborhood_depth2(self, test_client, teacher_headers, phase4_node_ids):
        """depth=2 liefert auch 2-Hop-Nachbarn."""
        node_a_id = phase4_node_ids["neighborhood_a"]
        resp = await test_client.get(
            f"/context/nodes/{node_a_id}/neighborhood?depth=2",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Sollte Knoten A, B, C, D enthalten
        node_titles = {n["title"] for n in data["nodes"]}
        assert "Neighborhood Zentrum" in node_titles
        assert "Nachbar B" in node_titles
        assert "Nachbar C" in node_titles
        assert "Nachbar D" in node_titles

    @pytest.mark.asyncio
    async def test_neighborhood_node_not_found(self, test_client, teacher_headers):
        """404 wenn Startknoten nicht existiert."""
        fake_uuid = str(_uuid.uuid4())
        resp = await test_client.get(
            f"/context/nodes/{fake_uuid}/neighborhood",
            headers=teacher_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_neighborhood_with_category_filter(self, test_client, teacher_headers, phase4_node_ids):
        """category-Filter reduziert die zurückgegebenen Knoten."""
        node_a_id = phase4_node_ids["neighborhood_a"]
        resp = await test_client.get(
            f"/context/nodes/{node_a_id}/neighborhood?category=concept",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Alle Nachbarn sind 'concept', also sollte alles enthalten sein
        for node in data["nodes"]:
            assert node["category"] == "concept"

    @pytest.mark.asyncio
    async def test_neighborhood_with_relation_filter(self, test_client, teacher_headers, phase4_node_ids):
        """relation-Filter reduziert die zurückgegebenen Kanten."""
        node_a_id = phase4_node_ids["neighborhood_a"]
        resp = await test_client.get(
            f"/context/nodes/{node_a_id}/neighborhood?relation=references",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Alle Kanten in unserem Test sind 'references' oder 'part_of'
        # Also sollte nur die references-Kanten enthalten sein
        for edge in data["edges"]:
            assert edge["relation"] == "references"



class TestArchivedReferences:
    """Tests für GET /context/nodes/{id}/archived-references."""

    @pytest.mark.asyncio
    async def test_archived_references(self, test_client, teacher_headers, phase4_node_ids):
        """Korrekte Ergebnis-Liste mit archivierten Knoten + optionalem Nachfolger."""
        # archived_source hat eine Kante zu archived_target
        node_source_id = phase4_node_ids["archived_source"]
        resp = await test_client.get(
            f"/context/nodes/{node_source_id}/archived-references",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Sollte archived_target enthalten
        assert len(data) == 1
        assert data[0]["title"] == "Ziel archiviert"
        assert data[0]["relation"] == "references"
        assert data[0]["suggested_successor_id"] == phase4_node_ids["archived_successor"]

    @pytest.mark.asyncio
    async def test_archived_references_empty(self, test_client, teacher_headers, phase4_node_ids):
        """[] wenn keine archivierten Referenzen."""
        # Ein Knoten ohne ausgehende Kanten zu archivierten Knoten
        node_id = phase4_node_ids["math1_active"]
        resp = await test_client.get(
            f"/context/nodes/{node_id}/archived-references",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_archived_references_node_not_found(self, test_client, teacher_headers):
        """404 wenn Startknoten nicht existiert."""
        fake_uuid = str(_uuid.uuid4())
        resp = await test_client.get(
            f"/context/nodes/{fake_uuid}/archived-references",
            headers=teacher_headers,
        )
        assert resp.status_code == 404



class TestCopyNode:
    """Tests für POST /context/nodes/{id}/copy."""

    @pytest.mark.asyncio
    async def test_copy_node(self, test_client, teacher_headers, phase4_node_ids):
        """Kopie hat status=active, gleichen Inhalt, neues schuljahr."""
        node_id = phase4_node_ids["copy_source"]
        resp = await test_client.post(
            f"/context/nodes/{node_id}/copy",
            json={
                "schuljahr": "2025/26",
                "valid_until": "2026-06-30",
                "read_scope_group_id": MATH_GROUP_2["id"],
            },
            headers=teacher_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        
        # Prüfe Eigenschaften der Kopie
        assert data["status"] == "active"
        assert data["title"] == "Copy-Quelle"
        assert data["content"] == "Inhalt zum Kopieren"
        assert data["category"] == "knowledge"
        assert data["content_type"] == "themengebiet"
        assert data["owner_pseudonym"] == TEACHER1_PSEUDO
        assert data["schuljahr"] == "2025/26"
        assert data["read_scope_group_id"] == MATH_GROUP_2["id"]
        assert data["id"] != node_id

    @pytest.mark.asyncio
    async def test_copy_archived_node(self, test_client, teacher_headers, phase4_node_ids):
        """Auch archivierte Knoten können kopiert werden → Kopie ist active."""
        node_id = phase4_node_ids["copy_source_archived"]
        resp = await test_client.post(
            f"/context/nodes/{node_id}/copy",
            json={},
            headers=teacher_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        
        # Kopie sollte active sein
        assert data["status"] == "active"
        assert data["title"] == "Copy-Quelle (archiviert)"
        assert data["content"] == "Archivierter Inhalt"

    @pytest.mark.asyncio
    async def test_copy_node_not_found(self, test_client, teacher_headers):
        """404 wenn Quellknoten nicht existiert."""
        fake_uuid = str(_uuid.uuid4())
        resp = await test_client.post(
            f"/context/nodes/{fake_uuid}/copy",
            json={},
            headers=teacher_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_copy_node_preserves_metadata(self, test_client, teacher_headers, phase4_node_ids):
        """metadata wird korrekt kopiert."""
        node_id = phase4_node_ids["copy_source"]
        resp = await test_client.post(
            f"/context/nodes/{node_id}/copy",
            json={},
            headers=teacher_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        
        # Original hat metadata {"test": "value"}
        assert data["metadata"] == {"test": "value"}



class TestLifecycleRoundtrip:
    """Tests für Status-Übergänge."""

    @pytest.mark.asyncio
    async def test_lifecycle_roundtrip(self, test_client, teacher_headers, phase4_node_ids):
        """PATCH status=archived → active; kein 403 für Eigentümer."""
        # Erst einen eigenen Knoten erstellen
        create_resp = await test_client.post(
            "/context/nodes",
            json={
                "category": "concept",
                "content_type": "abstrakt",
                "title": "Test Lifecycle",
                "content": "Test Inhalt",
            },
            headers=teacher_headers,
        )
        assert create_resp.status_code == 201
        node_id = create_resp.json()["id"]
        
        # Status auf archived setzen
        patch_resp = await test_client.patch(
            f"/context/nodes/{node_id}",
            json={"status": "archived"},
            headers=teacher_headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "archived"
        
        # Status zurück auf active setzen
        patch_resp2 = await test_client.patch(
            f"/context/nodes/{node_id}",
            json={"status": "active"},
            headers=teacher_headers,
        )
        assert patch_resp2.status_code == 200
        assert patch_resp2.json()["status"] == "active"
