"""Darf diese Person diesen Assistenten benutzen? — **eine** Regel für alle Wege.

⚠️ **Der Anlass war kein Schönheitsfehler** (Jan, 26.09.2026, in der Oberfläche
nachgestellt): `_is_visible_for_user` prüfte Zielgruppe und Zeitfenster — **nicht**
`scope` und **nicht** `scope_group_id`. Eine Freigabe „für diese Unterrichtsgruppe" war
damit keine Einschränkung, sondern eine Beschriftung: Fremde Schüler:innen sahen den
Assistenten in ihrer Liste. Und weil der Chat-Endpunkt dieselbe Funktion fragte, war
sogar ein **privater** Assistent für jeden benutzbar, der seine ID kannte — die
Listenabfrage filterte `private` zwar, der Chat-Weg nicht.

Genau diese Trennung ist die Falle: Die Liste beantwortete die Frage auf ihre Weise (als
SQL-Bedingung), der Chat auf seine (als Funktion), und nur eine der beiden kannte die
Scopes. Deshalb stehen hier **beide** Darstellungen nebeneinander —
:func:`darf_nutzen` und :func:`sichtbar_klausel` —, und ein Test lässt sie am selben
Bestand gegeneinander laufen. Dasselbe Muster wie bei den Wissensknoten
(:mod:`app.context.visibility`); es war nicht neu zu erfinden.

**Die Regel** (absteigend geprüft):

* Nur **aktive** Assistenten im Zeitfenster — gilt für alle, auch für die Erstellerin.
  Ein Entwurf gehört in den Editor, nicht in den Chat (zum Ausprobieren gibt es den
  Testlauf, der eigene Rechte prüft).
* **Eigene immer** — wer ihn angelegt hat, findet ihn (Entscheidung Jan, 27.09.2026).
* **`private`** danach für niemanden sonst.
* **Gruppen-Scopes** für Mitglieder der Gruppe — und für **Lehrkräfte** dieser Gruppe,
  auch wenn der Assistent an Schüler:innen gerichtet ist: Eine Lehrkraft muss wissen,
  womit ihre Klasse arbeitet, selbst wenn eine Kollegin ihn angelegt hat.
* **`teachers`** für Lehrkräfte und Admins.
* Schulweite Scopes für alle — dort entscheidet allein die Zielgruppe.

**Was hier bewusst *nicht* geprüft wird:** `min_grade`/`max_grade` und `visibility`
werden heute nirgends ausgewertet. Sie hier einzubauen hieße, zwei Zusagen zu erfinden,
die es bisher nicht gab; sie stehen als eigener Befund im Todo.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload
from app.db.models import Assistant, GroupMembership

#: Scopes, die an einer Gruppe hängen. Deckungsgleich mit `GROUP_SCOPES` im Router —
#: dort entscheidet sie über die Pflichtangabe beim Anlegen, hier über den Zugang.
GRUPPENSCOPES = frozenset({"subject_department", "activity_group", "teaching_group"})

#: Scopes, die niemanden ausschließen; über sie entscheidet allein die Zielgruppe.
OFFENE_SCOPES = frozenset({"grade", "all_students", "all"})


@dataclass(frozen=True)
class Zugang:
    """Was von einer Person für diese Frage zählt.

    Als Objekt, weil beide Darstellungen dieselben vier Angaben brauchen — und weil
    eine Funktion mit vier losen Parametern an zwei Aufrufstellen irgendwann drei hat.
    """

    pseudonym: str
    rollen: frozenset[str]
    #: Alle Gruppen, in denen die Person Mitglied ist.
    gruppen: frozenset[int]
    #: Davon die, in denen sie als Lehrkraft geführt wird.
    lehrgruppen: frozenset[int]

    @property
    def lehrkraft(self) -> bool:
        """Admin ist eine Erweiterung der Lehrkraft-Rolle (CLAUDE.md, Rollenmodell)."""
        return bool({"teacher", "admin"} & self.rollen)

    @property
    def schuelerin(self) -> bool:
        return "student" in self.rollen


async def lade_zugang(db: AsyncSession, user: JwtPayload) -> Zugang:
    """Die Mitgliedschaften einer Person — **eine** Abfrage für beide Wege."""
    zeilen = (await db.execute(
        sa.select(GroupMembership.group_id, GroupMembership.role_in_group)
        .where(GroupMembership.pseudonym == user.sub)
    )).all()
    return Zugang(
        pseudonym=user.sub,
        rollen=frozenset(user.roles or ()),
        gruppen=frozenset(g for g, _r in zeilen),
        lehrgruppen=frozenset(g for g, r in zeilen if r == "teacher"),
    )


def _zielgruppe_passt(audience: str, zugang: Zugang) -> bool:
    if audience == "all":
        return True
    if audience == "student":
        return zugang.schuelerin
    if audience == "teacher":
        return zugang.lehrkraft
    return False


def darf_nutzen(assistant: Assistant, zugang: Zugang, *, jetzt=None) -> bool:
    """Die Regel als Funktion — für einen einzelnen Assistenten (Chat, Detailansicht)."""
    jetzt = jetzt or datetime.now(timezone.utc)
    if assistant.status != "active":
        return False
    if assistant.available_from and assistant.available_from > jetzt:
        return False
    if assistant.available_until and assistant.available_until < jetzt:
        return False

    if assistant.created_by == zugang.pseudonym:
        return True

    if assistant.scope in GRUPPENSCOPES:
        gruppe = assistant.scope_group_id
        if gruppe is None:
            # Ein Gruppen-Scope ohne Gruppe schließt niemanden ein. Das Anlegen
            # verhindert es (422); ein Altbestand aus der Zeit davor soll nicht
            # versehentlich schulweit gelten.
            return False
        if gruppe in zugang.lehrgruppen and zugang.lehrkraft:
            return True
        if gruppe not in zugang.gruppen:
            return False
        return _zielgruppe_passt(assistant.audience, zugang)

    if assistant.scope == "teachers":
        return zugang.lehrkraft
    if assistant.scope in OFFENE_SCOPES:
        return _zielgruppe_passt(assistant.audience, zugang)

    # ⚠️ **Aufzählung, kein Rückfall — und das ist der Unterschied.** Bis hierher kommt
    # `private` und alles, was jemand später erfindet. Ein durchlässiges
    # `return _zielgruppe_passt(...)` am Ende (so stand es zuerst hier) gäbe einen neuen
    # Scope für alle frei, während die Abfrage ihn ausschlösse: Die beiden liefen
    # auseinander, ohne dass jemand die Regel angefasst hätte. Die Gegenprobe „nur die
    # Abfrage lässt `private` durch" blieb genau deshalb grün — dort **war** es schon
    # eine Aufzählung.
    return False


def sichtbar_klausel(zugang: Zugang, *, jetzt=None):
    """Dieselbe Regel als SQL-Bedingung — für die Liste.

    ⚠️ Wer hier etwas ändert, ändert :func:`darf_nutzen` mit.
    `tests/integration/test_assistenten_sichtbarkeit.py` lässt beide am selben Bestand
    gegeneinander laufen; auseinanderlaufen lassen sie sich nur, indem man den Test
    löscht.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    gruppen = list(zugang.gruppen) or [-1]
    lehrgruppen = list(zugang.lehrgruppen) or [-1]

    aktiv = and_(
        Assistant.status == "active",
        or_(Assistant.available_from.is_(None), Assistant.available_from <= jetzt),
        or_(Assistant.available_until.is_(None), Assistant.available_until >= jetzt),
    )
    zielgruppe = or_(
        Assistant.audience == "all",
        and_(Assistant.audience == "student", zugang.schuelerin),
        and_(Assistant.audience == "teacher", zugang.lehrkraft),
    )
    gruppenzugang = and_(
        Assistant.scope.in_(sorted(GRUPPENSCOPES)),
        # Redundant in SQL (`NULL IN (…)` ist nie wahr) und trotzdem hier: Sie sagt,
        # was gemeint ist — ein Gruppen-Scope ohne Gruppe schließt niemanden ein.
        Assistant.scope_group_id.is_not(None),
        or_(
            and_(Assistant.scope_group_id.in_(lehrgruppen), zugang.lehrkraft),
            and_(Assistant.scope_group_id.in_(gruppen), zielgruppe),
        ),
    )
    # Positivliste, spiegelbildlich zu `darf_nutzen`: `private` steht nicht darin und
    # ist damit ausgeschlossen, ohne dass es eigens verboten werden müsste.
    return and_(
        aktiv,
        or_(
            Assistant.created_by == zugang.pseudonym,
            gruppenzugang,
            and_(Assistant.scope == "teachers", zugang.lehrkraft),
            and_(Assistant.scope.in_(sorted(OFFENE_SCOPES)), zielgruppe),
        ),
    )
