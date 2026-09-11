"""Was die Kontolöschung mit den persönlichen Daten macht — M2, entschieden 07./08.09.2026.

`cleanup_inactive_accounts` ließ fünf Tabellen unangetastet; der Wächtertest
`test_pseudonym_deletion_coverage` führte sie als `OFFEN` bzw. — bei `artifacts` — als
Beschreibung des Status quo. Alle fünf sind jetzt entschieden:

- **`context_nodes`** trennt nach `read_scope`, nicht nach Eigentum: `private` wird
  gelöscht, alles Übrige bleibt stehen und verliert nur den Namen. Ein Arbeitsblatt, das
  eine Klasse liest, verschwinden zu lassen, risse in fremde Planungen ein Loch.
- **`artifacts`** wird gelöscht, Zeilen **und Dateien**: Die Bibliothek ist strikt
  privat, damit gilt dieselbe Regel wie für einen privaten Baustein.
- **`node_engagement`**, **`group_memberships`**, **`teacher_group_exclusions`** gehen
  schlicht mit — persönliche Verlaufs-, Zugehörigkeits- und Ansichtsdaten ohne
  Fremdbezug.

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


SUBJECT_ID = 990001


@pytest.fixture
def artefakt_ablage(tmp_path, monkeypatch):
    """Artefakt-Bytes in ein Wegwerf-Verzeichnis, nicht nach `backend/data/`."""
    from app.artifacts import store

    monkeypatch.setattr(store.settings, "artifact_storage_dir", str(tmp_path))
    return store


def _artefakt(cur, store, titel, *, owner):
    """Eine Bibliothekszeile **samt Datei** — nur beides zusammen ist der echte Fall."""
    aid = uuid.uuid4()
    pfad = store._file_path(aid, "text/markdown")
    pfad.write_text(f"# {titel}\n", encoding="utf-8")
    cur.execute(
        "INSERT INTO artifacts (id, owner_pseudonym, kind, mime_type, byte_size, title,"
        " source, expires_at)"
        " VALUES (%s,%s,'document','text/markdown',%s,%s,%s, now() + interval '2 years')",
        (str(aid), owner, pfad.stat().st_size, titel, f"# {titel}\n"),
    )
    return aid, pfad


@pytest.fixture
def bestand(sync_conn, seed_test_group, artefakt_ablage):
    """Ein verlassenes Konto mit allem, was daran hängt — und ein aktives zur Gegenprobe."""
    store = artefakt_ablage
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pseudonym_audit (pseudonym, role, roles, last_login_at)"
            " VALUES (%s,'teacher','[\"teacher\"]',%s), (%s,'teacher','[\"teacher\"]',%s)"
            " ON CONFLICT (pseudonym) DO UPDATE SET last_login_at = EXCLUDED.last_login_at",
            (VERLASSEN, LANGE_HER, AKTIV, datetime.now(timezone.utc)),
        )
        cur.execute(
            "INSERT INTO subjects (id, name, slug) VALUES (%s,'Testfach','testfach-m2')"
            " ON CONFLICT (id) DO NOTHING",
            (SUBJECT_ID,),
        )
        ids = {
            "privat": _node(cur, "Klausurentwurf", owner=VERLASSEN, read_scope="private"),
            "gruppe": _node(cur, "Arbeitsblatt der 8c", owner=VERLASSEN,
                            read_scope="group", gruppe=seed_test_group),
            "schule": _node(cur, "Lerntext Bruchrechnen", owner=VERLASSEN,
                            read_scope="school", content_type="lerntext"),
            "fremd": _node(cur, "Blatt der Kollegin", owner=AKTIV, read_scope="private"),
        }

        # ── Bibliothek ──
        ids["artefakt"], ids["artefakt_pfad"] = _artefakt(
            cur, store, "Mein Arbeitsblatt", owner=VERLASSEN
        )
        ids["artefakt_fremd"], ids["artefakt_fremd_pfad"] = _artefakt(
            cur, store, "Blatt der Kollegin", owner=AKTIV
        )

        # ── Lernzustand ──
        # Beide hängen am `schule`-Knoten: Der überlebt (anonymisiert). Am privaten
        # Knoten wäre die Cascade über `node_id` schneller als die Pseudonym-Regel,
        # und der Test bewiese nichts.
        cur.execute(
            "INSERT INTO node_engagement (pseudonym, node_id, relation, source)"
            " VALUES (%s,%s,'struggles_with','test')",
            (VERLASSEN, str(ids["schule"])),
        )
        cur.execute(
            "INSERT INTO node_engagement (group_id, node_id, relation, source)"
            " VALUES (%s,%s,'introduced','lesson_plan')",
            (seed_test_group, str(ids["schule"])),
        )

        # ── Mitgliedschaften und Ausblendungen ──
        cur.execute(
            "INSERT INTO group_memberships (group_id, pseudonym, role_in_group)"
            " VALUES (%s,%s,'teacher'), (%s,%s,'teacher')"
            " ON CONFLICT DO NOTHING",
            (seed_test_group, VERLASSEN, seed_test_group, AKTIV),
        )
        cur.execute(
            "INSERT INTO teacher_group_exclusions (pseudonym, class_group_id, subject_id)"
            " VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
            (VERLASSEN, seed_test_group, SUBJECT_ID),
        )
    sync_conn.commit()
    yield ids
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        for schluessel in ("privat", "gruppe", "schule", "fremd"):
            cur.execute("DELETE FROM context_nodes WHERE id = %s", (str(ids[schluessel]),))
        for schluessel in ("artefakt", "artefakt_fremd"):
            cur.execute("DELETE FROM artifacts WHERE id = %s", (str(ids[schluessel]),))
        cur.execute("DELETE FROM group_memberships WHERE pseudonym IN (%s,%s)",
                    (VERLASSEN, AKTIV))
        cur.execute("DELETE FROM teacher_group_exclusions WHERE pseudonym = %s", (VERLASSEN,))
        cur.execute("DELETE FROM subjects WHERE id = %s", (SUBJECT_ID,))
        cur.execute("DELETE FROM pseudonym_audit WHERE pseudonym IN (%s,%s)",
                    (VERLASSEN, AKTIV))
    sync_conn.commit()


def _zaehle(conn, sql, *werte):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(sql, werte)
        return cur.fetchone()[0]


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


# ── Die vier am 08.09.2026 entschiedenen Fälle ───────────────────────────────


class TestBibliothek:
    """Strikt privat — also gilt dieselbe Regel wie für einen privaten Baustein."""

    async def test_zeile_und_datei_verschwinden(self, sync_conn, gelaufen):
        """Die Datei mitzuprüfen ist der Kern: Eine Zeile zu löschen und die Bytes
        liegen zu lassen wäre die Löschung, die nur in der Datenbank stattfindet."""
        assert _zaehle(
            sync_conn, "SELECT count(*) FROM artifacts WHERE id = %s",
            str(gelaufen["artefakt"]),
        ) == 0
        assert not gelaufen["artefakt_pfad"].exists(), "Bytes liegen noch auf der Platte"

    async def test_fremde_bibliothek_bleibt(self, sync_conn, gelaufen):
        assert _zaehle(
            sync_conn, "SELECT count(*) FROM artifacts WHERE owner_pseudonym = %s", AKTIV,
        ) == 1
        assert gelaufen["artefakt_fremd_pfad"].exists()


class TestLernzustand:
    async def test_persoenlicher_lernzustand_geht_mit(self, sync_conn, gelaufen):
        """„Tut sich schwer mit X" ist das Sensibelste, was hier steht."""
        assert _zaehle(
            sync_conn, "SELECT count(*) FROM node_engagement WHERE pseudonym = %s",
            VERLASSEN,
        ) == 0

    async def test_gruppen_lernzustand_bleibt(self, sync_conn, gelaufen):
        """Die Gegenprobe: Was an der Gruppe hängt, ist kein Kontodatum — und es ist
        heute der **einzige** Fall, den `complete_review` tatsächlich schreibt."""
        assert _zaehle(
            sync_conn,
            "SELECT count(*) FROM node_engagement WHERE node_id = %s AND pseudonym IS NULL",
            str(gelaufen["schule"]),
        ) == 1


class TestMitgliedschaften:
    async def test_ehemalige_sind_keine_mitglieder_mehr(self, sync_conn, gelaufen):
        """`sync_groups` schreibt beim Login fort — wer nie wieder kommt, bliebe sonst
        für immer Mitglied seiner Klassen und Kurse."""
        assert _zaehle(
            sync_conn, "SELECT count(*) FROM group_memberships WHERE pseudonym = %s",
            VERLASSEN,
        ) == 0

    async def test_aktive_mitgliedschaft_bleibt(self, sync_conn, gelaufen):
        assert _zaehle(
            sync_conn, "SELECT count(*) FROM group_memberships WHERE pseudonym = %s", AKTIV,
        ) == 1

    async def test_ausblendungen_gehen_mit(self, sync_conn, gelaufen):
        assert _zaehle(
            sync_conn,
            "SELECT count(*) FROM teacher_group_exclusions WHERE pseudonym = %s",
            VERLASSEN,
        ) == 0
