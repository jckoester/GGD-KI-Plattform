"""Passen Scope und Trägergruppe eines Knotens zusammen?

Zwei Regeln, die bisher fehlten oder nur halb galten:

**1. Pflicht.** `read_scope`/`write_scope` von `subject` oder `group` verlangen die
zugehörige Gruppe — sonst wäre nicht bestimmt, wer lesen bzw. pflegen darf. Die
Datenbank erzwingt das (`check_context_nodes_*_group_id`), aber als IntegrityError:
Die Oberfläche bekäme einen 500 ohne Hinweis, was fehlt. Beim Anlegen wurde das
schon abgefangen, **beim Ändern nicht** — dort schlug es weiterhin durch.

**2. Art.** Ein `subject`-Scope meint die **Fachschaft**, ein `group`-Scope eine
Gruppe von Menschen. Geprüft hat das niemand: Bis 09/2026 boten beide
Knotenformulare unter „Fachgruppe" ausschließlich Unterrichtsgruppen an, auch bei
`write_scope = subject`. Die falsche Wahl wurde stumm gespeichert — ein Baustein,
der laut Scope der Fachschaft gehört, hing an einer Klasse. Aufgefallen ist das
nur, weil jemand das Formular benutzt hat.

**Warum die Artprüfung eng gefasst ist.** Sie behauptet nur die Entsprechung
`subject` ↔ `subject_department`, in beide Richtungen. Welche *Menschengruppe* zu
`group` passt, bleibt offen: Klasse, Unterrichtsgruppe, AG — und auch das
Kollegium (`teachers`) ist ein sinnvoller Träger für „alle Lehrkräfte, keine
Schüler:innen", wofür `school` zu weit wäre. Eine Positivliste hätte diesen Fall
verboten, ohne dass jemand ihn geprüft hat.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Group

#: Der Gruppentyp, der eine Fachschaft ist — Träger von `scope = subject`.
FACHSCHAFT = "subject_department"

#: Scopes, die überhaupt eine Gruppe brauchen.
BRAUCHT_GRUPPE = ("subject", "group")


async def pruefe_scope_gruppe(
    db: AsyncSession, *, feld: str, scope: str, gruppen_id: int | None
) -> None:
    """Prüft **einen** Scope samt Gruppe. Wirft ``ValueError`` mit Klartext.

    ``feld`` ist ``"read_scope"`` oder ``"write_scope"`` — es steht in der Meldung,
    damit die Oberfläche nicht raten muss, welches der beiden gemeint ist.
    """
    if scope not in BRAUCHT_GRUPPE:
        return

    if gruppen_id is None:
        raise ValueError(
            f"Bei `{feld} = {scope}` muss die zuständige Gruppe mitgegeben werden "
            f"(`{feld}_group_id`) — sonst wäre nicht bestimmt, wer den Baustein "
            "lesen bzw. pflegen darf."
        )

    typ = await db.scalar(sa.select(Group.type).where(Group.id == gruppen_id))
    if typ is None:
        raise ValueError(f"Die angegebene Gruppe zu `{feld}` gibt es nicht.")

    if scope == "subject" and typ != FACHSCHAFT:
        raise ValueError(
            f"`{feld} = subject` meint die Fachschaft, die angegebene Gruppe ist "
            f"aber vom Typ {typ!r}. Wähle eine Fachschaft — oder `{feld} = group`, "
            "wenn die Gruppe gemeint war."
        )
    if scope == "group" and typ == FACHSCHAFT:
        raise ValueError(
            f"`{feld} = group` meint eine Gruppe von Menschen, die angegebene ist "
            f"aber eine Fachschaft. Wähle `{feld} = subject`, wenn die Fachschaft "
            "zuständig sein soll."
        )


async def pruefe_scopes(
    db: AsyncSession,
    *,
    read_scope: str,
    read_gruppen_id: int | None,
    write_scope: str,
    write_gruppen_id: int | None,
) -> None:
    """Beide Scopes eines Knotens. Wirft ``ValueError`` beim ersten Verstoß."""
    await pruefe_scope_gruppe(
        db, feld="read_scope", scope=read_scope, gruppen_id=read_gruppen_id
    )
    await pruefe_scope_gruppe(
        db, feld="write_scope", scope=write_scope, gruppen_id=write_gruppen_id
    )
