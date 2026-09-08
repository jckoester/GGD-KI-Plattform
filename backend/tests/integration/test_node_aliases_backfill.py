"""Der Backfill der Migration 0057 — gegen gesetzte Daten, nicht gegen ein leeres Schema.

Die Testdatenbank wird zu Sitzungsbeginn leer aufgebaut; die Migration liefe dort über
einen leeren Bestand. Ausgerechnet dieser Teil läuft aber **genau einmal**, und zwar
gegen die echten Daten der Schule: Wenn er die Reihenfolge verdreht, ändert sich der
Embedding-Input von `methode` und `operator`, und deren Vektoren sind still nicht mehr
vergleichbar. Deshalb führt dieser Test dasselbe SQL aus, das die Migration ausführt —
importiert, nicht abgeschrieben.
"""
import importlib.util
import uuid
from pathlib import Path

import psycopg2
import pytest

_MIGRATION = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0057_node_aliases.py"
)


def _lade_migration():
    """Per Pfad geladen — `0057_node_aliases` ist kein gültiger Modulname."""
    spec = importlib.util.spec_from_file_location("migration_0057", _MIGRATION)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="module")
def sql():
    return _lade_migration()


@pytest.fixture(scope="module")
def conn(db_url, run_migrations):
    verbindung = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield verbindung
    verbindung.close()


@pytest.fixture
def knoten(conn):
    """Ein Knoten mit Aliasen in den Metadaten — der Zustand vor der Migration."""
    nid = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO context_nodes (id, category, content_type, title, read_scope,"
            " write_scope, status, metadata)"
            " VALUES (%s,'knowledge','methode','Ich-Du-Wir','school','school','active',"
            " %s::jsonb)",
            (
                str(nid),
                # Reihenfolge absichtlich nicht alphabetisch. „  think-pair-share " ist
                # die Dublette — die Normalisierung faltet Groß-/Kleinschreibung und
                # Leerraum, **nicht** Bindestriche: „think pair share" wäre unter dieser
                # Regel ein eigener Name, genau wie bei Titeln. Diese Lücke schließt die
                # Ähnlichkeitsstufe der Suche, nicht die Normalisierung.
                # Der leere Eintrag und der Zusatzschlüssel prüfen die Filter.
                '{"aliase": ["Think-Pair-Share", "Murmelphase", "  think-pair-share ", "  "],'
                ' "ablauf": "erst allein, dann zu zweit"}',
            ),
        )
    conn.commit()
    yield nid
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE id = %s", (str(nid),))
    conn.commit()


@pytest.fixture
def gelaufen(conn, sql, knoten):
    with conn.cursor() as cur:
        cur.execute(sql.BACKFILL_SQL)
        cur.execute(sql.AUFRAEUMEN_SQL)
    conn.commit()
    return knoten


def _aliase(conn, nid):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT alias FROM node_aliases WHERE node_id = %s ORDER BY id", (str(nid),)
        )
        return [z[0] for z in cur.fetchall()]


def test_reihenfolge_bleibt_erhalten(conn, gelaufen):
    """Der Kern: Nach `id` gelesen steht die Array-Reihenfolge da, nicht die alphabetische.

    Daran hängt, ob die bestehenden Embeddings von `methode` und `operator` gültig
    bleiben — der Eingabetext ist aus genau dieser Folge zusammengesetzt.
    """
    assert _aliase(conn, gelaufen) == ["Think-Pair-Share", "Murmelphase"]


def test_dubletten_und_leeres_fallen_weg(conn, gelaufen):
    """„  think-pair-share " ist nach der Normalisierung derselbe Alias — der
    Unique-Index wiese ihn zurück, der Backfill fängt ihn vorher ab. Ein leerer Eintrag
    ist kein Name."""
    aliase = _aliase(conn, gelaufen)
    assert len(aliase) == 2
    assert not any(a.strip() == "" for a in aliase)


def test_metadaten_schluessel_ist_weg(conn, gelaufen):
    """Zwei Wahrheiten für dieselbe Sache wären schlimmer als eine unbequeme."""
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("SELECT metadata FROM context_nodes WHERE id = %s", (str(gelaufen),))
        metadaten = cur.fetchone()[0]
    assert "aliase" not in metadaten
    assert metadaten["ablauf"] == "erst allein, dann zu zweit", "Fremdes mitgelöscht"


def test_zweiter_lauf_bricht_nicht(conn, sql, gelaufen):
    """Idempotenz: Der Aufräum-Schritt nimmt der Quelle die Grundlage, ein erneuter
    Backfill findet nichts mehr — und darf nicht am Unique-Index scheitern."""
    with conn.cursor() as cur:
        cur.execute(sql.BACKFILL_SQL)
    conn.commit()
    assert _aliase(conn, gelaufen) == ["Think-Pair-Share", "Murmelphase"]
