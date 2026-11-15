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


def eintraege_normalisieren(metadata: dict) -> dict:
    """`metadata` einer Lernsequenz mit normalisierten Feldern an jedem Eintrag (Kopie).

    Für den allgemeinen Schreibweg (`PATCH /context/nodes/{id}`), über den der Editor die
    Einträge als Ganzes schickt. Andere Schlüssel bleiben unberührt; leere Felder fallen weg.
    """
    eintraege = metadata.get("eintraege")
    if not isinstance(eintraege, list):
        return metadata
    neu = []
    for e in eintraege:
        if isinstance(e, dict) and any(f in e for f in FELDER):
            e = {k: v for k, v in e.items() if k not in FELDER} | eintrag_felder(e.get("begriffe"), e.get("fachmethoden"))
        neu.append(e)
    return {**metadata, "eintraege": neu}


#: Wie viele Vorschläge die Eingabe der Fachmethoden höchstens bekommt.
FACHMETHODEN_VORSCHLAEGE = 15

_FACHMETHODEN_SQL = sa.text("""
    SELECT f->>'name' AS name, count(*) AS anzahl
    FROM context_nodes n
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(n.metadata->'eintraege') = 'array' THEN n.metadata->'eintraege' ELSE '[]' END) e
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(e->'fachmethoden') = 'array' THEN e->'fachmethoden' ELSE '[]' END) f
    WHERE n.id IN :ids
      AND jsonb_typeof(f) = 'object' AND coalesce(f->>'name', '') <> ''
    GROUP BY 1
""").bindparams(sa.bindparam("ids", expanding=True))


async def fachmethoden_des_fachs(db: AsyncSession, user, subject_id: int | None, q: str = "") -> list[dict]:
    """Fachmethoden aus den Einträgen der lesbaren Curricula eines Fachs, mit Häufigkeit.

    Je Schlüssel (wie beim Abgleich) die häufigste Schreibweise. Gefiltert wird auf `q`
    (enthält, ohne Groß-/Kleinschreibung); wer damit beginnt, steht vorn.
    """
    from app.context.visibility import read_scope_clause

    if subject_id is None:
        return []
    ids = list((await db.execute(sa.select(ContextNode.id).where(
        ContextNode.content_type == "lernsequenz",
        ContextNode.status == "active",
        ContextNode.subject_id == subject_id,
        read_scope_clause(user.sub, getattr(user, "roles", None) or ()),
    ))).scalars())
    if not ids:
        return []
    zeilen = (await db.execute(_FACHMETHODEN_SQL, {"ids": ids})).all()

    je_schluessel: dict[str, dict[str, int]] = {}
    for name, anzahl in zeilen:
        je_schluessel.setdefault(schluessel(name), {})[name] = int(anzahl)
    gesucht = schluessel(q) if q.strip() else ""
    aus = []
    for k, schreibweisen in je_schluessel.items():
        if gesucht and gesucht not in k:
            continue
        name = max(schreibweisen, key=lambda s: (schreibweisen[s], s))
        aus.append({"name": name, "anzahl": sum(schreibweisen.values()), "_vorn": bool(gesucht) and k.startswith(gesucht)})
    aus.sort(key=lambda m: (not m["_vorn"], -m["anzahl"], m["name"].casefold()))
    return [{"name": m["name"], "anzahl": m["anzahl"]} for m in aus[:FACHMETHODEN_VORSCHLAEGE]]
