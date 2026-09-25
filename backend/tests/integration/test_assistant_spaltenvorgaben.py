"""Die Spaltenvorgaben von `assistants` sind benutzbar (Alembic 0077).

**Der Fehler:** `0001_initial_schema.py` und `0009_assistants_full_schema.py` übergaben
`server_default` als Python-Zeichenkette (`server_default="'student'"`). Alembic quotet
die noch einmal — in der Datenbank stand `DEFAULT '''student'''`, der Vorgabewert war
also die Zeichenkette `'student'` **samt Apostrophen**.

**Warum es niemandem auffiel:** Über das ORM greift die Python-Vorgabe, nicht die der
Datenbank; die Anwendung setzt alle sechs Felder ohnehin selbst. Erst ein roher `INSERT`
zeigt es — und der kommt in Tests und Reparaturskripten vor (gefunden am 25.09.2026 beim
Schreiben der Lebenszyklus-Tests: Die Zeile verletzte `check_assistant_audience`).

⚠️ **Gegen die Datenbank, nicht gegen das Modell.** Das Modell war die ganze Zeit richtig
(`sa.text(...)`) — genau deshalb fiel die Abweichung nicht auf. Ein Test, der das Modell
befragt, hätte sie nie gefunden.
"""
import psycopg2
import pytest

pytestmark = pytest.mark.asyncio

SPALTEN = ("status", "audience", "scope", "name", "model", "system_prompt")
DREI_APOSTROPHE = chr(39) * 3


@pytest.fixture
def conn(db_url, run_migrations):
    verbindung = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield verbindung
    verbindung.close()


def test_kein_vorgabewert_traegt_apostrophe(conn):
    """Der direkte Blick in den Katalog — er nennt den Fehler beim Namen."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name, column_default FROM information_schema.columns"
            " WHERE table_name = 'assistants' AND column_name = ANY(%s)",
            (list(SPALTEN),),
        )
        vorgaben = dict(cur.fetchall())
    conn.rollback()
    assert len(vorgaben) == len(SPALTEN)
    for spalte, vorgabe in vorgaben.items():
        # ⚠️ **Am Anfang prüfen, nicht irgendwo.** Der erste Entwurf strippte die
        # Apostrophe von beiden Seiten und suchte dann nach der Verdopplung — die
        # war da aber gerade weggestrippt, und die Gegenprobe kam grün zurück.
        # `'student'::text` beginnt mit einem Apostroph, der kaputte Wert mit dreien.
        assert not (vorgabe or "").startswith(DREI_APOSTROPHE), (
            f"{spalte}: {vorgabe} — doppelt gequotet, siehe Alembic 0077"
        )


def test_ein_assistent_aus_lauter_vorgaben_ist_gueltig(conn):
    """⚠️ **Die eigentliche Zusage.** Vorher scheiterte genau das an der CHECK-Bedingung.

    Was die Datenbank als Vorgabe einträgt, muss ihre eigenen Bedingungen erfüllen —
    sonst ist die Vorgabe keine.
    """
    with conn.cursor() as cur:
        cur.execute("INSERT INTO assistants DEFAULT VALUES RETURNING id")
        neu = cur.fetchone()[0]
        cur.execute(
            "SELECT status, audience, scope, name, model, system_prompt"
            " FROM assistants WHERE id = %s",
            (neu,),
        )
        werte = cur.fetchone()
    conn.rollback()
    assert werte == ("draft", "student", "private", "", "", "")
