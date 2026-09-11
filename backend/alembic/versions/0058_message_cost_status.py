"""`messages.cost_status` — wie belastbar der gespeicherte Betrag ist.

Ein Chat-Zug besteht aus mehreren LLM-Anfragen (je Werkzeugrunde eine, dazu die
Titelgenerierung). `_kosten_des_zuges` sucht ihre SpendLogs; findet es nur einen Teil,
wird die **Teilsumme** gespeichert — bis jetzt ununterscheidbar von einer
vollständigen. Die Admin-Statistik summiert sie (`WHERE m.cost_usd IS NOT NULL`) und
meldet stillschweigend zu wenig.

Dazu kommt der Umbau, für den diese Spalte gebraucht wird: Die Kosten werden künftig
**nach** dem Antworttext im Hintergrund nachgetragen. Zwischen dem Schreiben der
Nachricht und dem Eintreffen des Betrags gibt es damit einen dritten Zustand, den
`cost_usd IS NULL` nicht ausdrücken kann — „wird noch ermittelt" ist etwas anderes als
„gibt es nicht".

**Bestandszeilen bleiben `NULL`.** Das heißt „keine Aussage", nicht
„vollständig": Unter den alten Beträgen sind Teilsummen, und welche, weiß niemand.
Sie pauschal als vollständig zu markieren hieße, eine Unsicherheit in eine Behauptung
zu verwandeln — genau das, was die Spalte abschaffen soll. `NULL` trägt auch für
User-Nachrichten, die überhaupt keine Kosten haben.

Revision ID: 0058
Revises: 0057
"""
from alembic import op
import sqlalchemy as sa

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None

ZUSTAENDE = ("ausstehend", "vollstaendig", "unvollstaendig")
CHECK_NAME = "check_messages_cost_status"


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("cost_status", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        CHECK_NAME,
        "messages",
        "cost_status IS NULL OR cost_status IN "
        f"({', '.join(repr(z) for z in ZUSTAENDE)})",
    )
    # Teilindex für die Aufräum-/Diagnoseabfrage „was hängt noch?". Ohne ihn liefe sie
    # über die ganze Nachrichtentabelle; mit ihm über die paar Zeilen, die gerade
    # tatsächlich ausstehen.
    op.create_index(
        "idx_messages_cost_ausstehend",
        "messages",
        ["created_at"],
        postgresql_where=sa.text("cost_status = 'ausstehend'"),
    )


def downgrade() -> None:
    op.drop_index("idx_messages_cost_ausstehend", table_name="messages")
    op.drop_constraint(CHECK_NAME, "messages", type_="check")
    op.drop_column("messages", "cost_status")
