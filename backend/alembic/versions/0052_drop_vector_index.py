"""Vektorindex entfernen — die semantische Suche läuft exakt

Der HNSW-Index ``idx_context_nodes_embedding`` lieferte nicht die ähnlichsten Knoten,
sondern eine Auswahl daraus. Gemessen am Prüfsatz (``config/search_eval.yaml``,
15 Anfragen, 14.244 Vektoren, 30.08.2026):

===========================================  ==========  ================
Zustand                                       Recall@10  richtiges Fach
                                                          auf Platz 1
===========================================  ==========  ================
Ausgangszustand                                    48 %            8/15
nach ``REINDEX``                                   65 %            6/15
``REINDEX`` mit ``maintenance_work_mem=1GB``       65 %            7/15
Neuaufbau ``m=32, ef_construction=200``            71 %            6/15
ohne Index (exakte Suche)                         100 %           11/15
===========================================  ==========  ================

Weder ein Neuaufbau noch stärkere Parameter bringen ihn auf ein brauchbares Maß, und beim
praktisch entscheidenden Wert — steht das richtige Fach oben? — verbessert er sich gar
nicht. ``hnsw.ef_search`` ist keine Stellschraube: Ab 100 hält der Planer den Indexscan
für teurer als den vollständigen Durchlauf und wählt letzteren; höhere Werte schalten den
Index also faktisch ab, statt ihn zu verbessern.

**Warum er hier scheitert**, zeigt der Prüfsatz selbst: Zwischen Platz 1 und Platz 10 der
exakten Trefferliste liegen im Median nur 0,063 Ähnlichkeit (bei 0,569 auf Platz 1). Die
Kandidaten liegen dicht beieinander — der Greedy-Abstieg durch den Graphen hat kaum ein
Gefälle, dem er folgen könnte. Das ist keine Fehlkonfiguration, sondern eine Eigenschaft
dieses Bestands: 14.000 Kompetenztexte derselben Textsorte, derselben Sprache, mit
denselben Wendungen.

**Was das kostet:** Der vollständige Durchlauf über 14.244 Vektoren dauert 40–55 ms
(gegen 1,4 ms mit Index). Neben einem LLM-Aufruf von mehreren Sekunden fällt das nicht
ins Gewicht. Er trägt bis grob 150.000 Knoten; siehe docs/admin/vor-der-installation.md
für die Betriebsschwelle und die Stellschrauben.

Die Abfragen ändern sich **nicht**: Ohne Index wählt PostgreSQL von sich aus den
vollständigen Durchlauf.

Revision ID: 0052
Revises: 0051
"""

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF EXISTS: Migration 0043 (Vektorbreite) legt den Index seit derselben Änderung
    # nicht mehr neu an — auf einer frischen Installation ist hier also schon keiner mehr
    # da, auf einer bestehenden sehr wohl.
    op.execute("DROP INDEX IF EXISTS idx_context_nodes_embedding")


def downgrade() -> None:
    op.execute(
        """
        CREATE INDEX idx_context_nodes_embedding
        ON context_nodes
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        WHERE embedding IS NOT NULL
        """
    )
