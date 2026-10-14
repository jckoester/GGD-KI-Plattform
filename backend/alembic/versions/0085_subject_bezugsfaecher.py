"""Bezugsfächer je Fach: subjects.bezugsfaecher (0.16, Schritt 2)

Welche Fächer ein Fach „mitliest" — NwT greift auf Begriffe aus Biologie, Chemie, Physik und
Mathematik zurück, Physik auf Mathematik. Gepflegt wird jeder Begriff einmal, im Leitfach;
die Bezugsfächer sagen, wo ein Chat außerhalb seines Fachs noch suchen darf (Plan
„Vorab-Suche-Begriffe", F5).

**Gerichtet:** „NwT liest Biologie mit" heißt nicht „Biologie liest NwT mit". Wer beides will,
trägt beides ein.

**Slugs, keine IDs:** geseedet aus `config/subjects.yaml` wie `sso_aliases` und `untis_codes`;
der Seed prüft jeden Eintrag gegen die Slugs derselben Datei. Aufgelöst wird bei der Abfrage.

**Rücknahme:** `alembic downgrade 0084` entfernt die Spalte; die Einträge in `subjects.yaml`
bleiben stehen.

Revision ID: 0085
Revises: 0084
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subjects",
        sa.Column(
            "bezugsfaecher",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("subjects", "bezugsfaecher")
