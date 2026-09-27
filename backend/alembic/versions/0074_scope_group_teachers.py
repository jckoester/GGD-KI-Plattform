"""Neuer Sichtbarkeits-Scope `group_teachers` — Lehrkräfte einer Gruppe

Revision ID: 0074
Revises: 0073
Create Date: 2026-09-24

⚠️ **Der Anlass ist ein Datenschutzbefund** (gemessen 24.09.2026). Planungsknoten
(`unterrichtsstunde`, `unterrichtseinheit`, `jahresplan`) werden im Code mit
`read_scope = 'group'` angelegt. `group` heißt **alle Mitglieder** — also auch
Schüler:innen. Nachgestellt:

    GET /planning/lessons/{id}                        (Schüler:in) -> 403   ✓
    GET /context/nodes/{id}                           (Schüler:in) -> 200   ✗
    GET /context/nodes?content_type=unterrichtsstunde (Schüler:in) -> enthält den Entwurf

Ausgeliefert wurden `metadata.phasen` **und** `metadata.reflexion` — die Notiz, die die
Lehrkraft nach der Stunde über die Klasse schreibt.

Die Ursache war eine Asymmetrie: `_check_write_permission` verlangt bei `group`
zusätzlich die Lehrkraft-Rolle, `_check_read_permission` und `read_scope_clause` nicht.

**Warum ein eigener Wert statt einer Rollen-Sonderregel auf `group`.** Derselbe Scope
würde sonst je nach Fragendem etwas anderes bedeuten, und `group` bleibt für geteiltes
Gruppenmaterial gebraucht, das Schüler:innen sehen sollen. Der Wert sagt jetzt, was
gemeint ist.

**Die Restriktivitäts-Bedingung hat den Zuschnitt entschieden.** Sie verlangt
`write_rang <= read_rang` — schreiben darf nie weiter reichen als lesen. Ein Knoten mit
`read_scope='group_teachers'` und `write_scope='group'` verletzt das. Der neue Wert trägt
deshalb **beide** Seiten; `group_teachers` rangiert zwischen `private` und `group`.
"""
from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None

_SCOPES = "'global', 'school', 'subject', 'group', 'group_teachers', 'private'"
_MIT_GRUPPE = "'subject', 'group', 'group_teachers'"
_RANG = """
    CASE {spalte}
        WHEN 'private' THEN 0
        WHEN 'group_teachers' THEN 1
        WHEN 'group' THEN 2
        WHEN 'subject' THEN 3
        WHEN 'school' THEN 4
        WHEN 'global' THEN 5
    END
"""

_ALT_SCOPES = "'global', 'school', 'subject', 'group', 'private'"
_ALT_MIT_GRUPPE = "'subject', 'group'"
_ALT_RANG = """
    CASE {spalte}
        WHEN 'private' THEN 0
        WHEN 'group' THEN 1
        WHEN 'subject' THEN 2
        WHEN 'school' THEN 3
        WHEN 'global' THEN 4
    END
"""

# Nur diese drei Typen wandern mit. Andere `group`-Knoten sind geteiltes Material und
# sollen sichtbar bleiben — ein pauschales Umschreiben nähme Schüler:innen etwas weg,
# das für sie gedacht war.
_PLANUNGSTYPEN = "'unterrichtsstunde', 'unterrichtseinheit', 'jahresplan'"


def _setze_bedingungen(scopes: str, mit_gruppe: str, rang: str) -> None:
    for spalte in ("read", "write"):
        op.execute(f"ALTER TABLE context_nodes DROP CONSTRAINT IF EXISTS "
                   f"check_context_nodes_{spalte}_scope")
        op.execute(f"ALTER TABLE context_nodes ADD CONSTRAINT "
                   f"check_context_nodes_{spalte}_scope "
                   f"CHECK ({spalte}_scope IN ({scopes}))")
        op.execute(f"ALTER TABLE context_nodes DROP CONSTRAINT IF EXISTS "
                   f"check_context_nodes_{spalte}_group_id")
        op.execute(f"ALTER TABLE context_nodes ADD CONSTRAINT "
                   f"check_context_nodes_{spalte}_group_id "
                   f"CHECK ({spalte}_scope NOT IN ({mit_gruppe}) "
                   f"OR {spalte}_scope_group_id IS NOT NULL)")

    op.execute("ALTER TABLE context_nodes DROP CONSTRAINT IF EXISTS "
               "check_context_nodes_scope_restrictivity")
    op.execute(
        "ALTER TABLE context_nodes ADD CONSTRAINT "
        "check_context_nodes_scope_restrictivity CHECK ("
        + rang.format(spalte="write_scope") + " <= " + rang.format(spalte="read_scope") + ")"
    )


def upgrade() -> None:
    # ⚠️ **Erst die Bedingungen weiten, dann die Daten schreiben.** Andersherum bricht
    # das UPDATE an der alten Wertemenge ab.
    _setze_bedingungen(_SCOPES, _MIT_GRUPPE, _RANG)
    op.execute(f"""
        UPDATE context_nodes
        SET read_scope = 'group_teachers', write_scope = 'group_teachers'
        WHERE content_type IN ({_PLANUNGSTYPEN})
          AND read_scope = 'group' AND write_scope = 'group'
    """)


def downgrade() -> None:
    op.execute(f"""
        UPDATE context_nodes
        SET read_scope = 'group', write_scope = 'group'
        WHERE read_scope = 'group_teachers' OR write_scope = 'group_teachers'
    """)
    _setze_bedingungen(_ALT_SCOPES, _ALT_MIT_GRUPPE, _ALT_RANG)
