"""UP-Phase-3a: min_grade/max_grade für Curriculum-Knoten aus jahrgangsstufe backfillen

Die Spalten min_grade/max_grade existieren bereits auf context_nodes, wurden für
content_type='curriculum' aber nie befüllt. Diese Migration normalisiert das freie
metadata.jahrgangsstufe-Label (z. B. '5/6') strukturell in die Spalten — nur dort, wo
noch NULL. Idempotent.

Revision ID: 0026
Revises: 0025
"""

from alembic import op
import sqlalchemy as sa

from app.context.grades import parse_grade_band

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, metadata->>'jahrgangsstufe' AS jg "
            "FROM context_nodes "
            "WHERE content_type = 'curriculum' "
            "AND (min_grade IS NULL OR max_grade IS NULL)"
        )
    ).fetchall()

    for row in rows:
        min_grade, max_grade = parse_grade_band(row.jg)
        if min_grade is None and max_grade is None:
            continue
        conn.execute(
            sa.text(
                "UPDATE context_nodes SET min_grade = :mn, max_grade = :mx "
                "WHERE id = :id"
            ),
            {"mn": min_grade, "mx": max_grade, "id": row.id},
        )


def downgrade():
    # Kein verlustfreies Down: die ursprüngliche NULL-Belegung ist nicht
    # rekonstruierbar. metadata.jahrgangsstufe bleibt als Quelle erhalten.
    pass
