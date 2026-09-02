"""Knotentypen-Bereinigung V1–V5: sechs Typen gehen in vier auf

Die Taxonomie führte Typen, die sich **nur in der Herkunft** unterschieden oder für die
es überhaupt keinen Erzeugungsweg gab (Notiz-Knotentyp-Vereinfachung, ADR-019):

| entfällt        | geht auf in                          |
|-----------------|--------------------------------------|
| `aufgabenblatt` | `artifact/arbeitsblatt` (V1)         |
| `gliederung`    | `strukturierung`, `form=gliederung`  |
| `mindmap`       | `strukturierung`, `form=mindmap` (V2)|
| `operator_math` | `begriff` (V4)                       |
| `abstrakt`      | `begriff` (V5)                       |
| `reflexion`     | — (V3, siehe unten)                  |

⚠️ **Diese Migration muss vor dem neuen Code laufen** — genauer: mit ihm im selben
Release. Die Startprüfung (ADR-018) lässt das Backend nicht hochfahren, solange Knoten
einen Typ tragen, den die Taxonomie nicht mehr kennt. Das ist Absicht: Ein Bestand ohne
Zuständigkeit fällt sonst monatelang niemandem auf.

**`reflexion` hat kein Ziel.** Der Typ hatte nie einen Erzeugungsweg — Reflexionen
schreibt der Review-Workflow als `metadata.reflexion` an den Stunden-Knoten
(`app/planning/review_service.py`). Es gibt deshalb nichts, wohin ein solcher Knoten
sinnvoll wandern könnte, und diese Migration erfindet nichts: Findet sie welche, bricht
sie ab und nennt den Weg. Erwartet wird das nicht (Dev: 0 Knoten).

Idempotent und leerlauffähig: Alle UPDATEs sind an den alten Typ gebunden, ein zweiter
Lauf trifft nichts mehr.

Revision ID: 0055
Revises: 0054
"""

import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    verbindung = op.get_bind()

    # ── V3: Abbruch statt stillem Waisen ─────────────────────────────────────
    reflexionen = verbindung.execute(
        sa.text("SELECT count(*) FROM context_nodes WHERE content_type = 'reflexion'")
    ).scalar()
    if reflexionen:
        raise RuntimeError(
            f"{reflexionen} Knoten vom Typ 'reflexion' gefunden. Der Typ entfällt (V3), "
            "hat aber kein Ziel: Reflexionen leben als `metadata.reflexion` am "
            "Stunden-Knoten. Diese Knoten sind von Hand entstanden und brauchen eine "
            "Entscheidung — Inhalt an die zugehörige Stunde übertragen, in einen "
            "anderen Typ überführen oder löschen:\n"
            "  SELECT id, title, owner_pseudonym FROM context_nodes "
            "WHERE content_type = 'reflexion';\n"
            "Danach diese Migration erneut ausführen."
        )

    # ── V1: aufgabenblatt → artifact/arbeitsblatt ────────────────────────────
    # Einziger Fall mit Kategoriewechsel: `document` → `artifact`. Beide Typen waren
    # Material, die Material-Listen ändern sich dadurch nicht.
    op.execute(
        "UPDATE context_nodes SET category = 'artifact', content_type = 'arbeitsblatt' "
        "WHERE content_type = 'aufgabenblatt'"
    )

    # ── V2: gliederung/mindmap → strukturierung mit metadata.form ────────────
    # Die Form geht nicht verloren, sie wandert ins Metadatum. `metadata` ist NOT NULL
    # mit Vorgabe '{}', `||` verträgt trotzdem kein NULL — daher COALESCE.
    for alt in ("gliederung", "mindmap"):
        op.execute(
            sa.text(
                "UPDATE context_nodes SET content_type = 'strukturierung', "
                "metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('form', :form) "
                "WHERE content_type = :alt"
            ).bindparams(form=alt, alt=alt)
        )

    # ── V4/V5: operator_math und abstrakt → begriff ──────────────────────────
    # Beide sind bereits `concept`; nur der content_type ändert sich.
    op.execute(
        "UPDATE context_nodes SET content_type = 'begriff' "
        "WHERE content_type IN ('operator_math', 'abstrakt')"
    )

    # **Kein Re-Embedding nötig, und das ist geprüft, nicht gehofft.** Ein Vektor wird
    # ungültig, wenn sich die Formel des Typs ändert — `embedding_input` oder
    # `embedding_enrichment` (siehe `_build_embedding_input`). Keiner der beteiligten
    # Typen hat eines von beidem: Alle laufen über den Standardaufbau (`content`, Titel
    # davor, wo er eigene Information trägt), und der hängt am Inhalt, nicht am Typ.
    # Die bestehenden Vektoren bleiben also vergleichbar.
    #
    # Ein Fall wird neu einzubetten sein: `operator_math` trug kein Embedding, `begriff`
    # trägt eins. Diese Knoten haben `embedding IS NULL` und werden vom nächsten
    # `embedding_backfill.py`-Lauf von selbst erfasst — hier ist nichts zu tun.

    # ── V3-Folge: Stunden mit Reflexion neu einbetten ────────────────────────
    # Mit dem Wegfall des eigenen Typs zieht `metadata.reflexion` in den
    # `embedding_input` der `unterrichtsstunde` ein — damit „Was habe ich mir zu X
    # notiert?" beantwortbar bleibt. **Hier ändert sich die Formel wirklich**, und ein
    # Vektor nach alter Formel ist mit neuen nicht vergleichbar.
    #
    # Betroffen sind nur Stunden, die tatsächlich eine Reflexion tragen: Bei den übrigen
    # liefert die neue Quelle einen leeren Teil, der herausfällt — der Input bleibt Zeichen
    # für Zeichen derselbe. Deshalb genau diese und nicht alle: Ein Re-Embedding kostet
    # einen Modellaufruf je Knoten.
    #
    # `embedding = NULL` ist das Signal an `scripts/embedding_backfill.py` (täglich 03:15
    # in der Compose). Bis er läuft, ist die Stunde thematisch nicht auffindbar — über
    # Name und Aufzählung bleibt sie erreichbar. Wer nicht warten will, startet ihn von
    # Hand.
    op.execute(
        "UPDATE context_nodes SET embedding = NULL "
        "WHERE content_type = 'unterrichtsstunde' AND metadata ? 'reflexion'"
    )


def downgrade() -> None:
    """Nicht rückführbar — und das ist keine Nachlässigkeit.

    Nach V1 ist ein `arbeitsblatt` nicht mehr von einem unterscheidbar, das schon immer
    eines war; nach V4/V5 ein `begriff` nicht mehr von einem, der als `operator_math`
    oder `abstrakt` begann. Die Herkunft steht nirgends, weil sie keine Mechanik trägt —
    genau das war die Begründung der Zusammenlegung.

    Wer zurück muss, spielt ein Backup ein.
    """
    raise NotImplementedError(
        "0055 ist nicht rückführbar: Die zusammengelegten Typen sind nach der Migration "
        "nicht mehr auseinanderzuhalten. Backup einspielen."
    )
