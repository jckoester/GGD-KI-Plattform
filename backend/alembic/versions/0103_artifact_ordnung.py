"""Ordnung der Werkstatt: Fach, Thema, Ursprung, zuletzt bearbeitet, Assistent (0.41, Päckchen AN)

Revision ID: 0103
Revises: 0102
Create Date: 2026-11-13

**`artifacts.subject_id`** — eigenes Fach des Produkts (Plan 0.41, F3/F5 der Notiz). Bis 0.40 gab es
den Fachbezug nur über die Herkunfts-Konversation; die wird nach spätestens 93 Tagen gelöscht, und das
Produkt fiel dann aus jedem Fach-Auszug. Beim Speichern aus dem Chat wird das Fach jetzt **kopiert**.
`SET NULL`: Ein gelöschtes Fach nimmt keine Produkte mit. Eine Gruppe am Produkt gibt es bewusst nicht.

**`artifacts.topic`** — freies Thema (Text), keine Kante zur Planung.

**`artifacts.derived_from`** — Ursprungsprodukt, etwa das Dokument eines Exports. `CASCADE` (Plan F5):
Exporte gehen mit ihrem Dokument. Gesetzt wird es erst ab Schritt 5; bis dahin bleibt es leer.

**`artifacts.updated_at`** — zuletzt bearbeitet (Vorgabe-Sortierung der Werkstatt).

**`artifacts.assistant_name`** — Name des Assistenten, aus dessen Chat das Produkt stammt (Plan F12).
Kopie als Text wie `provider_model`: Der Chat verschwindet, ein Assistent kann umbenannt oder gelöscht
werden — die Herkunft soll das nicht verändern.

**Vorbelegung** aus der noch vorhandenen Herkunfts-Konversation: Fach (direkt oder über die Gruppe) und
Assistent; `updated_at = created_at`. Produkte ohne lebende Konversation bleiben ohne Fach.

**Rücknahme:** `alembic downgrade 0102` entfernt die Spalten samt Inhalt.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None


def vorbelegung_sql() -> list[str]:
    """Die Vorbelegung — eigene Funktion, damit ein Test sie gegen echte Zeilen laufen lassen kann."""
    return [
        "UPDATE artifacts SET updated_at = created_at",
        """
        UPDATE artifacts a
           SET subject_id = coalesce(c.subject_id, g.subject_id),
               assistant_name = s.name
          FROM conversations c
          LEFT JOIN groups g ON g.id = c.group_id
          LEFT JOIN assistants s ON s.id = c.assistant_id
         WHERE c.id = a.origin_conversation_id
           AND c.pseudonym = a.owner_pseudonym
        """,
    ]


def upgrade() -> None:
    op.add_column("artifacts", sa.Column(
        "subject_id", sa.Integer(), sa.ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True,
    ))
    op.add_column("artifacts", sa.Column("topic", sa.Text(), nullable=True))
    op.add_column("artifacts", sa.Column(
        "derived_from", UUID(as_uuid=True), sa.ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=True,
    ))
    op.add_column("artifacts", sa.Column(
        "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"),
    ))
    op.add_column("artifacts", sa.Column("assistant_name", sa.Text(), nullable=True))
    op.create_index("idx_artifacts_owner_subject", "artifacts", ["owner_pseudonym", "subject_id"])
    op.create_index("idx_artifacts_derived_from", "artifacts", ["derived_from"])
    for sql in vorbelegung_sql():
        op.execute(sql)


def downgrade() -> None:
    op.drop_index("idx_artifacts_derived_from", table_name="artifacts")
    op.drop_index("idx_artifacts_owner_subject", table_name="artifacts")
    for spalte in ("assistant_name", "updated_at", "derived_from", "topic", "subject_id"):
        op.drop_column("artifacts", spalte)
