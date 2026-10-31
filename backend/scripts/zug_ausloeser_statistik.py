"""Zähler der Zug-Auslöser für den Betatest (0.26, Rückfall Schritt 10, Migration 0094).

    cd backend && venv/bin/python scripts/zug_ausloeser_statistik.py --seit 2026-11-02

Zwei Fragen (Jan, 31.10.2026): Wie oft wird je 100 Gespräche die Nachsetz- und die
Lehrkraft-Anweisung gesetzt — und wie oft arbeitet die Schüler:in danach weiter? Das sagt, ob das
Problem im Betrieb die Größe hat, die der Prüfsatz ihm gibt.

- **Gespräche:** Konversationen von Schüler:innen (Rolle `student` in `pseudonym_audit`), angelegt
  seit ``--seit``, mit mindestens einer Schülernachricht, ohne Editor-Vorschau (`is_test`). Für das
  Nachsetzen zählt als Nenner zusätzlich nur, was in einem Assistenten mit „Begleiten statt lösen“
  lief — nur dort gilt der Auslöser.
- **Weitergearbeitet:** Nach der Nachricht mit Anweisung kam im selben Gespräch noch mindestens
  eine Schülernachricht (ersetzte Nachrichten zählen nicht).

Gibt nur Zahlen aus, keine Texte und keine Pseudonyme. Konversationen, die der Lebenszyklus schon
gelöscht hat, fehlen samt ihren Zeilen.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ABFRAGE = """
WITH gespraeche AS (
  SELECT c.id, c.assistant_id,
         COALESCE((a.bausteine ? 'begleiten_statt_loesen'), false) AS begleiten,
         (SELECT count(*) FROM messages m WHERE m.conversation_id = c.id AND m.role = 'user'
                                            AND m.ersetzt_am IS NULL) AS nutzer
  FROM conversations c
  JOIN pseudonym_audit p ON p.pseudonym = c.pseudonym
  LEFT JOIN assistants a ON a.id = c.assistant_id
  WHERE c.created_at >= %(seit)s AND NOT c.is_test AND p.roles::text LIKE '%%student%%'
)
SELECT
  (SELECT count(*) FROM gespraeche WHERE nutzer > 0),
  (SELECT count(*) FROM gespraeche WHERE nutzer > 0 AND begleiten),
  z.art,
  count(*) FILTER (WHERE z.treffer),
  count(*) FILTER (WHERE z.anweisung),
  count(DISTINCT z.conversation_id) FILTER (WHERE z.anweisung),
  count(*) FILTER (WHERE z.anweisung AND g.nutzer > z.nutzer_nachricht),
  count(*) FILTER (WHERE z.anweisung AND z.quelle = 'regex'),
  count(*) FILTER (WHERE z.anweisung AND z.quelle LIKE 'korpus%%')
FROM zug_ausloeser z JOIN gespraeche g ON g.id = z.conversation_id
GROUP BY z.art
"""


def main() -> None:
    p = argparse.ArgumentParser(description="Zähler der Zug-Auslöser (Betatest)")
    p.add_argument("--seit", type=date.fromisoformat, required=True, help="Datum JJJJ-MM-TT")
    args = p.parse_args()

    import psycopg2

    from app.config import settings
    conn = psycopg2.connect(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute(ABFRAGE, {"seit": args.seit})
        zeilen = cur.fetchall()
        if not zeilen:
            cur.execute("SELECT count(*) FROM conversations c JOIN pseudonym_audit p ON p.pseudonym = c.pseudonym "
                        "WHERE c.created_at >= %s AND NOT c.is_test AND p.roles::text LIKE '%%student%%'", (args.seit,))
            print(f"Seit {args.seit}: {cur.fetchone()[0]} Schüler-Gespräche, kein Zug-Auslöser angeschlagen.")
            return
    conn.close()
    alle, begleiten = zeilen[0][0], zeilen[0][1]
    print(f"Seit {args.seit}: {alle} Schüler-Gespräche, davon {begleiten} in Assistenten mit „Begleiten statt lösen“.\n")
    for _, _, art, treffer, anweisungen, gespraeche_mit, weiter, regex, korpus in zeilen:
        nenner = begleiten if art == "druck" else alle
        name = "Nachsetzen" if art == "druck" else "Lehrkraft-Behauptung"
        je100 = 100 * gespraeche_mit / nenner if nenner else 0.0
        print(f"{name}: Treffer {treffer}, Anweisungen {anweisungen} (Muster {regex}, Korpus {korpus})")
        print(f"  Gespräche mit Anweisung: {gespraeche_mit} = {je100:.1f} je 100 Gespräche"
              f"{' (Nenner: mit Begleiten-Baustein)' if art == 'druck' else ''}")
        print(f"  danach weitergearbeitet: {weiter} von {anweisungen}"
              f"{f' ({100 * weiter / anweisungen:.0f} %)' if anweisungen else ''}\n")


if __name__ == "__main__":
    main()
