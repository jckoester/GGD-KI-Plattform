"""Abschnitt „Andere allgemeine Assistenten“ (0.26, Plan „Rückfall-Assistenten“, Schritt 3).

Ein Rückfall-Assistent (`suggest: fallback`) bekommt im Chat einer Schüler:in die Liste der
übrigen Rückfall-Assistenten, die sie nutzen darf — je Name und `suggestion_text`, also
derselbe Satz wie im Vorschlagsdialog. Was er damit tut, sagt der Baustein „Begleiten statt
lösen“: Passt einer besser, ist der erste Satz der Hinweis darauf; steht keiner da, verweist
er auf niemanden.

Aus dem Bestand gebaut, nicht in den Prompt geschrieben: So bleibt der Prompt stabil gegen
Umbenennungen und gegen Nachbarn, die es in dieser Schule (noch) nicht gibt.

⚠️ **Zur Probe behalten (Jan, 29.10.2026, F21).** Seit 0.26 bietet der Vorschlag auch in der
Assistenten-Konversation Rückfälle an (Klassifikator mit der letzten Antwort als Kontext). Der
Abschnitt bleibt trotzdem vorerst: Er ist der einzige Hinweis, wenn der Vorfilter keinen
Kandidaten findet. Steht der Hinweis in der Praxis doppelt da, entfällt er. Spezifische
Assistenten stehen nicht darin.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistants.sichtbarkeit import Zugang, sichtbar_klausel
from app.db.models import Assistant

UEBERSCHRIFT = "## Andere allgemeine Assistenten"


def abschnitt(eintraege: list[tuple[str, str]]) -> str:
    """Aus (Name, Satz) den Abschnitt; leer, wenn es keinen gibt."""
    if not eintraege:
        return ""
    zeilen = [f"- Assistent für {name}: {satz}" for name, satz in eintraege]
    return (f"{UEBERSCHRIFT}\n\nDiese Assistenten kann die Schüler:in außerdem wählen "
            "(in der Assistentenauswahl oder mit „/“):\n" + "\n".join(zeilen))


def andere_namen(text: str) -> list[str]:
    """Die Namen in einem Abschnitt aus :func:`abschnitt` — für den Messkanal."""
    vorn = "- Assistent für "
    return [z[len(vorn):].split(": ", 1)[0] for z in text.splitlines() if z.startswith(vorn)]


async def andere_allgemeine(db: AsyncSession, zugang: Zugang, eigene_id: int) -> str:
    """Die übrigen Rückfall-Assistenten, die diese Person nutzen darf, als Abschnitt."""
    zeilen = (await db.execute(
        sa.select(Assistant.name, Assistant.suggestion_text)
        .where(sichtbar_klausel(zugang), Assistant.suggest == "fallback",
               Assistant.visibility != "hidden", Assistant.id != eigene_id,
               Assistant.suggestion_text.is_not(None))
        .order_by(Assistant.sort_order, Assistant.name)
    )).all()
    return abschnitt([(n, s.strip()) for n, s in zeilen if s and s.strip()])
