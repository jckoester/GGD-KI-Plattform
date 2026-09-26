"""Die Relation `is_a` in der Datenbank (Paket 9, AP2).

⚠️ **Gegen die echte Bedingung, nicht gegen die Konstante.** `ERLAUBTE_RELATIONEN` in
`app/context/metadata.py` ist eine Zusage der Anwendung; durchgesetzt wird sie vom
CHECK-Constraint `check_context_edges_relation`. Beide sind schon einmal auseinander
gewesen (Alembic 0056 strich `reflects_on`), und ein Test gegen die Konstante hätte das
nicht bemerkt.

Der Wert der Kante steht in ADR-013: Hierarchie ist eine eigene Beziehungsart, weil
Graphansicht und Traversierung nach Relationstyp filtern. Ein `related_to` mit
Kanten-Metadata wäre nur daneben filterbar.
"""
import uuid

import psycopg2
import pytest

from app.context.metadata import ERLAUBTE_RELATIONEN

pytestmark = pytest.mark.asyncio

TITEL = ("ISA Natriumchlorid", "ISA Salz")


@pytest.fixture
def conn(db_url, run_migrations):
    verbindung = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield verbindung
    with verbindung.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE title = ANY(%s)", (list(TITEL),))
    verbindung.commit()
    verbindung.close()


def _knoten(cur, titel):
    knoten_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO context_nodes (id, category, content_type, title, content,"
        " read_scope, write_scope, status)"
        # `write_scope = 'school'`, nicht `subject`: Letzteres verlangt eine
        # Fachschaftsgruppe (`check_context_nodes_write_group_id`), und um die geht es
        # hier nicht.
        " VALUES (%s, 'concept', 'begriff', %s, 'x', 'school', 'school', 'active')",
        (knoten_id, titel),
    )
    return knoten_id


def test_is_a_kante_laesst_sich_anlegen(conn):
    with conn.cursor() as cur:
        unten, oben = (_knoten(cur, t) for t in TITEL)
        cur.execute(
            "INSERT INTO context_edges (from_node_id, to_node_id, relation, metadata)"
            " VALUES (%s, %s, 'is_a', '{}'::jsonb)",
            (unten, oben),
        )
        cur.execute(
            "SELECT relation FROM context_edges WHERE from_node_id = %s", (unten,)
        )
        assert cur.fetchone()[0] == "is_a"
    conn.commit()


def test_unbekannte_relationen_bleiben_abgewiesen(conn):
    """Die Gegenprobe: Der Constraint ist nicht weggefallen, sondern gewachsen."""
    with conn.cursor() as cur:
        unten, oben = (_knoten(cur, t) for t in TITEL)
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                "INSERT INTO context_edges (from_node_id, to_node_id, relation, metadata)"
                " VALUES (%s, %s, 'ist_ein', '{}'::jsonb)",
                (unten, oben),
            )
    conn.rollback()


def test_anwendung_und_datenbank_kennen_dieselben_relationen(conn):
    """⚠️ Der eigentliche Wächter.

    Eine Relation, die nur die Anwendung kennt, scheitert beim Speichern; eine, die nur
    die Datenbank kennt, bietet niemand an. Beides fällt erst auf, wenn es jemand
    versucht.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conname = 'check_context_edges_relation'"
        )
        zeile = cur.fetchone()
    conn.rollback()
    assert zeile, "Die Bedingung `check_context_edges_relation` fehlt in der Datenbank"

    import re

    in_der_db = set(re.findall(r"'(\w+)'::text", zeile[0]))
    assert in_der_db == set(ERLAUBTE_RELATIONEN), (
        f"Datenbank: {sorted(in_der_db)} · Anwendung: {sorted(ERLAUBTE_RELATIONEN)}"
    )
