"""Namen zu Begriffen — viele auf einmal, für ein Fach (0.44, Päckchen AQ).

Bis 0.43 schlug die Planung jeden Namen einzeln nach (`begriff_zum_titel`, eine bis zwei
Abfragen je Name). Ein Curriculum nennt Hunderte; gemessen (AQ Schritt 0, 300 Namen gegen
Chemie): je Name 769 ms, gebündelt 12,5 ms. Deshalb holt :func:`begriffe_abgleichen` alle
Schlüssel samt Einzahlformen in **einer** Abfrage und wendet die Regeln danach in Python an.
Die Planung läuft auf derselben Funktion — zwei Abgleiche nebeneinander drifteten auseinander.

**Die Regeln** (unverändert aus `begriff_zum_titel`, gemessenes Verhalten des
Stundenassistenten):

1. Gesucht wird über Titel und Aliase, normalisiert wie der Index (`TITEL_NORMALISIERT`,
   `ALIAS_NORMALISIERT`), im Fach und seinen Bezugsfächern, nur unter dem, was die Person
   lesen darf (`read_scope_clause`).
2. Ist eine Fassung angegeben, zählen nur Treffer dieser Fassung.
3. Bleiben mehrere und genau einer liegt im eigenen Fach, gilt der.
4. Trifft der Name nichts, gilt eine Einzahlform (`einzahlformen`) — aber nur, wenn sie
   genau einen Begriff trifft; sonst bleibt der Name *fehlt* (nicht *mehrdeutig*).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.aliase import ALIAS_NORMALISIERT
from app.context.filters import TITEL_NORMALISIERT
from app.context.lookup import einzahlformen, normalisiere_titel
from app.db.models import ContextNode, NodeAlias
from app.planning.schemas import BEGRIFF_TYPEN

#: Bindestriche, die ein Modell statt „-" schreibt. `gpt-oss-120b` setzt durchweg den
#: geschützten Bindestrich U+2011 („Arenium‑Ion") — in Messung 3 (0.17) scheiterten daran
#: alle Begriffe zweier Läufe, obwohl sie als Alias bestanden. Nur auf der Seite der Eingabe
#: ersetzt: Die Normalisierung der Datenbankseite ist die des Index (`titel_normalisiert_sql`)
#: und muss es bleiben. Das weiche Trennzeichen U+00AD fällt weg.
BINDESTRICHE = str.maketrans({"‐": "-", "‑": "-", "­": None})

Zustand = Literal["gefunden", "fehlt", "mehrdeutig"]


@dataclass
class Abgleich:
    """Ergebnis für einen Namen. `knoten` nur bei *gefunden*, `kandidaten` nur bei *mehrdeutig*."""

    name: str
    fassung: str | None
    zustand: Zustand
    knoten: ContextNode | None = None
    kandidaten: list[ContextNode] = field(default_factory=list)


def schluessel(name: str) -> str:
    """Der Vergleichsschlüssel eines eingegebenen Namens."""
    return normalisiere_titel(str(name).translate(BINDESTRICHE))


def _fassung(knoten: ContextNode) -> str:
    return str((knoten.metadata_ or {}).get("fassung") or "").strip().casefold()


async def begriffe_abgleichen(
    db: AsyncSession, user, subject_id: int, namen: list[tuple[str, str | None]],
    *, bezugsfaecher: tuple[int, ...] | None = None,
) -> list[Abgleich]:
    """Gleicht `namen` (Name, Fassung oder None) gegen die Begriffe des Fachs ab.

    Eine Abfrage für alle Namen; Reihenfolge des Ergebnisses = Reihenfolge der Eingabe.
    `bezugsfaecher` erspart die Abfrage, wenn der Aufrufer sie schon kennt.
    """
    from app.context.service import bezugsfaecher_von
    from app.context.visibility import read_scope_clause

    if not namen:
        return []
    if bezugsfaecher is None:
        bezugsfaecher = tuple(await bezugsfaecher_von(db, subject_id))
    faecher = (subject_id, *bezugsfaecher)

    eigene = [schluessel(n) for n, _ in namen]
    alle = list(dict.fromkeys(s for k in eigene for s in (k, *einzahlformen(k)) if s))

    je_schluessel: dict[str, dict[UUID, ContextNode]] = {}
    if alle:
        # Ein Alias trägt nur bei, wenn er selbst passt — sonst ergäbe der Join je Alias des
        # Begriffs eine Zeile.
        zeilen = (await db.execute(
            sa.select(ContextNode, TITEL_NORMALISIERT, ALIAS_NORMALISIERT)
            .outerjoin(NodeAlias, sa.and_(NodeAlias.node_id == ContextNode.id, ALIAS_NORMALISIERT.in_(alle)))
            .where(
                ContextNode.content_type.in_(BEGRIFF_TYPEN),
                ContextNode.status == "active",
                read_scope_clause(user.sub, getattr(user, "roles", None) or ()),
                ContextNode.subject_id.in_(faecher),
                sa.or_(TITEL_NORMALISIERT.in_(alle), NodeAlias.id.is_not(None)),
            )
        )).all()
        gesucht = set(alle)
        for knoten, titel_k, alias_k in zeilen:
            for k in (titel_k, alias_k):
                if k in gesucht:
                    je_schluessel.setdefault(k, {})[knoten.id] = knoten

    def suche(schl: list[str], fassung: str | None) -> list[ContextNode]:
        treffer: dict[UUID, ContextNode] = {}
        for s in schl:
            treffer.update(je_schluessel.get(s, {}))
        liste = sorted(treffer.values(), key=lambda t: t.id)  # wie bisher: order_by(id)
        if fassung:
            gewuenscht = fassung.translate(BINDESTRICHE).strip().casefold()
            liste = [t for t in liste if _fassung(t) == gewuenscht]
        if len(liste) > 1:
            im_fach = [t for t in liste if t.subject_id == subject_id]
            if len(im_fach) == 1:
                liste = im_fach
        return liste

    ergebnis = []
    for (name, fassung), k in zip(namen, eigene):
        treffer = suche([k], fassung)
        if not treffer and (formen := einzahlformen(k)):
            einzahl = suche(formen, fassung)
            if len(einzahl) == 1:
                ergebnis.append(Abgleich(name, fassung, "gefunden", einzahl[0]))
                continue
        if len(treffer) == 1:
            ergebnis.append(Abgleich(name, fassung, "gefunden", treffer[0]))
        elif not treffer:
            ergebnis.append(Abgleich(name, fassung, "fehlt"))
        else:
            ergebnis.append(Abgleich(name, fassung, "mehrdeutig", kandidaten=treffer))
    return ergebnis
