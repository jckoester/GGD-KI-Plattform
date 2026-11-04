"""Welche Assistenten sieht eine Schüler:in dieser Gruppe? (0.32, Päckchen AJ)

Für den Reiter „Assistenten“ der Gruppenseite. Beantwortet wird die Frage mit **derselben**
Regel wie in Chat und Assistentenliste (`app/assistants/sichtbarkeit.py`) — über einen
nachgebauten Schüler-`Zugang`, nicht mit einer zweiten, eigenen Auswahl. Eine Liste, die
anders rechnet als der Chat, wäre schlimmer als keine.

Der nachgebaute Zugang: Rolle `student`, Mitglied **nur** dieser Gruppe, Jahrgang der Gruppe
(oder gewählt, Plan F1), Modellfreigabe dieser Stufe, eigene Assistenten zählen nicht (eine
Schüler:in sieht die Entwürfe ihrer Lehrkraft nicht). Was eine einzelne Schüler:in über
**andere** Gruppen zusätzlich sieht (AGs, andere Fächer), kann diese Liste nicht zeigen — es
hängt an der Person, nicht an der Gruppe.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistants.sichtbarkeit import (
    GRUPPENSCOPES, Zugang, sichtbar_klausel, warum_nicht,
)
from app.db.models import Assistant, Group
from app.litellm.team_models import erlaubte_modelle_fuer
from app.planning.curriculum_resolver import group_grade


@dataclass
class Schuelersicht:
    jahrgang: int | None
    #: ``festgelegt`` (an der Gruppe gespeichert), ``abgeleitet`` (aus Klassen oder Name),
    #: ``gewaehlt`` (im Reiter), ``None`` (unbekannt — dann gilt kein Stufenfilter).
    jahrgang_quelle: str | None
    #: Ist die Modellfreigabe der Stufe bekannt? Ohne Jahrgang oder ohne Proxy nicht — dann
    #: wird, wie im Chat, nicht nach Modell gefiltert.
    modelle_bekannt: bool
    fuer_die_gruppe: list[Assistant] = field(default_factory=list)
    schulweit: list[Assistant] = field(default_factory=list)
    #: Eigene Assistenten der Lehrkraft, die die Gruppe nicht sieht — mit Grund (Plan F4 a).
    eigene_unsichtbar: list[tuple[Assistant, str]] = field(default_factory=list)


async def zugang_fuer_gruppe(gruppe: Group, jahrgang: int | None) -> Zugang:
    """Der Zugang einer gedachten Schüler:in, die nur Mitglied dieser Gruppe ist."""
    modelle = await erlaubte_modelle_fuer(["student"], jahrgang) if jahrgang is not None else None
    return Zugang(
        # Kein echtes Pseudonym: Die gedachte Schüler:in hat keine eigenen Assistenten.
        pseudonym=f"schuelersicht:{gruppe.id}",
        rollen=frozenset({"student"}),
        gruppen=frozenset({gruppe.id}),
        lehrgruppen=frozenset(),
        stufe=jahrgang,
        modelle=frozenset(modelle) if modelle is not None else None,
        eigene=False,
    )


async def schuelersicht(
    db: AsyncSession, gruppe: Group, *, lehrkraft: str, jahrgang_wahl: int | None = None,
) -> Schuelersicht:
    """Sichtbare Assistenten der Gruppe und die eigenen, die sie nicht sieht."""
    if jahrgang_wahl is not None:
        jahrgang, quelle = jahrgang_wahl, "gewaehlt"
    elif gruppe.jahrgang is not None:
        jahrgang, quelle = gruppe.jahrgang, "festgelegt"
    else:
        jahrgang = await group_grade(db, gruppe.id)
        quelle = "abgeleitet" if jahrgang is not None else None

    zugang = await zugang_fuer_gruppe(gruppe, jahrgang)
    ergebnis = Schuelersicht(jahrgang=jahrgang, jahrgang_quelle=quelle,
                             modelle_bekannt=zugang.modelle is not None)

    sichtbar = (await db.execute(
        sa.select(Assistant).where(sichtbar_klausel(zugang)).order_by(Assistant.name)
    )).scalars().all()
    for a in sichtbar:
        if a.scope in GRUPPENSCOPES:
            ergebnis.fuer_die_gruppe.append(a)
        else:
            ergebnis.schulweit.append(a)

    gesehen = {a.id for a in sichtbar}
    eigene = (await db.execute(
        sa.select(Assistant).where(Assistant.created_by == lehrkraft).order_by(Assistant.name)
    )).scalars().all()
    for a in eigene:
        if a.id in gesehen:
            continue
        grund = warum_nicht(a, zugang)
        # „Kein Grund“ hieße: sichtbar, aber nicht in der Abfrage — Klausel und Erklärung
        # wären uneins. Das verhindert der Wächtertest; hier bliebe der Eintrag nur weg.
        if grund is not None:
            ergebnis.eigene_unsichtbar.append((a, grund))
    return ergebnis
