"""Aliase als eigene Tabelle statt als Metadaten-Krücke

Bis hierher lagen weitere Namen eines Bausteins als JSON-Liste in `metadata.aliase`.
Das trug für die zwei Typen, die sie pflegen (`methode`, `sozialform`), reichte aber nur
fürs Embedding: Die **Namenssuche sah sie nie**. Wer „Think-Pair-Share" tippte, fand
„Ich-Du-Wir" nicht, obwohl der Alias gepflegt war.

Ein Alias soll sich verhalten wie ein zweiter Titel — exakter Treffer **und** Ähnlichkeit.
Die Ähnlichkeitsstufe hängt am Trigramm-Index, und den gibt es nur auf einer Textspalte,
nicht über Elemente eines JSON-Arrays. Deshalb die Tabelle.

⚠️ **Die Einfügereihenfolge wird bewahrt.** Für `methode` und `operator` gehen die Aliase
in den Embedding-Input ein; eine andere Reihenfolge ergäbe einen anderen Eingabetext und
damit unvergleichbare Vektoren. Der Backfill schreibt in Array-Reihenfolge
(`WITH ORDINALITY`), gelesen wird nach `id` — der zusammengesetzte String bleibt
zeichengleich, ein Re-Embedding ist nicht nötig.

Die drei Ausdrucksindizes liegen auf **derselben** Normalisierung wie die Titel-Indizes
aus 0053/0054 (`app.context.lookup.titel_normalisiert_sql`). Weicht die Abfrage davon ab,
benutzt PostgreSQL sie stillschweigend nicht — dasselbe stille Versagen, vor dem schon
0054 warnt.

Revision ID: 0057
Revises: 0056
"""

from alembic import op

from app.context.lookup import titel_normalisiert_sql

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

NORM = titel_normalisiert_sql("alias")

# ── Der Backfill, als Konstanten ─────────────────────────────────────────────
#
# Herausgezogen, damit ein Integrationstest **genau dieses** SQL gegen gesetzte Daten
# laufen lassen kann. In den Tests wird das Schema leer aufgebaut; die Migration liefe
# dort also über einen leeren Bestand und bewiese nichts — ausgerechnet beim einzigen
# Teil, der genau einmal und dann gegen den echten Bestand läuft.

BACKFILL_SQL = f"""
    INSERT INTO node_aliases (node_id, alias)
    SELECT node_id, alias FROM (
        SELECT DISTINCT ON (n.id, {NORM})
               n.id AS node_id, a.alias, a.ord
          FROM context_nodes n
          CROSS JOIN LATERAL jsonb_array_elements_text(n.metadata->'aliase')
               WITH ORDINALITY AS a(alias, ord)
         WHERE jsonb_typeof(n.metadata->'aliase') = 'array'
           AND btrim(a.alias) <> ''
         ORDER BY n.id, {NORM}, a.ord
    ) q
    ORDER BY q.node_id, q.ord
"""

# Die Krücke entfernen — zwei Wahrheiten für dieselbe Sache sind schlimmer als eine
# unbequeme. Wer die alten Werte braucht, findet sie in dieser Migration.
AUFRAEUMEN_SQL = """
    UPDATE context_nodes
       SET metadata = metadata - 'aliase'
     WHERE metadata ? 'aliase'
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("""
        CREATE TABLE node_aliases (
            id         bigserial PRIMARY KEY,
            node_id    uuid NOT NULL REFERENCES context_nodes(id) ON DELETE CASCADE,
            alias      text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_node_aliases_node ON node_aliases (node_id)")
    # Exakter Treffer — das Gegenstück zu 0053 für Titel.
    op.execute(f"CREATE INDEX idx_node_aliases_norm ON node_aliases (({NORM}))")
    # Teiltreffer — das Gegenstück zu 0054.
    op.execute(
        f"CREATE INDEX idx_node_aliases_trigramm ON node_aliases "
        f"USING gin (({NORM}) gin_trgm_ops)"
    )
    # Ein Alias je Knoten nur einmal — verglichen wird normalisiert, sonst stünden
    # „Think-Pair-Share" und „think pair share" nebeneinander.
    op.execute(
        f"CREATE UNIQUE INDEX uq_node_aliases_node_norm ON node_aliases (node_id, ({NORM}))"
    )

    # Backfill: `WITH ORDINALITY` hält die Array-Reihenfolge fest, `ORDER BY` beim
    # Einfügen bildet sie auf die aufsteigende `id` ab. `DISTINCT ON` fängt Dubletten in
    # der Quelle ab, die der Unique-Index sonst zurückwiese.
    op.execute(BACKFILL_SQL)
    op.execute(AUFRAEUMEN_SQL)


def downgrade() -> None:
    # Zurück in die Metadaten, damit ein Rückschritt keine Daten verliert.
    op.execute("""
        UPDATE context_nodes n
           SET metadata = n.metadata || jsonb_build_object('aliase', q.aliase)
          FROM (
                SELECT node_id, jsonb_agg(alias ORDER BY id) AS aliase
                  FROM node_aliases
                 GROUP BY node_id
               ) q
         WHERE q.node_id = n.id
    """)
    op.execute("DROP TABLE IF EXISTS node_aliases")
