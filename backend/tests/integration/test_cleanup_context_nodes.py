"""Kontolöschung und eigene Wissensbausteine — M2 (entschieden 07.09.2026).

Bis dahin fasste `cleanup_inactive_accounts` die `context_nodes` **gar nicht** an: Ein
Baustein einer ausgeschiedenen Person blieb samt Pseudonym unbegrenzt stehen — ein
personenbezogenes Datum ohne Frist. Der Wächtertest `test_pseudonym_deletion_coverage`
führte die Tabelle deshalb als `OFFEN`.

Die Regel trennt nach `read_scope`, nicht nach Eigentum:

- **`private`** — konnte nie jemand anders sehen, wird mit dem Konto gelöscht.
- **alles andere** — bleibt stehen und verliert nur den Namen. Ein Arbeitsblatt, das
  eine Klasse liest, verschwinden zu lassen, risse in fremde Planungen ein Loch.

Geprüft wird gegen die echte Datenbank, nicht gegen Mocks: Die Aussage steckt in der
SQL-Semantik — welche Zeile welches `WHERE` trifft —, nicht im Kontrollfluss.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import psycopg2
import pytest

VERLASSEN = "verlassen-m2"
AKTIV = "aktiv-m2"

# Der Lauf löscht *jedes* Konto jenseits der 90 Tage — auch fremde Testdaten in
# derselben DB. Deshalb liegt der Stichtag im Jahr 2000: Nur das eigens angelegte
# Konto ist älter, alles andere bleibt außerhalb der Reichweite dieses Tests.
STICHTAG = datetime(2000, 6, 1, tzinfo=timezone.utc)
LANGE_HER = datetime(1999, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def sync_conn(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield conn
    conn.close()


def _node(cur, titel, *, owner, read_scope, content_type="arbeitsblatt", gruppe=None):
    nid = uuid.uuid4()
    cur.execute(
        "INSERT INTO context_nodes (id, category, content_type, title, owner_pseudonym,"
        " read_scope, read_scope_group_id, write_scope, status)"
        " VALUES (%s, 'artifact', %s, %s, %s, %s, %s, 'private', 'active')",
        (str(nid), content_type, titel, owner, read_scope, gruppe),
    )
    return nid


@pytest.fixture
def bestand(sync_conn, seed_test_group):
    """Ein verlassenes Konto mit drei Bausteinen, ein aktives zur Gegenprobe."""
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pseudonym_audit (pseudonym, role, roles, last_login_at)"
            " VALUES (%s,'teacher','[\"teacher\"]',%s), (%s,'teacher','[\"teacher\"]',%s)"
            " ON CONFLICT (pseudonym) DO UPDATE SET last_login_at = EXCLUDED.last_login_at",
            (VERLASSEN, LANGE_HER, AKTIV, datetime.now(timezone.utc)),
        )
        ids = {
            "privat": _node(cur, "Klausurentwurf", owner=VERLASSEN, read_scope="private"),
            "gruppe": _node(cur, "Arbeitsblatt der 8c", owner=VERLASSEN,
                            read_scope="group", gruppe=seed_test_group),
            "schule": _node(cur, "Lerntext Bruchrechnen", owner=VERLASSEN,
                            read_scope="school", content_type="lerntext"),
            "fremd": _node(cur, "Blatt der Kollegin", owner=AKTIV, read_scope="private"),
        }
    sync_conn.commit()
    yield ids
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        for nid in ids.values():
            cur.execute("DELETE FROM context_nodes WHERE id = %s", (str(nid),))
        cur.execute("DELETE FROM pseudonym_audit WHERE pseudonym IN (%s,%s)",
                    (VERLASSEN, AKTIV))
    sync_conn.commit()


def _zustand(conn, node_id):
    """(existiert, owner_pseudonym) — aus einer frischen Transaktion gelesen."""
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("SELECT owner_pseudonym FROM context_nodes WHERE id = %s", (str(node_id),))
        zeile = cur.fetchone()
    return (zeile is not None, zeile[0] if zeile else None)


@pytest.fixture
async def gelaufen(async_engine, bestand):
    """Führt den Löschlauf aus — ohne LiteLLM, das hier nichts beiträgt."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.crons.cleanup_service import cleanup_inactive_accounts

    with patch("app.crons.cleanup_service.LiteLLMClient") as klient:
        klient.return_value.delete_user = AsyncMock()
        klient.return_value.delete_key = AsyncMock()
        klient.return_value.close = AsyncMock()
        session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
        async with session_factory() as session:
            stats = await cleanup_inactive_accounts(session, now=STICHTAG)
    assert stats.deleted_local == 1, "Genau das verlassene Konto sollte gelöscht werden"
    return bestand


async def test_privates_wird_geloescht(sync_conn, gelaufen):
    """Niemand sonst konnte es sehen — Löschen zerstört nichts Gemeinsames."""
    existiert, _ = _zustand(sync_conn, gelaufen["privat"])
    assert not existiert


async def test_geteiltes_bleibt_und_verliert_den_namen(sync_conn, gelaufen):
    """Der Kern der Entscheidung: Das Arbeitsergebnis gehört der Schule, der
    Personenbezug nicht."""
    for schluessel in ("gruppe", "schule"):
        existiert, eigner = _zustand(sync_conn, gelaufen[schluessel])
        assert existiert, f"{schluessel}: Baustein verschwunden"
        assert eigner is None, f"{schluessel}: Pseudonym steht noch dran"


async def test_fremdes_konto_bleibt_unberuehrt(sync_conn, gelaufen):
    """Die Gegenprobe — ein aktives Konto darf der Lauf nicht anfassen."""
    existiert, eigner = _zustand(sync_conn, gelaufen["fremd"])
    assert existiert
    assert eigner == AKTIV


async def test_kein_pseudonym_bleibt_zurueck(sync_conn, gelaufen):
    """Die Zusage, um die es geht: Nach dem Lauf verweist kein Baustein mehr auf
    das gelöschte Konto — weder ein privater noch ein geteilter."""
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM context_nodes WHERE owner_pseudonym = %s",
                    (VERLASSEN,))
        assert cur.fetchone()[0] == 0
