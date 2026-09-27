"""Archivierte Bildungsplan-Knoten aus alter `bp_id`-Schreibweise entfernen

Revision ID: 0080
Revises: 0079
Create Date: 2026-09-27

Mathematik führte V2 doppelt: 326 aktive und 326 archivierte IK-Kompetenzen, paarweise
gleich. Es sind **keine Dubletten im Sinne gleicher `bp_id`** — der Scraper hat sein
Schema geändert:

    aktiv:      …_IK_5-6_01_00_01   „3.1.1(1) die Prinzipien …"
    archiviert: …_IK_5-6_01_01      „3.1.1.(1) die Prinzipien …"

Derselbe Inhalt, alte ID-Bildung, alte Titelform (Punkt vor der Klammer). Der Import
sah die alten IDs als „weggefallen" und archivierte sie, während er dieselben
Kompetenzen unter neuen IDs anlegte.

⚠️ **Warum das mehr ist als Ordnungsliebe.** `status = 'archived'` trägt an
Bildungsplan-Knoten dadurch drei Bedeutungen: abgelöst, alte Schreibweise, und „diese
Edition gilt für das Fach noch nicht". Jede Anzeige, die den Grund benennen will, rät
bei zwei von dreien. Nach diesem Lauf bleiben zwei.

**Die Bedingungen sind eng — und das ist Absicht.** Gelöscht wird nur, was *alle* vier
erfüllt:

1. alte Schreibweise (`.(` in der Kompetenznummer),
2. ein **aktiver** Knoten mit derselben Nummer in **derselben** Edition desselben Fachs,
3. keine eingehende Kante,
4. in keinem Chat angeheftet.

Damit ist der Lauf selbstbegrenzend: Trifft er auf einem anderen Bestand weniger oder
nichts, löscht er weniger oder nichts. Gemessen im Dev-System (27.09.2026): 326 Zeilen,
alle aus Mathematik `2016.V2`. **Das Produktivsystem zeigt dasselbe Bild** (Jan,
27.09.2026, mit derselben Bedingung als `SELECT` geprüft) — die Altlast ist nicht auf
einen Entwicklungsrechner beschränkt, und genau deshalb ist sie eine Migration und kein
Handgriff.

⚠️ **Die 319 Knoten der Basisfassung `2016` bleiben stehen.** Sie tragen dieselbe alte
Schreibweise, aber dort gibt es **keinen** aktiven Zwilling — die ganze Basisedition ist
für Mathematik archiviert, und das ist die *legitime* Bedeutung von „abgelöst". Einer
von ihnen hängt außerdem in einem Chat. Bedingung 2 schließt sie aus, ohne dass sie
eigens erwähnt werden müssten.

⚠️ **Nicht rückrollbar, und das trifft auch das Produktivsystem.** Die Zeilen sind
danach weg; der Scraper erzeugt die alte Schreibweise nicht mehr, ein erneuter Import
bringt sie also nicht zurück. Der einzige Weg zurück ist die Sicherung — siehe
`docs/admin/updates-und-wartung.md`. Vor dem Ausrollen von 0.11 gehört sie ohnehin dazu;
diese Migration ist der Grund, es diesmal nicht zu überspringen.
"""
from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


#: Die Auswahl, einmal formuliert — die Migration löscht danach, der Prüfsatz zählt
#: damit. Zwei Fassungen derselben Bedingung liefen auseinander.
AUSWAHL = """
    SELECT alt.id
    FROM context_nodes alt
    WHERE alt.status = 'archived'
      AND alt.content_type = 'ik_kompetenz'
      AND alt.metadata->>'kompetenz_nr' LIKE '%.(%'
      AND EXISTS (
            SELECT 1 FROM context_nodes neu
            WHERE neu.subject_id = alt.subject_id
              AND neu.bp_version = alt.bp_version
              AND neu.content_type = 'ik_kompetenz'
              AND neu.status = 'active'
              AND neu.metadata->>'kompetenz_nr'
                  = replace(alt.metadata->>'kompetenz_nr', '.(', '(')
      )
      AND NOT EXISTS (
            SELECT 1 FROM context_edges e WHERE e.to_node_id = alt.id
      )
      AND NOT EXISTS (
            SELECT 1 FROM chat_context_nodes x WHERE x.node_id = alt.id
      )
"""


def upgrade() -> None:
    op.execute(f"DELETE FROM context_nodes WHERE id IN ({AUSWAHL})")


def downgrade() -> None:
    """Bewusst leer — und das ist keine Nachlässigkeit.

    Die Zeilen sind weg, und der Scraper erzeugt die alte Schreibweise nicht mehr; sie
    ließen sich also auch durch einen erneuten Import nicht wiederherstellen. Eine
    Rückrolle, die so tut, als könnte sie das, wäre schlimmer als eine, die schweigt.

    Verloren geht dabei nichts, was irgendwo gebraucht wird: Jeder gelöschte Knoten
    hatte einen aktiven Zwilling, keine eingehende Kante und hing in keinem Chat —
    genau das waren die Bedingungen.
    """
