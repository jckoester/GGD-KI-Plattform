"""Begriffe und Fachmethoden am Eintrag eines Curriculums (0.44, Päckchen AQ).

**Gespeichert wird Text, keine Kante** (E1): Ein Eintrag in `lernsequenz.metadata.eintraege`
trägt

    begriffe:     [{"name": "Oxidation", "fassung": "Elektronen"}, {"name": "Redoxreihe"}]
    fachmethoden: [{"name": "Säure-Base-Titration"}]

`fassung` steht nur, wo jemand eine gewählt hat (E4). Fachmethoden haben dasselbe Format, damit
ein späterer Typ `fachmethode` auf dieselbe Weise andocken kann (E2); aufgelöst werden sie
noch nicht.

**Aufgelöst wird beim Lesen** (:func:`begriffe_aufloesen`), und zwar nur im Lesen und Ändern
des Curriculums im Router — nicht in `load_curriculum_tree`: Die Funktion kennt die lesende
Person nicht, und Export und Neuverknüpfen brauchen nur die Namen. Das Ergebnis steht neben
dem Baum, nicht in ihm: Der Editor schreibt die Einträge als Ganzes zurück, und eine
Auflösung in den Einträgen landete sonst in der Datenbank.
"""
from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.begriffe_abgleich import begriffe_abgleichen, schluessel
from app.db.models import ContextNode, Subject

#: Obergrenzen je Eintrag — ein Curriculum ist kein Glossar; ein Name ist kein Absatz.
NAMEN_JE_EINTRAG = 50
NAME_LAENGE = 200

FELDER = ("begriffe", "fachmethoden")


def namen_normalisieren(roh: Any, *, mit_fassung: bool = True) -> list[dict]:
    """Eingabe aus Zwischenformat, YAML oder Editor → gespeichertes Format.

    Nimmt Texte (`"Oxidation"`) und Objekte (`{"name": …, "fassung": …}`); leere Namen fallen
    weg, Leerraum wird zusammengezogen, Dubletten (gleicher Schlüssel und gleiche Fassung)
    ebenso. Was keine Liste ist, ergibt eine leere Liste.
    """
    if not isinstance(roh, list):
        return []
    aus: list[dict] = []
    gesehen: set[tuple[str, str]] = set()
    for e in roh:
        if isinstance(e, str):
            name, fassung = e, None
        elif isinstance(e, dict):
            name, fassung = e.get("name"), e.get("fassung") if mit_fassung else None
        else:
            continue
        name = " ".join(str(name or "").split())[:NAME_LAENGE]
        fassung = " ".join(str(fassung or "").split())[:NAME_LAENGE] or None
        if not name:
            continue
        k = (schluessel(name), (fassung or "").casefold())
        if k in gesehen:
            continue
        gesehen.add(k)
        aus.append({"name": name, "fassung": fassung} if fassung else {"name": name})
        if len(aus) >= NAMEN_JE_EINTRAG:
            break
    return aus


def eintrag_felder(begriffe: Any, fachmethoden: Any) -> dict:
    """Die beiden Felder für einen Eintrag — nur, was belegt ist."""
    aus = {}
    if b := namen_normalisieren(begriffe):
        aus["begriffe"] = b
    if f := namen_normalisieren(fachmethoden, mit_fassung=False):
        aus["fachmethoden"] = f
    return aus


def _begriffe_im_baum(tree: dict) -> list[tuple[str, str | None]]:
    """Alle (Name, Fassung) der Einträge, in Reihenfolge des Auftretens, ohne Wiederholung."""
    paare: dict[tuple[str, str | None], None] = {}
    for kap in tree.get("kapitel") or []:
        for ls in kap.get("lernsequenzen") or []:
            for e in (ls.get("metadata") or {}).get("eintraege") or []:
                if not isinstance(e, dict):
                    continue
                for b in namen_normalisieren(e.get("begriffe")):
                    paare.setdefault((b["name"], b.get("fassung")), None)
    return list(paare)


def _knoten_kurz(k: ContextNode, faecher: dict[int, str]) -> dict:
    return {
        "node_id": str(k.id),
        "titel": k.title,
        "fassung": (k.metadata_ or {}).get("fassung") or None,
        "subject_id": k.subject_id,
        "fach": faecher.get(k.subject_id),
    }


async def namen_aufloesen(db: AsyncSession, user, subject_id: int | None,
                          paare: list[tuple[str, str | None]]) -> list[dict]:
    """(Name, Fassung) → Auflösung, wie sie Editor und Übersicht lesen.

    Je Paar: `name`, `fassung` (wie gespeichert), `zustand` (*gefunden*, *fehlt*,
    *mehrdeutig*), bei *gefunden* der Baustein (`node_id`, `titel`, `subject_id`, `fach`,
    `bezugsfach` — liegt er nicht im Fach des Curriculums, E9), bei *mehrdeutig* die
    `kandidaten`. Ohne Fach ist alles *fehlt*.
    """
    if not paare:
        return []
    if subject_id is None:
        return [{"name": n, "fassung": f, "zustand": "fehlt"} for n, f in paare]
    abgleich = await begriffe_abgleichen(db, user, subject_id, paare)

    fach_ids = {k.subject_id for a in abgleich for k in ([a.knoten] if a.knoten else a.kandidaten)}
    faecher = dict((await db.execute(
        sa.select(Subject.id, Subject.name).where(Subject.id.in_(fach_ids))
    )).all()) if fach_ids else {}

    aus = []
    for a in abgleich:
        eintrag: dict[str, Any] = {"name": a.name, "fassung": a.fassung, "zustand": a.zustand}
        if a.knoten is not None:
            eintrag |= _knoten_kurz(a.knoten, faecher) | {"bezugsfach": a.knoten.subject_id != subject_id}
            eintrag["fassung"] = a.fassung  # die gespeicherte, nicht die des Bausteins
        elif a.kandidaten:
            eintrag["kandidaten"] = [_knoten_kurz(k, faecher) for k in a.kandidaten]
        aus.append(eintrag)
    return aus


async def begriffe_aufloesen(db: AsyncSession, tree: dict, user) -> list[dict]:
    """Die Begriffe aller Einträge eines Curriculums, aufgelöst für `user` — eine Abfrage."""
    return await namen_aufloesen(db, user, tree.get("subject_id"), _begriffe_im_baum(tree))
