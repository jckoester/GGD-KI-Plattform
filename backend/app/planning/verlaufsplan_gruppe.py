"""Der Jahresverlaufsplan einer Unterrichtsgruppe (Päckchen BD Teil B, Schritt 1).

Welcher Plan zu einer Gruppe gehört (FB2, Jan 26.11.2026): der Plan ihres **Fachs** und ihrer
**Stufe** im **laufenden** Schuljahr — Entwurf oder beschlossen, auch ein Entwurf dient als
Vorlage. Die Stufe kommt aus :func:`app.groups.jahrgang.jahrgang_aus` (Festlegung, sonst die
kleinste Klasse, sonst der Name); ohne erkennbare Stufe gibt es keinen Plan, nur einen Hinweis.

Die Wahl steht bewusst in **einer** Funktion (:func:`plan_der_gruppe`): Bekommen Pläne später
Varianten (Todo, Jan 26.11.2026), wählt die Gruppe hier ihre Variante.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context import verlaufsplan as vp
from app.context.curriculum_entwurf import ENTWURF
from app.db.models import ContextNode, Group
from app.planning.curriculum_resolver import _group_grade

#: Warum eine Gruppe keinen Plan hat — die Oberfläche formuliert den Satz dazu.
KEIN_FACH, KEINE_STUFE, KEIN_PLAN = "kein_fach", "keine_stufe", "kein_plan"


@dataclass
class PlanDerGruppe:
    schuljahr: str
    stufe: Optional[int]
    plan: Optional[ContextNode]
    grund: Optional[str]


async def plan_der_gruppe(db: AsyncSession, group: Group) -> PlanDerGruppe:
    schuljahr = vp.aktuelles_schuljahr()
    if group.subject_id is None:
        return PlanDerGruppe(schuljahr, None, None, KEIN_FACH)
    stufe = await _group_grade(db, group)
    if stufe is None:
        return PlanDerGruppe(schuljahr, None, None, KEINE_STUFE)
    plan = (await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == vp.TYP,
            ContextNode.subject_id == group.subject_id,
            ContextNode.min_grade == stufe,
            ContextNode.metadata_["schuljahr"].as_string() == schuljahr,
            ContextNode.status.in_((ENTWURF, vp.BESCHLOSSEN)),
        ).limit(1)
    )).scalar_one_or_none()
    return PlanDerGruppe(schuljahr, stufe, plan, None if plan else KEIN_PLAN)


def wochenschluessel(montag: date) -> str:
    """ISO-Woche wie im Planer (`wochenSchluessel` in `lib/planner.js`): „2026-W38“."""
    jahr, woche, _ = montag.isocalendar()
    return f"{jahr}-W{woche:02d}"


def abschnitt_je_woche(lage: Optional[dict]) -> dict[str, int]:
    """{ISO-Woche: Index des Abschnitts} für die Wochen, die ein Abschnitt belegt.

    Der Planer zählt Kalenderwochen, der Plan Unterrichtswochen; verbunden sind beide über den
    Montag der Unterrichtswoche. Wochen hinter dem Schuljahresende haben keinen Montag und fallen
    heraus, freie Wochen ebenso. Puffer stehen drin — die Oberfläche zeigt sie als Puffer.
    """
    if not lage:
        return {}
    montag = {w["nr"]: w["montag"] for w in lage.get("wochen", [])}
    ergebnis: dict[str, int] = {}
    for i, a in enumerate(lage.get("abschnitte", [])):
        for nr in range(a["von_woche"], a["bis_woche"] + 1):
            if nr in montag:
                m = montag[nr]
                ergebnis[wochenschluessel(m if isinstance(m, date) else date.fromisoformat(m))] = i
    return ergebnis
