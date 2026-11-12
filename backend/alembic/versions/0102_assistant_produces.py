"""Angabe „stellt her" am Assistenten (0.40, Päckchen AM)

Revision ID: 0102
Revises: 0101
Create Date: 2026-11-12

**`assistants.produces`** — Liste von Kennungen aus `app/assistants/produkte.py` (`image`,
`diagram`, `document`, `lesson_plan`, `year_plan`). Ein Assistent mit Angabe ist ein
**Werkzeug**: Marke und Filter in der Assistentenliste. Die Seite `/tools` entfällt.

**Vorbelegung** aus den Fähigkeiten — einmalig, danach gilt nur das Feld (Plan F1):
`image_generation` → `image`, `lesson_planning` → `lesson_plan`, `planning` → `year_plan`.
Die Zuordnung ist hier festgeschrieben, nicht aus `produkte.py` gelesen: Eine Migration muss
auch dann noch dasselbe tun, wenn sich die Liste später ändert. Diagramme und Dokumente
haben keine Fähigkeit; sie setzt die Schule im Editor (Seed: „Schaltpläne zeichnen“).

**Rücknahme:** `alembic downgrade 0101` entfernt die Spalte samt Inhalt.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None

#: Reihenfolge wie `PRODUKTARTEN` zum Zeitpunkt dieser Migration.
_VORBELEGUNG = (
    ("image_generation", "image"),
    ("lesson_planning", "lesson_plan"),
    ("planning", "year_plan"),
)


def vorbelegung_sql() -> str:
    """Die Vorbelegung als ein UPDATE — eigene Funktion, damit ein Test sie gegen echte Zeilen
    laufen lassen kann (`tests/integration/test_assistant_produces.py`)."""
    teile = " || ".join(
        f"CASE WHEN tool_groups ? '{faehigkeit}' THEN '[\"{art}\"]'::jsonb ELSE '[]'::jsonb END"
        for faehigkeit, art in _VORBELEGUNG
    )
    return f"UPDATE assistants SET produces = {teile}"


def upgrade() -> None:
    op.add_column(
        "assistants",
        sa.Column("produces", JSONB(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.execute(vorbelegung_sql())


def downgrade() -> None:
    op.drop_column("assistants", "produces")
