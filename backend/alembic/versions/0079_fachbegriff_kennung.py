"""Stabile Kennung (`seed_id`) für importierte Fachbegriffe

Revision ID: 0079
Revises: 0078
Create Date: 2026-09-27

Bis Paket 9 erkannte der Import einen Knoten am **Dateinamen**
(`metadata.seed_quelle`). Wer eine Datei im Vault umbenannte — beim Pflegen die
Regel, nicht die Ausnahme —, bekam beim nächsten Lauf einen zweiten Knoten und merkte
es erst in der Sammlung. Seit Paket 10/AP2 trägt jeder importierte Knoten eine
**Kennung**, die das Umbenennen übersteht (Entscheidung D3).

Diese Migration rüstet den Bestand nach: `seed_id` aus Fachkürzel und Herkunftsdatei,
nach derselben Regel wie :func:`app.context.fachbegriffe_import.leite_id_ab`.

⚠️ **Dieselbe Regel an zwei Orten** — hier als SQL, dort als Python. Auseinanderlaufen
würde nicht knallen, sondern leise wirken: Der nächste Import fände den Knoten nicht
über die Kennung, fiele auf `seed_quelle` zurück und schriebe eine zweite. Deshalb hält
`tests/integration/test_seed_id_sql.py` beide Seiten an echten Pilot-Dateinamen
zusammen.

**`updated_at` bleibt stehen** — gewollt, aber nicht mein Verdienst: Der Stempel hängt
an SQLAlchemys `onupdate`, und rohes SQL geht daran vorbei. Richtig so: `updated_at`
beantwortet seit Paket 9 „wie aktuell ist dieser Knoten?", und eine nachgetragene
Kennung ist keine Bearbeitung. Der Import macht dasselbe ausdrücklich
(`_trage_kennung_nach`), weil er über die ORM schreibt.

**Dateinamen ohne Slug** (nur Sonderzeichen) bleiben unberührt: Eine Kennung zu
erfinden, die niemand wiedererkennt, wäre schlechter als keine. Der Import meldet
solche Dateien und verlangt ein `id:` im Frontmatter.
"""
from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

TYPEN = ("begriff", "stoffsteckbrief")


def slug_sql(ausdruck: str) -> str:
    """Die Slug-Regel als SQL: klein, Umlaute ausgeschrieben, Rest zu Bindestrichen.

    `translate()` taugt nicht — es bildet Zeichen auf Zeichen ab, und `ß` wird zu
    **zwei**. Deshalb geschachtelte `replace()`.
    """
    klein = f"lower({ausdruck})"
    for von, nach in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        klein = f"replace({klein}, '{von}', '{nach}')"
    return f"trim(both '-' from regexp_replace({klein}, '[^a-z0-9]+', '-', 'g'))"


def kennung_sql(fach_ausdruck: str, datei_ausdruck: str) -> str:
    """Fachkürzel + Dateiname → Kennung, wie `leite_id_ab()` sie baut."""
    return (
        f"trim(both '-' from ({slug_sql(fach_ausdruck)} || '-' "
        f"|| {slug_sql(datei_ausdruck)}))"
    )


_KENNUNG = kennung_sql("coalesce(s.fach_code, s.slug)", "n.metadata->>'seed_quelle'")
_TYPEN_SQL = ", ".join(f"'{t}'" for t in TYPEN)


def upgrade_sql() -> str:
    """Als Funktion, damit `tests/integration/test_seed_id_sql.py` die Anweisung selbst
    ausführen kann — eine Migration, die nur im Vorbeigehen läuft, ist ungeprüft."""
    return f"""
        UPDATE context_nodes n
        SET metadata = jsonb_set(n.metadata, '{{seed_id}}', to_jsonb({_KENNUNG}))
        FROM subjects s
        WHERE s.id = n.subject_id
          AND n.content_type IN ({_TYPEN_SQL})
          AND n.metadata ? 'seed_quelle'
          AND NOT (n.metadata ? 'seed_id')
          AND {slug_sql("n.metadata->>'seed_quelle'")} <> ''
    """


def downgrade_sql() -> str:
    """Kennung wieder entfernen.

    Verlustfrei, solange der Code von vorher zurückkommt: Der findet die Knoten über
    `seed_quelle`, das die Migration nie angefasst hat. Kennungen, die der neue Import
    inzwischen selbst vergeben hat, fallen mit weg — sie stehen ohnehin in den Dateien
    bzw. entstehen beim nächsten Lauf neu.
    """
    return f"""
        UPDATE context_nodes
        SET metadata = metadata - 'seed_id'
        WHERE content_type IN ({_TYPEN_SQL}) AND metadata ? 'seed_id'
    """


def upgrade() -> None:
    op.execute(upgrade_sql())


def downgrade() -> None:
    op.execute(downgrade_sql())
