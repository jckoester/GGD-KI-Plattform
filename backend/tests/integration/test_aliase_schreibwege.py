"""Weitere Namen landen in `node_aliases`, nicht im toten `metadata.aliase` (0.13.1).

Migration 0057 (0.9.0) hat die Aliase in eine eigene Tabelle gelegt und das Metadatenfeld
geleert. Drei Wege schrieben bis 0.13.0 weiter dorthin, wo niemand mehr liest — weder die
Suche noch der Namensfilter noch der Embedding-Input:

- der Bildungsplan-Import (die Operator-Synonyme aus dem JSONL),
- der Methodik-Seed (Probelauf gegen Dev am 04.10.2026: „12 aktualisiert, 9 Vektoren
  verworfen", die Tabelle blieb unberührt),
- `POST/PATCH /context/nodes`.

Dazu `aliase.nachziehen()`, das einmal einsammelt, was bis dahin dort gelandet ist.
"""
import importlib.util
import json
import sys
from pathlib import Path

import psycopg2
import pytest
import sqlalchemy as sa

from app.context import aliase as aliase_modul
from app.db.models import ContextNode

_REPO = Path(__file__).resolve().parents[3]
PRAEFIX = "ALIASTEST_"


def _sync(db_url):
    return db_url.replace("postgresql+asyncpg://", "postgresql://")


def _lade(name, pfad):
    spec = importlib.util.spec_from_file_location(name, pfad)
    modul = importlib.util.module_from_spec(spec)
    sys.modules[name] = modul
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="module")
def bp_import():
    return _lade("_import_bildungsplan_aliase", _REPO / "scripts" / "import_bildungsplan.py")


@pytest.fixture(scope="module")
def seed():
    return _lade("_seed_methodik_aliase", _REPO / "backend" / "scripts" / "seed_methodik.py")


@pytest.fixture
def cur(db_url, run_migrations):
    """psycopg2 wie im Import selbst — die Knoten werden vorher und nachher entfernt."""
    conn = psycopg2.connect(_sync(db_url))
    conn.autocommit = True
    cursor = conn.cursor()
    loesche = f"DELETE FROM context_nodes WHERE metadata->>'bp_id' LIKE '{PRAEFIX}%%'"
    cursor.execute(loesche)
    yield cursor
    cursor.execute(loesche)
    conn.close()


def _breite(cur) -> int:
    cur.execute(
        "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'context_nodes'::regclass "
        "AND attname = 'embedding'"
    )
    return cur.fetchone()[0]


def _vektor(breite: int) -> str:
    return "[" + ",".join(["0.1"] * breite) + "]"


def _aliase(cur, node_id) -> list[str]:
    cur.execute("SELECT alias FROM node_aliases WHERE node_id = %s ORDER BY id", (str(node_id),))
    return [z[0] for z in cur.fetchall()]


def _zustand(cur, node_id):
    """(Metadaten, hat einen Vektor)"""
    cur.execute(
        "SELECT metadata, embedding IS NOT NULL FROM context_nodes WHERE id = %s",
        (str(node_id),),
    )
    return cur.fetchone()


def _operator(bp_id, aliase, content_hash="h1"):
    return {
        "bp_id": bp_id, "type": "knowledge", "content_type": "operator",
        "title": f"{bp_id} darstellen", "content": "Sachverhalte strukturiert wiedergeben.",
        "content_hash": content_hash, "visibility": "global",
        "metadata": {"afb": ["I"], "aliase": aliase},
    }


# ── Bildungsplan-Import ──────────────────────────────────────────────────────


def test_import_legt_operator_aliase_in_die_tabelle(bp_import, cur):
    knoten = _operator(f"{PRAEFIX}OP_01", ["beschreiben", "Beschreiben", " ", "erläutern"])
    ergebnis, node_id = bp_import.upsert_node(cur, knoten, False, {})

    assert ergebnis == "inserted"
    # Dublette in anderer Schreibweise und Leeres fallen weg, die Reihenfolge bleibt.
    assert _aliase(cur, node_id) == ["beschreiben", "erläutern"]
    assert "aliase" not in _zustand(cur, node_id)[0]


def test_import_holt_aliase_aus_dem_toten_feld_und_behaelt_eigene(bp_import, cur):
    """Der Fall der Produktion: Ein Import zwischen 0.9.0 und 0.13.0 hat die Synonyme
    in `metadata.aliase` gelegt, die Tabelle ist leer, der Vektor entstand ohne sie.

    Der nächste Import läuft über den Pfad „Hash unverändert" — und dessen
    Metadaten-UPDATE räumt das tote Feld weg. Ohne das Ergänzen wären die Synonyme
    danach verloren.
    """
    bp_id = f"{PRAEFIX}OP_02"
    vektor = _vektor(_breite(cur))
    cur.execute(
        "INSERT INTO context_nodes (category, content_type, title, content, metadata, "
        "read_scope, write_scope, status, embedding) "
        "VALUES ('knowledge', 'operator', %s, 'x', %s, 'global', 'global', 'active', %s) "
        "RETURNING id",
        (f"{bp_id} erklären",
         json.dumps({"bp_id": bp_id, "content_hash": "h2", "aliase": ["erläutern", "deuten"]}),
         vektor),
    )
    node_id = cur.fetchone()[0]

    knoten = _operator(bp_id, ["erläutern", "deuten"], content_hash="h2")
    assert bp_import.upsert_node(cur, knoten, False, {})[0] == "skipped"
    metadaten, hat_vektor = _zustand(cur, node_id)
    assert _aliase(cur, node_id) == ["erläutern", "deuten"]
    assert "aliase" not in metadaten
    assert not hat_vektor  # entstand ohne die Synonyme

    # Ein im Editor ergänzter Name überlebt den nächsten Lauf, und weil sich nichts
    # ändert, bleibt auch der inzwischen neu gerechnete Vektor.
    cur.execute("INSERT INTO node_aliases (node_id, alias) VALUES (%s, 'auslegen')", (str(node_id),))
    cur.execute("UPDATE context_nodes SET embedding = %s WHERE id = %s", (vektor, str(node_id)))
    assert bp_import.upsert_node(cur, knoten, False, {})[0] == "skipped"
    assert _aliase(cur, node_id) == ["erläutern", "deuten", "auslegen"]
    assert _zustand(cur, node_id)[1]


