"""Begriffe der Stunde — was Leiste, Werkzeug und Vorschlag gemeinsam brauchen (0.18).

Bis 0.17 lag der Abgleich allein im Werkzeugmodul (`assistant_tools.py`). Mit der Leiste,
die Aliase einzeln bearbeitet, und dem Vorschlag aus den Phasentexten braucht ihn mehr als
ein Weg; er zieht schrittweise hierher (Plan „Begriffe aus den Phasentexten", Schritt 3/5).
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.context import aliase as aliase_modul
from app.planning.schemas import LessonRefItem


async def nur_aliase_des_knotens(db: AsyncSession, refs: list[LessonRefItem]) -> list[LessonRefItem]:
    """Aliase an Begriffen auf die beschränken, die der Knoten wirklich hat — in dessen
    Schreibweise; Kompetenzen tragen keine.

    `PATCH /planning/lessons` übernahm bis 0.18 `aliase` ungeprüft vom Client. Die Leiste
    schickt nur gespeicherte Schreibweisen (entfernen, oder das Alias, über das die Suche
    traf) — alles andere wäre ein erfundener Name, der dann in Leiste, Export und
    Klassenarbeits-Umfang stünde. Strenger als der Abgleich des Werkzeugs: kein
    Einzahl-Rückfall, denn den braucht nur ein Modell, das frei formuliert.
    """
    mit_aliasen = [r.node_id for r in refs if r.typ == "concept" and r.aliase]
    bekannt = await aliase_modul.lade_viele(db, mit_aliasen)
    ergebnis = []
    for ref in refs:
        if not ref.aliase:
            ergebnis.append(ref)
            continue
        if ref.typ != "concept":
            ergebnis.append(ref.model_copy(update={"aliase": []}))
            continue
        je_form = {aliase_modul.normalisiere(a): a for a in bekannt.get(ref.node_id, [])}
        geprueft = [je_form[f] for f in (aliase_modul.normalisiere(a) for a in ref.aliase) if f in je_form]
        ergebnis.append(ref.model_copy(update={"aliase": list(dict.fromkeys(geprueft))}))
    return ergebnis
