"""OAuth für KI-Abos (0.55, Päckchen AX Schritt 1): Clients, Codes, Token, Verbindungen

Claude im Browser, ChatGPT und Copilot melden Personen nur per OAuth an. Die Plattform wird dazu
ein kleiner Autorisierungsserver (das SDK `mcp` liefert die Endpunkte, wir den Speicher):

- **`oauth_clients`** — per Dynamic Client Registration angelegte Programme. ``client_secret``
  steht **im Klartext**: Das SDK vergleicht es so (`hmac.compare_digest`), und bei offener
  Registrierung schützt es wenig — den Zugang sichern PKCE, die festen Redirect-URIs und die
  Zustimmung der Lehrkraft (mit Jan abgestimmt 23.11.2026). ``last_used_at`` für den Cron, der
  nie benutzte Registrierungen nach 30 Tagen löscht (F12).
- **`oauth_codes`** — Autorisierungscodes, nur der SHA-256; einmalig, wenige Minuten gültig.
- **Verbindung = Zeile in `personal_access_tokens`** mit ``oauth_client_id``: ein Eintrag je
  verbundenem Programm im Profil (F7, F11), Widerruf dort beendet alles. Solche Zeilen haben
  keinen eigenen Tokentext, ``token_hash`` wird deshalb nullbar (die Prüfung stellt sicher, dass
  jede Zeile entweder einen Hash oder einen Client hat).
- **`oauth_tokens`** — die ausgestellten Zugriffs- (1 h) und Refresh-Token (90 Tage, F8), nur
  der SHA-256, an ihrer Verbindung. ``rotiert_at`` markiert einen eingelösten Refresh-Token:
  Kommt er noch einmal, ist er gestohlen, und die Verbindung endet.

**Rücknahme:** `alembic downgrade 0111` entfernt die Tabellen und die Spalte, löscht vorher die
Verbindungszeilen (sie hätten ohne Spalte keinen Sinn und keinen Hash).

Revision ID: 0112
Revises: 0111
Create Date: 2026-11-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0112"
down_revision = "0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.Text(), primary_key=True),
        sa.Column("client_secret", sa.Text(), nullable=True),
        sa.Column("metadaten", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_table(
        "oauth_codes",
        sa.Column("code_hash", sa.Text(), primary_key=True),
        sa.Column("client_id", sa.Text(), sa.ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("pseudonym", sa.Text(), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("code_challenge", sa.Text(), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("redirect_uri_explizit", sa.Boolean(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column("personal_access_tokens", sa.Column(
        "oauth_client_id", sa.Text(), sa.ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=True))
    op.alter_column("personal_access_tokens", "token_hash", existing_type=sa.Text(), nullable=True)
    op.create_check_constraint(
        "ck_personal_access_tokens_hash_oder_client", "personal_access_tokens",
        "token_hash IS NOT NULL OR oauth_client_id IS NOT NULL")
    op.create_table(
        "oauth_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"),
                  primary_key=True),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("art", sa.Text(), nullable=False),
        sa.Column("verbindung_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("personal_access_tokens.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("rotiert_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("art IN ('zugriff', 'refresh')", name="ck_oauth_tokens_art"),
    )
    # Abgleich bei jeder Anfrage über den Hash; Widerruf und Aufräumen je Verbindung.
    op.create_index("uq_oauth_tokens_hash", "oauth_tokens", ["token_hash"], unique=True)
    op.create_index("idx_oauth_tokens_verbindung", "oauth_tokens", ["verbindung_id"])


def downgrade() -> None:
    op.drop_index("idx_oauth_tokens_verbindung", table_name="oauth_tokens")
    op.drop_index("uq_oauth_tokens_hash", table_name="oauth_tokens")
    op.drop_table("oauth_tokens")
    op.execute("DELETE FROM personal_access_tokens WHERE oauth_client_id IS NOT NULL")
    op.drop_constraint("ck_personal_access_tokens_hash_oder_client", "personal_access_tokens", type_="check")
    op.alter_column("personal_access_tokens", "token_hash", existing_type=sa.Text(), nullable=False)
    op.drop_column("personal_access_tokens", "oauth_client_id")
    op.drop_table("oauth_codes")
    op.drop_table("oauth_clients")
