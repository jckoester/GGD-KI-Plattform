"""context_nodes.embedding auf die konfigurierte Vektorbreite bringen

Stellt die Spaltenbreite auf ``settings.embedding_dimensions`` (Env ``EMBEDDING_DIMENSIONS``)
um. Anders als die übrigen Migrationen ist diese damit **konfigurationsabhängig** — und
bewusst so: Die Spaltenbreite ist ein Schema-Constraint, das zum eingesetzten
Embedding-Modell passen muss.

**Idempotent:** Entspricht die Spalte bereits der Konfiguration, passiert NICHTS. Ohne
diesen Vergleich würde das erste ``alembic upgrade head`` auf einer bestehenden Datenbank
sämtliche Embeddings verwerfen, obwohl sich das Modell nicht geändert hat (der Default
entspricht dem bisherigen Stand).

**Späteren Modellwechsel NICHT über diese Migration fahren.** Alembic führt eine bereits
angewendete Revision nicht erneut aus, und ``downgrade 0042 && upgrade head`` würde alle
Revisionen oberhalb von 0042 mit aus- und wieder einbauen. Für den Wechsel im Betrieb:

    python scripts/resize_embedding_column.py --yes
    python scripts/embedding_backfill.py --batch-size 100

Beide Pfade teilen die Implementierung in ``app/db/embedding_column.py``, damit sie nicht
auseinanderlaufen. Siehe docs/runbooks/modellwechsel.md.

Bis das Re-Embedding durch ist, liefert die semantische Suche keine Treffer
(``retrieval.py`` und ``chat/router.py`` filtern auf ``embedding IS NOT NULL``) — sauberer
Funktionsausfall ohne Fehler, aber terminierungsbedürftig.

Revision ID: 0043
Revises: 0042
"""

import logging

from alembic import context, op

from app.config import settings
from app.db.embedding_column import resize_embedding_column

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _apply(target: int) -> None:
    if context.is_offline_mode():
        # Die Idempotenz-Sperre muss die aktuelle Spaltenbreite aus dem Katalog lesen; das
        # ist ohne Verbindung unmöglich. Lieber verständlich abbrechen als ein SQL-Skript
        # ausgeben, das im Zweifel alle Embeddings verwirft.
        raise RuntimeError(
            "Migration 0043 kann nicht im Offline-Modus (--sql) laufen: Sie vergleicht die "
            "tatsächliche Spaltenbreite mit der Konfiguration. Online migrieren oder "
            "scripts/resize_embedding_column.py verwenden."
        )

    result = resize_embedding_column(op.get_bind(), target)
    if not result.changed:
        logger.info(
            "context_nodes.embedding hat bereits vector(%d) — übersprungen, "
            "Embeddings bleiben erhalten.", result.target,
        )
        return
    logger.info(
        "context_nodes.embedding: vector(%s) → vector(%d)", result.previous, result.target
    )
    if result.cleared:
        logger.warning(
            "%d Embeddings verworfen (anderer Vektorraum). Vollständiges Re-Embedding "
            "nötig: python scripts/embedding_backfill.py", result.cleared,
        )


def upgrade() -> None:
    _apply(settings.embedding_dimensions)


def downgrade() -> None:
    # Vor dieser Migration galt durchgängig vector(1536) aus 0018 — unabhängig davon,
    # womit `upgrade()` gelaufen ist.
    _apply(1536)
