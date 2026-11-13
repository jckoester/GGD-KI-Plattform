"""Schüler-Bausteine in die Werkstatt überführen (0.41, Päckchen AN, Schritt 9).

Gegen echtes Postgres: `app.artifacts.schueler_wechsel.ueberfuehre`, der Kern von
`scripts/schueler_bausteine_ueberfuehren.py`. Testdaten über psycopg2, der Lauf über eine
eigene Sitzung (er committet je Baustein).
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.artifacts import schueler_wechsel as wechsel
from app.artifacts import store

pytestmark = pytest.mark.asyncio

SCHUELERIN = "an9-schuelerin"
LEHRKRAFT = "an9-lehrkraft"
FACH = 9631
JETZT = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def ablage(tmp_path, monkeypatch):
    monkeypatch.setattr(store.settings, "artifact_storage_dir", str(tmp_path))


@pytest.fixture
def conn(db_url, run_migrations):
    c = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))

    def aufraeumen():
        with c.cursor() as cur:
            cur.execute("DELETE FROM context_nodes WHERE owner_pseudonym = ANY(%s)", ([SCHUELERIN, LEHRKRAFT],))
            cur.execute("DELETE FROM artifacts WHERE owner_pseudonym = ANY(%s)", ([SCHUELERIN, LEHRKRAFT],))
            cur.execute("DELETE FROM pseudonym_audit WHERE pseudonym = ANY(%s)", ([SCHUELERIN, LEHRKRAFT],))
        c.commit()

    aufraeumen()
    with c.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name) VALUES (%s, 'an9', 'AN9') ON CONFLICT (id) DO NOTHING", (FACH,))
        cur.execute("INSERT INTO pseudonym_audit (pseudonym, role, roles, grade) VALUES (%s, 'student', %s, 7)",
                    (SCHUELERIN, json.dumps(["student"])))
        cur.execute("INSERT INTO pseudonym_audit (pseudonym, role, roles) VALUES (%s, 'teacher', %s)",
                    (LEHRKRAFT, json.dumps(["teacher"])))
    c.commit()
    yield c
    c.rollback()
    aufraeumen()
    with c.cursor() as cur:
        cur.execute("DELETE FROM subjects WHERE id = %s", (FACH,))
    c.commit()
    c.close()


@pytest.fixture
def sitzung(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    return fabrik


def _produkt(conn, *, titel="Mein Text", fach=None, owner=SCHUELERIN, groesse=10):
    pid = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO artifacts (id, owner_pseudonym, kind, mime_type, byte_size, title, source, subject_id,"
            " created_at, updated_at, expires_at) VALUES (%s, %s, 'document', 'text/markdown', %s, %s, 'x', %s,"
            " %s, %s, %s)",
            (str(pid), owner, groesse, titel, fach, JETZT, JETZT, JETZT + timedelta(days=300)),
        )
    conn.commit()
    return pid


def _baustein(conn, typ="schuelertext", *, owner=SCHUELERIN, titel="Baustein", inhalt="# Text",
              quelle=None, fach=None):
    nid = uuid.uuid4()
    meta = {"source_artifact_id": str(quelle)} if quelle else {}
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO context_nodes (id, category, content_type, title, content, read_scope, write_scope,"
            " owner_pseudonym, status, metadata, subject_id) VALUES (%s, 'artifact', %s, %s, %s, 'private',"
            " 'private', %s, 'active', %s::jsonb, %s)",
            (str(nid), typ, titel, inhalt, owner, json.dumps(meta), fach),
        )
    conn.commit()
    return nid


def _gibt_es(conn, node_id):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM context_nodes WHERE id = %s", (str(node_id),))
        return cur.fetchone()[0] == 1


def _produkte(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT title, subject_id, source FROM artifacts WHERE owner_pseudonym = %s ORDER BY title",
                    (SCHUELERIN,))
        return cur.fetchall()


def _ausgang(bericht, node_id):
    return next(e.ausgang for e in bericht.eintraege if e.node_id == node_id)


async def test_mit_quellprodukt_fach_ans_produkt_baustein_weg(conn, sitzung):
    produkt = _produkt(conn, titel="Mein Text")
    nid = _baustein(conn, quelle=produkt, fach=FACH, titel="Anders benannt")

    async with sitzung() as db:
        bericht = await wechsel.ueberfuehre(db, dry_run=False)

    assert _ausgang(bericht, nid) == wechsel.PRODUKT_VORHANDEN
    assert not _gibt_es(conn, nid)
    # Fach war leer → übernommen; der Titel des Produkts war kein Platzhalter → bleibt.
    assert _produkte(conn) == [("Mein Text", FACH, "x")]


async def test_platzhaltertitel_wird_ersetzt(conn, sitzung):
    produkt = _produkt(conn, titel="Dokument", fach=FACH)
    _baustein(conn, quelle=produkt, titel="Lernplan Mathe", fach=None)

    async with sitzung() as db:
        await wechsel.ueberfuehre(db, dry_run=False)

    assert _produkte(conn) == [("Lernplan Mathe", FACH, "x")]


async def test_ohne_quellprodukt_wird_dokument_angelegt(conn, sitzung):
    nid = _baustein(conn, "lernplan", titel="Woche 1", inhalt="- Vokabeln", fach=FACH,
                    quelle=uuid.uuid4())  # Herkunft, die es nicht mehr gibt

    async with sitzung() as db:
        bericht = await wechsel.ueberfuehre(db, dry_run=False)

    assert _ausgang(bericht, nid) == wechsel.DOKUMENT_ANGELEGT
    assert not _gibt_es(conn, nid)
    assert _produkte(conn) == [("Woche 1", FACH, "- Vokabeln")]


async def test_fremdes_quellprodukt_zaehlt_nicht(conn, sitzung):
    fremd = _produkt(conn, owner=LEHRKRAFT, titel="Fremd")
    nid = _baustein(conn, quelle=fremd, titel="Meins", inhalt="Eigenes")

    async with sitzung() as db:
        bericht = await wechsel.ueberfuehre(db, dry_run=False)

    assert _ausgang(bericht, nid) == wechsel.DOKUMENT_ANGELEGT
    assert _produkte(conn) == [("Meins", None, "Eigenes")]


async def test_quota_laesst_baustein_stehen_und_laeuft_weiter(conn, sitzung, monkeypatch):
    monkeypatch.setattr(wechsel, "get_artifact_limits", lambda r, g: (365, 20))
    monkeypatch.setattr(store, "get_artifact_limits", lambda r, g: (365, 20))
    gross = _baustein(conn, titel="Groß", inhalt="x" * 50)
    klein = _baustein(conn, titel="Klein", inhalt="kurz")

    async with sitzung() as db:
        probe = await wechsel.ueberfuehre(db, dry_run=True)
    assert (_ausgang(probe, gross), _ausgang(probe, klein)) == (wechsel.QUOTA, wechsel.DOKUMENT_ANGELEGT)

    async with sitzung() as db:
        bericht = await wechsel.ueberfuehre(db, dry_run=False)

    assert _ausgang(bericht, gross) == wechsel.QUOTA
    assert _gibt_es(conn, gross)
    assert not _gibt_es(conn, klein)
    assert [p[0] for p in _produkte(conn)] == ["Klein"]


async def test_probelauf_aendert_nichts(conn, sitzung):
    produkt = _produkt(conn)
    mit = _baustein(conn, quelle=produkt, fach=FACH)
    ohne = _baustein(conn, "schuelerpraesentation", inhalt="Folien")

    async with sitzung() as db:
        bericht = await wechsel.ueberfuehre(db, dry_run=True)

    assert (_ausgang(bericht, mit), _ausgang(bericht, ohne)) == (
        wechsel.PRODUKT_VORHANDEN, wechsel.DOKUMENT_ANGELEGT)
    assert _gibt_es(conn, mit) and _gibt_es(conn, ohne)
    assert _produkte(conn) == [("Mein Text", None, "x")]


async def test_ohne_inhalt_bleibt_stehen(conn, sitzung):
    nid = _baustein(conn, inhalt="  ")
    async with sitzung() as db:
        bericht = await wechsel.ueberfuehre(db, dry_run=False)
    assert _ausgang(bericht, nid) == wechsel.OHNE_INHALT
    assert _gibt_es(conn, nid)


async def test_strukturierung_nur_gelistet_ausser_mit_schalter(conn, sitzung):
    schueler = _baustein(conn, "strukturierung", inhalt="- Gliederung")
    lehrkraft = _baustein(conn, "strukturierung", owner=LEHRKRAFT, inhalt="- Klassenmindmap")

    async with sitzung() as db:
        bericht = await wechsel.ueberfuehre(db, dry_run=False)
    assert _ausgang(bericht, schueler) == wechsel.NUR_GELISTET
    assert all(e.node_id != lehrkraft for e in bericht.eintraege)
    assert _gibt_es(conn, schueler)

    async with sitzung() as db:
        bericht = await wechsel.ueberfuehre(db, dry_run=False, mit_strukturierung=True)
    assert _ausgang(bericht, schueler) == wechsel.DOKUMENT_ANGELEGT
    assert not _gibt_es(conn, schueler)
    assert _gibt_es(conn, lehrkraft), "Gliederungen von Lehrkräften bleiben Bausteine"
