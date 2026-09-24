"""Wer welchen Knoten lesen darf — **eine** Klausel für alle Abfragewege.

Bis 09/2026 gab es zwei Regeln. Die richtige stand im Kontext-Router (Audit #1:
``group``-Knoten nur für Mitglieder der Gruppe), eine schwächere im Suchpfad — dort
genügte ``read_scope = 'group'``, ohne die Mitgliedschaft zu prüfen. Eine gruppenweit
freigegebene Aufgabe einer fremden Lerngruppe erschien damit in den Suchtreffern und
ging über das Chat-Werkzeug **mitsamt Inhalt** ans Modell.

Dass zwei Kopien einer Rechteprüfung auseinanderdriften, ist der Regelfall, nicht der
Ausnahmefall: Die eine wird gepflegt, die andere vergessen. Deshalb liegt die Regel
jetzt hier, und wer eine neue Abfrage über ``context_nodes`` baut, holt sie hier —
abschreiben ist der Fehler, den man erst bemerkt, wenn er wirkt.

**Die Regel** (absteigend geprüft):

* eigene Knoten immer — ``owner_pseudonym`` entscheidet vor allem anderen;
* ``private`` **nur** für die Eigentümer:in, auch Admins sehen fremde private Knoten
  nicht;
* ``global``, ``school``, ``subject`` für alle angemeldeten Nutzer:innen;
* ``group`` nur für Mitglieder der freigegebenen Gruppe — Admins ausgenommen.
* ``group_teachers`` nur für deren **Lehrkräfte** (Planungsknoten, Alembic 0074).
"""

from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy import and_, or_

from app.db.models import ContextNode, GroupMembership

# Scopes, die jede angemeldete Person lesen darf. `private` fehlt hier absichtlich und
# `group` ebenso — beide hängen an der Person, nicht am Scope allein.
OFFENE_SCOPES = ("global", "school", "subject")


def read_scope_clause(pseudonym: str, rollen: Iterable[str] = ()):
    """SQL-Bedingung für die von dieser Person lesbaren ``context_nodes``.

    ``rollen`` ist die Rollenliste aus dem JWT; ``admin`` hebt die Gruppenprüfung auf,
    nicht aber den Schutz fremder ``private``-Knoten.
    """
    rollen = set(rollen or ())

    if "admin" in rollen:
        return or_(
            ContextNode.read_scope.in_([*OFFENE_SCOPES, "group", "group_teachers"]),
            ContextNode.owner_pseudonym == pseudonym,
        )

    eigene_gruppen = (
        sa.select(GroupMembership.group_id)
        .where(GroupMembership.pseudonym == pseudonym)
        .scalar_subquery()
    )
    # ⚠️ **`group_teachers` nur mit Lehrkraft-Rolle.** Bis zum 24.09.2026 gab es den Wert
    # nicht, und Planungsknoten standen auf `group` — also lasen Schüler:innen der Gruppe
    # die Stundenentwürfe ihrer Lehrkraft, samt `metadata.reflexion`. Die Schreibprüfung
    # verlangte die Rolle längst; nur das Lesen tat es nicht.
    lehrkraft = "teacher" in rollen
    gruppenscopes = ["group", "group_teachers"] if lehrkraft else ["group"]
    return or_(
        ContextNode.read_scope.in_(OFFENE_SCOPES),
        ContextNode.owner_pseudonym == pseudonym,
        and_(
            ContextNode.read_scope.in_(gruppenscopes),
            ContextNode.read_scope_group_id.in_(eigene_gruppen),
        ),
    )
