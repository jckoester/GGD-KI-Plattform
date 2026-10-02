"""Das Systemkonto: Modellaufrufe, die keiner Person gehören (0.12, AP3).

Heute ist das genau eine Stelle — die Einbettungen in `context/embedding.py`, also Suche,
Import und Backfill. Bild und Titel laufen über den Virtual Key der Nutzerin; die übrigen
Master-Key-Aufrufe in `client.py` sind Verwaltung und kosten nichts.

Zwei Dinge gehören dazu:

* **Der Schlüssel.** `LITELLM_SYSTEM_KEY`, mit Rückfall auf den Master-Key — eine
  bestehende Installation darf davon nicht stehenbleiben. Der Rückfall meldet sich beim
  Start. Mit eigenem Schlüssel trägt keine Suche mehr den Schlüssel, der alles darf, und
  LiteLLM führt die Ausgaben getrennt.
* **Der Betrag.** Aus dem Antwortkopf `x-litellm-response-cost`, je Tag aufsummiert in
  `system_spend`. Gezählt wird unabhängig vom Schlüssel, also auch im Rückfall.

Der Betrag ist winzig (gemessen 01.09.: rund 0,0000005 USD je Suche). Gezeigt wird er
nicht zur Kostenkontrolle, sondern damit „klein" gewusst und nicht angenommen wird.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

BERLIN = ZoneInfo("Europe/Berlin")
KOSTENKOPF = "x-litellm-response-cost"


def schluessel() -> str:
    """Der Schlüssel für Systemaufrufe — der eigene, sonst der Master-Key."""
    return settings.litellm_system_key or settings.litellm_master_key


def pruefe_beim_start() -> bool:
    """Meldet den Rückfall auf den Master-Key. Bewusst **weich**: Es funktioniert ja."""
    if settings.litellm_system_key:
        return True
    logger.warning(
        "LITELLM_SYSTEM_KEY ist nicht gesetzt — Einbettungen für Suche und Import laufen "
        "über den Master-Key. Das funktioniert, aber jede Suche trägt dann den Schlüssel, "
        "der alles darf, und LiteLLM führt die Ausgaben nicht getrennt. Schlüssel anlegen: "
        "docs/admin/installation.md, Abschnitt „Systemschlüssel“."
    )
    return False


def kosten_aus_antwort(antwort) -> float | None:
    """Betrag aus dem Antwortkopf; ``None``, wenn er fehlt oder unbrauchbar ist.

    Nur Zeichenketten zählen — httpx liefert Kopfwerte als ``str``, alles andere ist
    keine Antwort des Proxys.
    """
    wert = antwort.headers.get(KOSTENKOPF)
    if not isinstance(wert, str):
        return None
    try:
        betrag = float(wert)
    except ValueError:
        return None
    if not math.isfinite(betrag) or betrag < 0:
        return None
    return betrag


async def verbuche(antwort, *, sitzungen=None) -> None:
    """Addiert den Betrag einer Antwort zur Summe des heutigen (Berliner) Tages.

    Ohne Kostenkopf wird nichts gebucht — auch nicht die Anfrage: Eine Zahl Anfragen
    ohne Betrag sähe aus wie „kostet nichts".

    ⚠️ Wirft nie. Eine Suche, die an ihrer eigenen Abrechnung scheitert, wäre ein
    schlechter Tausch für einen Betrag von Bruchteilen eines Cents. Eigene Sitzung, weil
    der Aufrufer keine hat (Suche) oder sie für anderes braucht (Backfill).
    """
    betrag = kosten_aus_antwort(antwort)
    if betrag is None:
        return
    from app.db.models import SystemSpend

    if sitzungen is None:
        from app.db.session import AsyncSessionLocal as sitzungen

    neu = insert(SystemSpend).values(
        tag=datetime.now(BERLIN).date(), kosten_usd=betrag, anfragen=1
    )
    neu = neu.on_conflict_do_update(
        index_elements=[SystemSpend.tag],
        set_={
            "kosten_usd": SystemSpend.kosten_usd + neu.excluded.kosten_usd,
            "anfragen": SystemSpend.anfragen + 1,
        },
    )
    try:
        async with sitzungen() as db:
            await db.execute(neu)
            await db.commit()
    except Exception:
        logger.exception("Systemkosten nicht verbucht (%s)", betrag)


async def summe(db: AsyncSession, von: date, bis: date | None = None) -> tuple[float, int]:
    """Betrag und Anfragen von ``von`` bis ``bis`` — beide einschließlich, Berliner Tage."""
    from app.db.models import SystemSpend

    abfrage = select(
        func.coalesce(func.sum(SystemSpend.kosten_usd), 0.0),
        func.coalesce(func.sum(SystemSpend.anfragen), 0),
    ).where(SystemSpend.tag >= von)
    if bis is not None:
        abfrage = abfrage.where(SystemSpend.tag <= bis)
    betrag, anfragen = (await db.execute(abfrage)).one()
    return float(betrag), int(anfragen)
