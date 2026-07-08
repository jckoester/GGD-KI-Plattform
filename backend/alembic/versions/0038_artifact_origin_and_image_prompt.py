"""artifacts.origin_ref (Idempotenz) + generated_images.prompt (Promotion-Quelltext)

Phase 18, Schritt 2 („In Bibliothek speichern"):
- `artifacts.origin_ref` + partieller Unique-Index (owner, origin_ref) — zweimaliges
  Speichern desselben Chat-Inhalts liefert dasselbe Artefakt (Idempotenz).
- `generated_images.prompt` — der Bild-Prompt wird beim Generieren mitgeschrieben und
  beim Promoten eines Bildes als roher Quelltext (`artifacts.source`) übernommen.

Revision ID: 0038
Revises: 0037
"""

from alembic import op
import sqlalchemy as sa

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("artifacts", sa.Column("origin_ref", sa.Text(), nullable=True))
    op.create_index(
        "uq_artifacts_owner_origin",
        "artifacts",
        ["owner_pseudonym", "origin_ref"],
        unique=True,
        postgresql_where=sa.text("origin_ref IS NOT NULL"),
    )
    op.add_column("generated_images", sa.Column("prompt", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("generated_images", "prompt")
    op.drop_index("uq_artifacts_owner_origin", table_name="artifacts")
    op.drop_column("artifacts", "origin_ref")
