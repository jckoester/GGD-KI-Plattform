"""Vorschaumodus: die App als Schüler:in sehen (0.29, Päckchen S, ADR-016, Ansatz C).

**Ansatz C.** Das Vorschau-Token trägt die Rolle ``student`` und den gewählten Jahrgang. Alles,
was über **Rollen** entscheidet — `require_role`, die Pädagogik im Chat, die Modellfreigabe —,
sieht damit von selbst eine Schüler:in. Das Pseudonym bleibt das der Lehrkraft: Budget,
Kosten, Eigentum und Audit-Spur bleiben bei ihr. Die echten Rollen stehen nur im Merkmal
:class:`Vorschau`, gebraucht für den Rückweg.

Übrig bleibt, was über das **Pseudonym** entscheidet:

* **Mitgliedschaften.** Die Lehrkraft ist in ihren Gruppen als Lehrkraft eingetragen. In der
  Vorschau gilt stattdessen genau die gewählte Gruppe, und dort als Schüler:in — ohne Gruppe
  keine. Jede Abfrage der eigenen Mitgliedschaften läuft deshalb über :func:`mitglied`;
  `tests/unit/test_vorschau_mitgliedschaft_quelltext.py` verbietet den direkten Vergleich
  ``GroupMembership.pseudonym == …``.
* **Eigentum.** Eigene, nicht freigegebene Assistenten und private Kontextknoten der
  Lehrkraft sieht eine Schüler:in nicht — in der Vorschau also auch nicht
  (:func:`eigenes_zaehlt`).

**Warum die Vorschau für die Dauer der Anfrage gemerkt wird** und nicht als Parameter
durchgereicht: Die Mitgliedschaften werden an rund dreißig Stellen gelesen, meist in
Hilfsfunktionen, die nur das Pseudonym bekommen. Allen den Benutzer durchzureichen hieße,
Signaturen quer durch Kontext, Planung und Chat zu ändern — und eine vergessene Stelle fiele
nicht auf. :func:`get_current_user` setzt den Wert bei **jeder** Anfrage (auch auf „keine
Vorschau“), damit nichts aus einer früheren Anfrage desselben Tasks stehen bleibt; die
Helfer greifen nur, wenn das gefragte Pseudonym das der Vorschau ist.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from pydantic import BaseModel

from app.db.models import GroupMembership

if TYPE_CHECKING:
    from app.auth.jwt import JwtPayload


class Vorschau(BaseModel):
    """Das Merkmal im Vorschau-Token: wer man wirklich ist und was simuliert wird."""

    #: Die Rollen der Sitzung, aus der die Vorschau begann — für den Rückweg.
    echte_rollen: list[str]
    echter_jahrgang: str | None = None
    #: Die simulierte Unterrichtsgruppe (F3: nur eigene des laufenden Schuljahres).
    gruppe_id: int | None = None
    #: Eingetreten aus dem Editor (F6): dieser Assistent ist benutzbar, auch als Entwurf.
    assistent_id: int | None = None
    #: Beginn der Vorschau (Unix-Zeit).
    beginn: int
    #: Ablauf der Sitzung, aus der die Vorschau begann (Unix-Zeit). Der Rückweg stellt ein
    #: Token mit **diesem** Ablauf aus — die Vorschau verlängert die Sitzung nicht (F1).
    sitzung_ablauf: int


#: (Pseudonym, Vorschau) der laufenden Anfrage, sonst ``None``.
_AKTIV: ContextVar[Optional[tuple[str, Vorschau]]] = ContextVar("vorschau", default=None)


def fuer_anfrage(user: "JwtPayload") -> None:
    """Merkt sich die Vorschau dieser Anfrage — oder dass es keine gibt."""
    vorschau = getattr(user, "preview", None)
    _AKTIV.set((user.sub, vorschau) if vorschau is not None else None)


def ist_vorschau(user: "JwtPayload") -> bool:
    return getattr(user, "preview", None) is not None


def aktive(pseudonym: str) -> Optional[Vorschau]:
    """Die Vorschau dieser Anfrage, falls sie für ``pseudonym`` gilt."""
    aktiv = _AKTIV.get()
    if aktiv is None or aktiv[0] != pseudonym:
        return None
    return aktiv[1]


def mitglied(pseudonym: str, rolle: str | None = None):
    """SQL-Bedingung auf ``GroupMembership``: die Mitgliedschaften dieser Person.

    ``rolle`` schränkt auf ``role_in_group`` ein. In der Vorschau zählt nur die gewählte
    Gruppe — die Lehrkraft ist dort (F3) tatsächlich Mitglied, die Zeile existiert also —,
    und zwar als Schüler:in: Die Frage nach ``teacher`` ist immer falsch, die nach
    ``student`` für diese Gruppe wahr.
    """
    vorschau = aktive(pseudonym)
    if vorschau is None:
        bedingung = GroupMembership.pseudonym == pseudonym
        if rolle is not None:
            bedingung = sa.and_(bedingung, GroupMembership.role_in_group == rolle)
        return bedingung
    if vorschau.gruppe_id is None or rolle not in (None, "student"):
        return sa.false()
    return sa.and_(
        GroupMembership.pseudonym == pseudonym,
        GroupMembership.group_id == vorschau.gruppe_id,
    )


def rolle_in_gruppe(pseudonym: str, rolle: str | None) -> str | None:
    """``role_in_group`` einer gelesenen Zeile, wie die Vorschau sie sieht."""
    return "student" if aktive(pseudonym) is not None else rolle


def eigenes_zaehlt(pseudonym: str) -> bool:
    """Gilt „das gehört mir“ als Zugang? In der Vorschau nicht — eine Schüler:in sieht die
    Entwürfe und privaten Knoten ihrer Lehrkraft auch nicht."""
    return aktive(pseudonym) is None


def eintrittsassistent(pseudonym: str) -> int | None:
    """Der Assistent, mit dem die Vorschau aus dem Editor begann (F6), sonst ``None``."""
    vorschau = aktive(pseudonym)
    return vorschau.assistent_id if vorschau is not None else None