# ── Methodik-Seed ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_seed_schreibt_aliase_in_die_tabelle(seed, db_session):
    baustein = seed.Baustein(
        "AliasSeedTest", ("Ich-Du-Wir-Probe",), content="Erst allein, dann zu zweit."
    )
    await seed._upsert(db_session, "methode", baustein, seed.Bilanz(), ueberschreiben=False)
    knoten = (await db_session.execute(
        sa.select(ContextNode).where(ContextNode.title == "AliasSeedTest")
    )).scalar_one()

    assert await aliase_modul.lade(db_session, knoten.id) == ["Ich-Du-Wir-Probe"]
    assert "aliase" not in (knoten.metadata_ or {})

    # Bis 0.13.0 las der Seed das leere Metadatenfeld und hielt jeden Lauf für den ersten.
    zweiter = seed.Bilanz()
    await seed._upsert(db_session, "methode", baustein, zweiter, ueberschreiben=False)
    assert (zweiter.aktualisiert, zweiter.unveraendert) == (0, 1)

    # Was die Schule gepflegt hat, bleibt.
    await aliase_modul.setze(db_session, knoten.id, ["Eigene Bezeichnung"])
    dritter = seed.Bilanz()
    await seed._upsert(db_session, "methode", baustein, dritter, ueberschreiben=False)
    assert await aliase_modul.lade(db_session, knoten.id) == ["Eigene Bezeichnung"]
    assert dritter.behalten


# ── API ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_weist_aliase_in_den_metadaten_ab(test_client, auth_headers):
    neu = {
        "category": "knowledge", "content_type": "methode", "title": "AliasApiTest",
        "content": "Erst allein, dann zu zweit.", "read_scope": "school",
    }
    resp = await test_client.post(
        "/context/nodes", json={**neu, "metadata": {"aliase": ["Ich-Du-Wir"]}},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "aliase" in resp.json()["detail"]

    resp = await test_client.post("/context/nodes", json=neu, headers=auth_headers)
    assert resp.status_code == 201
    resp = await test_client.patch(
        f"/context/nodes/{resp.json()['id']}",
        json={"metadata": {"aliase": ["Ich-Du-Wir"]}}, headers=auth_headers,
    )
    assert resp.status_code == 422


# ── Nachziehen ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_nachziehen_ergaenzt_raeumt_und_verwirft_nur_betroffene_vektoren(db_session):
    breite = (await db_session.execute(sa.text(
        "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'context_nodes'::regclass "
        "AND attname = 'embedding'"
    ))).scalar_one()

    def knoten(titel, content_type, aliase):
        return ContextNode(
            category="knowledge", content_type=content_type, title=titel, content="x",
            read_scope="global", write_scope="global", status="active",
            metadata_={"aliase": aliase}, embedding=[0.1] * breite,
        )

    operator = knoten("NachzugOperator", "operator", ["erklären", "Erklären", "deuten"])
    # Ein Typ, dessen Vektor die Aliase nicht enthält — er behält ihn.
    leitidee = knoten("NachzugLeitidee", "leitidee", ["Zahl"])
    db_session.add_all([operator, leitidee])
    await db_session.flush()
    await aliase_modul.setze(db_session, operator.id, ["erläutern"])
    await db_session.flush()
    op_id, li_id = operator.id, leitidee.id

    await aliase_modul.nachziehen(db_session)
    db_session.expire_all()

    # Ergänzt hinter dem, was schon in der Tabelle stand; die Dublette fällt weg.
    assert await aliase_modul.lade(db_session, op_id) == ["erläutern", "erklären", "deuten"]
    assert await aliase_modul.lade(db_session, li_id) == ["Zahl"]
    operator, leitidee = await db_session.get(ContextNode, op_id), await db_session.get(ContextNode, li_id)
    assert "aliase" not in operator.metadata_ and "aliase" not in leitidee.metadata_
    assert operator.embedding is None
    assert leitidee.embedding is not None

    zweiter = await aliase_modul.nachziehen(db_session)
    assert (zweiter.knoten_mit_altfeld, zweiter.neue_aliase, zweiter.vektoren_verworfen) == (0, 0, 0)
