"""Die Rangfolge in der **laufenden** Datenbank (Paket 7, AP7).

Der Unit-Test daneben (`tests/unit/test_scope_rangfolge.py`) hält Modell und Startprüfung
zusammen. Beide beschreiben nur, was gelten *soll* — gebaut wird die Datenbank aus den
**Migrationen**, und die sind eingefroren. Genau dazwischen kann es auseinanderlaufen:
Ein `CheckConstraint` im Modell, den keine Migration je geschrieben hat, wirkt nirgends;
umgekehrt hält die Datenbank an einer Ordnung fest, die das Modell längst anders
beschreibt.

⚠️ Genau diese Lücke gab es schon einmal — `check_assistant_scope` war im Modell
vorhanden, und die Frage, ob die Datenbank ihn kennt, ließ sich nur durch Nachsehen
beantworten (25.09.2026, Paket 7 AP4).
"""
import re

import psycopg2
import pytest

from app.context.taxonomy_check import _SCOPE_RANG

pytestmark = pytest.mark.asyncio

BEDINGUNG = "check_context_nodes_scope_restrictivity"


@pytest.fixture
def conn(db_url, run_migrations):
    verbindung = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield verbindung
    verbindung.close()


def test_die_datenbank_traegt_dieselbe_rangfolge(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
            (BEDINGUNG,),
        )
        zeile = cur.fetchone()
    conn.rollback()
    assert zeile, f"Die Bedingung `{BEDINGUNG}` gibt es in der Datenbank nicht"

    bloecke = re.findall(r"CASE\s+(?:write_scope|read_scope)(.*?)END", zeile[0], re.S)
    assert len(bloecke) == 2, f"Erwartet zwei CASE-Blöcke, gefunden {len(bloecke)}"
    for block in bloecke:
        raenge = {n: int(r) for n, r in re.findall(r"WHEN '(\w+)'::text THEN (\d+)", block)}
        assert raenge == _SCOPE_RANG, (
            "Die Rangfolge in der Datenbank weicht von `_SCOPE_RANG` ab: "
            f"{raenge} ≠ {_SCOPE_RANG}. Eine Migration hat sie geändert (oder eine "
            "fehlt) — Modell und Startprüfung sind dann nur noch Behauptungen."
        )
