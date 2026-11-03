"""Bekannte Probleme und Antwortbewertung (0.31, Päckchen T, ADR-020)

Revision ID: 0101
Revises: 0100
Create Date: 2026-11-03

**`feedback.public_title`, `feedback.public_audience`** — eine Meldung als „bekanntes Problem“
zeigen. Öffentlich wird nur der Titel, den der Admin formuliert, nie der Text der Meldung.
`public_audience`: `NULL` = nicht öffentlich, `all` = alle, `teacher` = nur Lehrkräfte (Plan F1).
ADR-020 sah einen Schalter `visible_to_all` vor; die Zielgruppe ersetzt ihn.

**`message_ratings`** — Daumen hoch/runter an einer Antwort des Modells. **Ohne Pseudonym:**
Wem die Bewertung gehört, folgt aus Nachricht → Konversation; sie geht mit der Nachricht
(`ON DELETE CASCADE`). `rolle` hält fest, in welche Zählerzeile sie eingegangen ist.

**`rating_counts`** — dieselben Bewertungen als Wochenzähler je Assistent, Modell und Rolle,
ohne Personen- und Chatbezug (Plan F5). Sie überdauern das Löschen der Chats; ohne sie sähe eine
Auswertung höchstens 93 Tage zurück. Zeilen eines gelöschten Assistenten folgen ihm.

**Rücknahme:** `alembic downgrade 0100` entfernt Spalten und Tabellen samt Inhalt.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("feedback", sa.Column("public_title", sa.Text(), nullable=True))
    op.add_column("feedback", sa.Column("public_audience", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_feedback_public_audience", "feedback",
        "public_audience IS NULL OR public_audience IN ('all', 'teacher')",
    )
    op.create_check_constraint(
        "ck_feedback_public_title", "feedback",
        "public_audience IS NULL OR public_title IS NOT NULL",
    )

    op.create_table(
        "message_ratings",
        sa.Column("message_id", UUID(as_uuid=True),
                  sa.ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("rolle", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("rating IN (-1, 1)", name="ck_message_ratings_rating"),
        sa.CheckConstraint("rolle IN ('student', 'teacher')", name="ck_message_ratings_rolle"),
    )

    op.create_table(
        "rating_counts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("woche", sa.Date(), nullable=False),
        sa.Column("assistant_id", sa.Integer(),
                  sa.ForeignKey("assistants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("modell", sa.Text(), nullable=True),
        sa.Column("rolle", sa.Text(), nullable=False),
        sa.Column("plus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minus", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("woche", "assistant_id", "modell", "rolle",
                            name="uq_rating_counts_schluessel",
                            postgresql_nulls_not_distinct=True),
        sa.CheckConstraint("rolle IN ('student', 'teacher')", name="ck_rating_counts_rolle"),
        sa.CheckConstraint("plus >= 0 AND minus >= 0", name="ck_rating_counts_nicht_negativ"),
    )
    # Für die Kaskade beim Löschen eines Assistenten.
    op.create_index("idx_rating_counts_assistant", "rating_counts", ["assistant_id"])


def downgrade() -> None:
    op.drop_index("idx_rating_counts_assistant", table_name="rating_counts")
    op.drop_table("rating_counts")
    op.drop_table("message_ratings")
    op.drop_constraint("ck_feedback_public_title", "feedback", type_="check")
    op.drop_constraint("ck_feedback_public_audience", "feedback", type_="check")
    op.drop_column("feedback", "public_audience")
    op.drop_column("feedback", "public_title")
