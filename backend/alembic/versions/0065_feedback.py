"""`feedback` — Rückmeldungen aus der Anwendung heraus (ADR-020)

Der Beta-Betrieb lief ohne Rückkanal: Wer einen Fehler fand, hatte keinen Ort dafür.
Diese Tabelle ist er — ein Freitext mit Kategorie, dem technischen Kontext der Stelle,
an der die Meldung entstand, und einem Status, über den die meldende Person erfährt,
was daraus geworden ist.

**Warum kein Fremdschlüssel auf `pseudonym_audit`.** Der Entwurf in ADR-020 sah
`REFERENCES pseudonym_audit(pseudonym) ON DELETE SET NULL` vor. Dagegen sprechen drei
Dinge: Keine andere Tabelle im Projekt führt einen solchen Schlüssel — der Personenbezug
wird überall in `cleanup_inactive_accounts` von Hand abgeräumt. Der Automatismus träfe
außerdem nur `pseudonym`; `contact` muss ohnehin dort fallen, sodass die Regel zweimal
geschrieben stünde, halb hier und halb dort. Und die Integrationstests stellen ihre
Sitzungen über den JWT-Dienst aus, ohne Zeile in `pseudonym_audit` — jede Meldung aus
einem Test liefe gegen den Schlüssel.

**Warum `text` in der Datenbank `content` heißt.** `app/db/models.py` importiert `text`
aus SQLAlchemy für die `server_default`-Ausdrücke; ein Attribut dieses Namens verdeckte
die Funktion im Klassenkörper. `content` ist zudem der Hausname für den Textkörper
(`messages`, `context_nodes`).

**Ohne `preview` und `visible_to_all`.** Beide stehen im Datenmodell des ADR, gehören
aber zu Teilen, die nach 0.11.0 kommen (Vorschaumodus ADR-016 bzw. „Bekannte Probleme").
Eine Spalte, die niemand schreibt, ist eine Behauptung über die Zukunft.

Revision ID: 0065
Revises: 0064
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Nullable: Die Kontolöschung nimmt dem Eintrag den Personenbezug, statt ihn
        # zu löschen (ADR-011 §6.2).
        sa.Column("pseudonym", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("contact", sa.Text(), nullable=True),
        sa.Column("app_version", sa.Text(), nullable=False),
        sa.Column("route", sa.Text(), nullable=True),
        # Ohne FK — ein gelöschter Assistent entwertet die Meldung über ihn nicht.
        sa.Column("assistant_id", sa.Integer(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("viewport", sa.Text(), nullable=True),
        sa.Column("conversation_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'open'")),
        sa.Column("admin_reply", sa.Text(), nullable=True),
        sa.Column("resolved_in_version", sa.Text(), nullable=True),
        sa.Column("issue_ref", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("status_changed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "category IN ('bug', 'suggestion', 'other')", name="ck_feedback_category"
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'done', 'declined', 'spam')",
            name="ck_feedback_status",
        ),
    )
    # Zwei Zugriffswege: „Meine Meldungen" und die Tages-/Sperrzählung lesen je
    # Pseudonym, die Admin-Liste und der Löschlauf je Status — beide zeitlich sortiert.
    op.create_index("idx_feedback_pseudonym_created", "feedback", ["pseudonym", "created_at"])
    op.create_index("idx_feedback_status_created", "feedback", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_feedback_status_created", table_name="feedback")
    op.drop_index("idx_feedback_pseudonym_created", table_name="feedback")
    op.drop_table("feedback")
