"""Spaltenvorgaben in `assistants` richtigstellen — sie waren doppelt gequotet

Revision ID: 0077
Revises: 0076
Create Date: 2026-09-25

⚠️ **Der Vorgabewert war die Zeichenkette `'student'` samt Apostrophen**, nicht
`student`. Ursache: `0001_initial_schema.py` und `0009_assistants_full_schema.py`
übergaben `server_default` als **Python-Zeichenkette** (`server_default="'student'"`).
Alembic behandelt die dann als Literal und quotet sie noch einmal — in der Datenbank
stand `DEFAULT '''student'''`. Richtig wäre `sa.text("'student'")` gewesen; das Modell in
`app/db/models.py` macht es so und wich deshalb still von der Datenbank ab.

Betroffen sind sechs Spalten: `status`, `audience`, `scope`, `name`, `model`,
`system_prompt`.

**Warum es niemandem auffiel:** Die Anwendung setzt alle sechs Felder selbst — über das
ORM greift die Python-Vorgabe, nicht die der Datenbank. Sichtbar wird es nur bei einem
**rohen** `INSERT`, der eine dieser Spalten wegläßt:

* `status`, `audience` und `scope` verletzen dann ihre eigene CHECK-Bedingung — laut und
  sofort. Ärgerlich beim Testen, aber ungefährlich.
* `name`, `model` und `system_prompt` haben **keine** Bedingung. Dort landet die
  Zeichenkette `''` (zwei Apostrophe) statt eines leeren Feldes — und die steht dann im
  Namen eines Assistenten.

**Bestandsreparatur** für die drei ungeschützten Spalten. Die drei anderen können den
falschen Wert gar nicht tragen; ihre CHECK-Bedingung hat ihn immer abgewiesen.
"""
import sqlalchemy as sa
from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None

# Spalte → richtiger Vorgabewert
VORGABEN = {
    "status": "'draft'",
    "audience": "'student'",
    "scope": "'private'",
    "name": "''",
    "model": "''",
    "system_prompt": "''",
}

# Nur diese drei tragen keine CHECK-Bedingung und können den falschen Wert enthalten.
UNGESCHUETZT = ("name", "model", "system_prompt")


def upgrade() -> None:
    for spalte, vorgabe in VORGABEN.items():
        op.alter_column("assistants", spalte, server_default=sa.text(vorgabe))
    for spalte in UNGESCHUETZT:
        op.execute(
            f"UPDATE assistants SET {spalte} = '' WHERE {spalte} = ''''''"
        )


def downgrade() -> None:
    """Zurück zum doppelt gequoteten Zustand — vollständigkeitshalber, nicht als Angebot."""
    for spalte, vorgabe in VORGABEN.items():
        op.alter_column("assistants", spalte, server_default=vorgabe)
