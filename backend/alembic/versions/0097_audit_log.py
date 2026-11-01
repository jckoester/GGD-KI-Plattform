"""Audit-Log (0.28, Päckchen R, ADR-010 Teil 2)

Revision ID: 0097
Revises: 0096
Create Date: 2026-11-01

**`audit_log`**: sicherheitsrelevante Ereignisse in sechs Kategorien (`auth`, `admin`,
`access`, `moderation`, `secret`, `system`), Schema nach ADR-010 §2.2 — ohne `ip_hash`
(Nachtrag §2.5). Keine Inhalte, keine Tokens, keine Meldungstexte; geschrieben wird über
`app/core/audit.py`.

**Nur anhängen:** Ein Trigger weist `UPDATE`, `DELETE` und `TRUNCATE` ab. Ausnahmen setzt nur,
wer für seine Transaktion `SET LOCAL audit.aufraeumen = 'on'` ausführt — der tägliche
Aufräum-Lauf (Aufbewahrung je Klasse, §2.3) und die Kontolöschung (Platzhalter für das
Pseudonym, §2.5). `REVOKE` liefe ins Leere: Die Anwendung läuft in der Compose als `postgres`.

**Rücknahme:** `alembic downgrade 0096` entfernt Tabelle, Trigger und Funktion samt Inhalt.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None

_KATEGORIEN = "('auth','admin','access','moderation','secret','system')"


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("occurred_at", postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor_pseudonym", sa.Text(), nullable=True),
        sa.Column("actor_role", sa.Text(), nullable=True),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("retention_class", sa.Text(), nullable=False),
        sa.CheckConstraint(f"category IN {_KATEGORIEN}", name="check_audit_log_category"),
        sa.CheckConstraint(f"retention_class IN {_KATEGORIEN}", name="check_audit_log_retention_class"),
    )
    op.create_index("audit_log_occurred_at_idx", "audit_log", [sa.text("occurred_at DESC")])
    op.create_index("audit_log_category_idx", "audit_log", ["category", sa.text("occurred_at DESC")])
    op.create_index("audit_log_actor_idx", "audit_log", ["actor_pseudonym", sa.text("occurred_at DESC")])

    op.execute(
        """
        CREATE FUNCTION audit_log_nur_anhaengen() RETURNS trigger AS $$
        BEGIN
            IF coalesce(current_setting('audit.aufraeumen', true), '') = 'on' THEN
                RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
            END IF;
            RAISE EXCEPTION 'audit_log ist nur zum Anhängen (% abgewiesen)', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER audit_log_nur_anhaengen_zeile BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_nur_anhaengen()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_nur_anhaengen_leeren BEFORE TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_nur_anhaengen()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_nur_anhaengen_leeren ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_nur_anhaengen_zeile ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_nur_anhaengen()")
    op.drop_table("audit_log")
