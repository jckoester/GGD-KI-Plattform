"""`groups.erbt_mitglieder` — ob eine Unterrichtsgruppe ihre Mitglieder aus der Klasse zieht

**Warum eine Spalte und keine Regel.** Bis hierher galt: Eine Gruppe erbt, wenn sie
**genau eine** Quellklasse hat. Das ist eine gute Näherung — aber eben nur eine. Religion
und Ethik teilen eine Klasse, ohne dass der Stundenplan zwei Klassennamen nennt; eine
solche Gruppe erbte die ganze Klasse und damit Schüler:innen, die gar nicht hingehören.
Umgekehrt gibt es kleine Klassen, die vollständig gemeinsam unterrichtet werden und unter
der Zählregel keinen Zugang bekämen.

Beides weiß **die Lehrkraft** und sonst niemand. Die Frage stellt sich genau einmal je
Gruppe, beim Anlegen — deshalb wird sie dort gestellt und die Antwort hier gespeichert,
statt sie bei jedem Login neu aus der Anzahl der Quellklassen zu erraten.

⚠️ **Die Zählregel bleibt die Vorbelegung, nicht die Wahrheit.** Vorgeschlagen wird
„erbt" bei genau einer Klasse, „Teilgruppe" bei mehreren und in der Kursstufe. Die
Vorbelegung ist die sichere Richtung: Wer sie übernimmt, bekommt nie zu viele Mitglieder.

**Zum Backfill.** `true` genau dort, wo bisher tatsächlich vererbt wurde — Unterrichts\
gruppe, keine SSO-Entsprechung, **genau eine** Quellklasse. Alles andere `false`. Damit
verhält sich der Bestand nach der Migration wie davor; niemand verliert oder gewinnt
Mitglieder.

**Umschalten wirkt.** Wird `erbt_mitglieder` später auf `false` gesetzt, räumt der
Vererbungslauf die bisher geerbten Mitgliedschaften beim nächsten Login ab — er entfernt
`geerbt`-Einträge in jeder Gruppe, die gerade nicht vererbt. Die Entscheidung ist also
korrigierbar, ohne dass jemand von Hand eingreifen müsste.

Revision ID: 0069
Revises: 0068
"""
import sqlalchemy as sa
from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column(
            "erbt_mitglieder",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Den bisherigen Zustand festschreiben: genau eine Quellklasse = es wurde vererbt.
    op.execute(
        """
        UPDATE groups g SET erbt_mitglieder = true
         WHERE g.type = 'teaching_group'
           AND g.sso_group_id IS NULL
           AND (SELECT count(*) FROM group_source_classes q WHERE q.group_id = g.id) = 1
        """
    )


def downgrade() -> None:
    op.drop_column("groups", "erbt_mitglieder")
