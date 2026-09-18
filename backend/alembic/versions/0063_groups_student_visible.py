"""`groups.student_visible` — Freigabe einer Unterrichtsgruppe für ihre Schüler:innen

Für einen **begrenzten Testbetrieb**: Rund zehn Lehrkräfte nehmen mit je einem Teil ihrer
Lerngruppen teil. Schüler:innen sollen nur die Fächer sehen, die wirklich dazugehören —
alle übrigen haben weder Material noch Assistenten und sind nicht sinnvoll nutzbar.

**Warum eine Spalte und keine Ableitung.** Naheliegend wäre gewesen, das Signal aus den
vorhandenen Daten zu lesen: Eine Gruppe hat genau dann ein Mitglied mit
`role_in_group='teacher'`, wenn eine Lehrkraft dieses Kurses sich angemeldet hat
(`group_sync.py` schreibt Mitgliedschaften beim Login). Das trägt aber nicht: Der Sync
schreibt die Lehrkraft in **alle** ihre Unterrichtsgruppen. Wer mit einer Gruppe in
Mathematik teilnimmt und dieselbe Gruppe auch in Physik unterrichtet, gäbe Physik
ungewollt mit frei. Die Anmeldung ist eine Aussage über die Person, gebraucht wird eine
über die Gruppe.

Ebenso verworfen: die Ableitung aus dem Verhalten (Wochenmuster vorhanden, Baustein
geteilt). Solche Regeln sind stumm — eine Lehrkraft, deren Fach unsichtbar bleibt, erfährt
den Grund nicht.

**Ohne den Schalter folgenlos.** Gelesen wird die Spalte nur bei
`STUDENT_SUBJECTS_OPT_IN=true`. Steht er aus, verhält sich die Plattform wie zuvor; nach
dem Testbetrieb genügt das Umlegen des Schalters, es ist nichts zurückzubauen.

`false` als Vorgabe ist die sichere Richtung: Im Testbetrieb ist nichts sichtbar, was
nicht ausdrücklich freigegeben wurde.

Revision ID: 0063
Revises: 0062
"""
import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column(
            "student_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("groups", "student_visible")
