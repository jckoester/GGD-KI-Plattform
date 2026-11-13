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

from app.db.models import Conversation, GroupMembership

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


# ── Schreibsperre (0.29, Schritt 3) ─────────────────────────────────────────────
#
# In der Vorschau ändert sich nichts am Konto der Lehrkraft. Rollengeprüfte Wege sperrt die
# Rolle `student` von selbst; offen blieben die rund vierzig schreibenden Wege, die auch
# Schüler:innen benutzen dürfen — sie schrieben in Einstellungen, Bibliothek, Zugangstoken,
# Gruppenbeitritte der Lehrkraft. Deshalb hier **eine** Regel für alle: Schreibendes ist
# gesperrt, außer was auf der Liste steht. `get_current_user` ruft sie bei jeder Anfrage,
# also erreicht sie jeden angemeldeten Weg ohne Zutun der Route.
#
# Geführt über die Endpunkt-Funktion, nicht über den Pfad: Mit verschachtelt eingebundenen
# Routern fehlt in der Pfadvorlage das äußere Präfix (`/auth`), der Name der Funktion
# dagegen ist eindeutig. `tests/unit/test_vorschau_schreibsperre.py` prüft, dass es jeden
# Namen gibt.

SCHREIBEND = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Schreibende Wege, die in der Vorschau offen bleiben.
ERLAUBT: dict[str, str] = {
    "app.chat.router.chat": "Ausprobieren ist der Zweck der Vorschau",
    "app.chat.router.variiere_generiertes_bild": "Bild im Chat abwandeln — Teil des Chats",
    "app.chat.router.update_conversation": "nur Vorschau-Chats (`darf_chat_sehen`)",
    "app.chat.router.delete_conversation": "nur Vorschau-Chats (`darf_chat_sehen`)",
    "app.upload.router.upload_session": "Datei für den Chat",
    "app.feedback.router.create_feedback": "Rückmeldung aus der Vorschau (ADR-020, feedback.preview)",
    "app.context.router.search_context_nodes": "rechnet nur",
    "app.api.pii.pii_scan": "rechnet nur",
    "app.render.router.render_block": "rechnet nur (Cache)",
    "app.artifacts.router.ggb_from_source": "rechnet nur (GeoGebra-Datei aus dem Chat, speichert nichts)",
    "app.auth.router.logout": "Abmelden beendet auch die Vorschau",
    "app.auth.vorschau_router.vorschau_betreten": "weist selbst ab (409, keine Verschachtelung)",
}

#: Wege, die in der Vorschau auch lesend gesperrt sind.
AUCH_LESEND_GESPERRT: dict[str, str] = {
    "app.auth.router.step_up_challenge": "erneute Anmeldung für die Krisen-Einsicht",
}

GESPERRT_TEXT = "In der Vorschau lässt sich nichts ändern."


def endpunkt_name(endpunkt) -> str | None:
    if endpunkt is None:
        return None
    return f"{endpunkt.__module__}.{endpunkt.__qualname__}"


def pruefe_schreibsperre(scope: dict, methode: str, user: "JwtPayload") -> None:
    """403, wenn eine Vorschau einen gesperrten Weg nimmt."""
    if not ist_vorschau(user):
        return
    name = endpunkt_name(scope.get("endpoint"))
    if name in AUCH_LESEND_GESPERRT or (methode in SCHREIBEND and name not in ERLAUBT):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail=GESPERRT_TEXT)


# ── Vorschau-Chats (0.29, Schritt 4) ────────────────────────────────────────────
#
# Ein Chat aus der Vorschau trägt `preview_context`. In der Vorschau sind nur solche Chats
# erreichbar — die echten Chats der Lehrkraft sieht eine Schüler:in nicht. Außerhalb darf die
# Lehrkraft ihre Vorschau-Chats lesen und löschen (eigene Liste), aber nicht fortsetzen: Sie
# liefen sonst mit Lehrkraft-Kontext weiter, in einem Chat, der als Schülersicht begann.


def chat_kontext(user: "JwtPayload") -> dict | None:
    """Was ein neuer Chat als `preview_context` bekommt — ``None`` außerhalb der Vorschau."""
    v = getattr(user, "preview", None)
    if v is None:
        return None
    return {"jahrgang": user.grade, "gruppe_id": v.gruppe_id,
            "assistent_id": v.assistent_id, "beginn": v.beginn}


def eigene_chats(user: "JwtPayload", *, vorschau_liste: bool = False):
    """SQL-Bedingung für Listen: in der Vorschau nur Vorschau-Chats; außerhalb ohne sie,
    außer ``vorschau_liste`` fragt ausdrücklich nach ihnen."""
    nur_vorschau = ist_vorschau(user) or vorschau_liste
    return sa.and_(
        Conversation.pseudonym == user.sub,
        Conversation.preview_context.is_not(None) if nur_vorschau
        else Conversation.preview_context.is_(None),
    )


def darf_chat_sehen(konversation, user: "JwtPayload") -> bool:
    """Einzelner Chat lesen, umbenennen, löschen."""
    if konversation is None or konversation.pseudonym != user.sub:
        return False
    return not ist_vorschau(user) or konversation.preview_context is not None


def darf_chat_fortsetzen(konversation, user: "JwtPayload") -> bool:
    """Weiterschreiben: nur in derselben Welt, in der der Chat entstand."""
    if not darf_chat_sehen(konversation, user):
        return False
    return ist_vorschau(user) == (konversation.preview_context is not None)



# ── Lernstand (0.29, Schritt 6) ─────────────────────────────────────────────────


def schreibt_lernstand(user: "JwtPayload") -> bool:
    """Darf aus dieser Anfrage persönlicher Lernstand (`node_engagement` je Pseudonym)
    entstehen? In der Vorschau nie: Was eine Lehrkraft als Schüler:in ausprobiert, ist kein
    Lernen (ADR-016).

    Heute schreibt niemand persönlichen Lernstand aus dem Chat — der einzige Schreiber ist
    der Gruppenstand der Nachbereitung, ein Lehrkraft-Weg. Wer einen Schreiber einführt,
    fragt hier; `tests/unit/test_lernstand_schreiber.py` erinnert daran.
    """
    return not ist_vorschau(user)
