"""`personal_access_tokens` — Zugang für Clients außerhalb des Browsers

Bis hierher akzeptierte die API ausschließlich das HttpOnly-Session-Cookie aus dem
SSO-Login. Ein Skript oder Plugin kommt so nicht an die Daten: Das Cookie ist an den
Browser gebunden und lässt sich nicht erneuern. Diese Tabelle trägt die Gegenstücke —
persönliche Token, die über den `Authorization`-Header kommen.

**Der Klartext steht nirgends.** Gespeichert wird `sha256(token)`; der Klartext ist genau
einmal sichtbar, bei der Erzeugung. Ein Datenbankauszug gibt damit keinen Zugang her.

**`expires_at` ist NOT NULL.** Ein Token ohne Ablauf ist ein Passwort, das niemand
wechselt. Die Obergrenze (ein Jahr) setzt die Anwendung, nicht die Datenbank — sie ist
eine Richtlinie, keine Invariante der Daten.

**Rollen stehen nicht in dieser Tabelle.** Sie kommen bei jeder Anfrage frisch aus
`pseudonym_audit`; ein eingefrorener Rollensatz überlebte sonst den Entzug der
Lehrkraft-Rolle (Sicherheits-Audit #11 gilt sinngemäß auch hier).

Revision ID: 0061
Revises: 0060
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_access_tokens",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column("pseudonym", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column(
            "scopes", postgresql.ARRAY(sa.Text()),
            nullable=False, server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # Der Abgleich läuft bei **jeder** Anfrage über den Hash — er muss über den Index
    # gehen, nicht über einen Tabellendurchlauf. `unique` ist dabei kein Selbstzweck:
    # Zwei Zeilen mit demselben Hash wären zwei Besitzer desselben Tokens.
    op.create_index(
        "uq_personal_access_tokens_hash", "personal_access_tokens",
        ["token_hash"], unique=True,
    )
    # Für die Liste „meine Token" im Profil.
    op.create_index(
        "idx_personal_access_tokens_pseudonym", "personal_access_tokens", ["pseudonym"]
    )


def downgrade() -> None:
    op.drop_index("idx_personal_access_tokens_pseudonym", table_name="personal_access_tokens")
    op.drop_index("uq_personal_access_tokens_hash", table_name="personal_access_tokens")
    op.drop_table("personal_access_tokens")
