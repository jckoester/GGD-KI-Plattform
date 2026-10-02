"""Zusätzliches Budget von Hand aufbuchen (0.12, Paket 2, AP1).

**Was ein Zuschlag ist.** Ein Betrag, der **obendrauf** kommt: Er wird sofort am Proxy
gesetzt und hebt zugleich den Deckel der Wochenaufstockung (`accrual.berechne`,
`zusatz_usd`), sodass die Aufstockung danach normal weiterläuft. Ohne diesen zweiten Teil
wäre er eine Vorauszahlung der kommenden Wochen — gemessen: sieben Wochen ohne Zuwachs.

**Reihenfolge je Person: erst der Proxy, dann die Zeile.** Schlägt der Proxy fehl, wird
keine Zeile geschrieben — die Person taucht in `fehlgeschlagen` auf, und ein zweiter
Versuch bucht **nicht doppelt**. Die umgekehrte Reihenfolge hätte für den häufigeren
Fehlerfall (Proxy kurz weg) eine Zeile ohne angehobene Grenze hinterlassen, und ein
erneuter Versuch hätte den Betrag zweimal verbucht.

Bleibt ein seltener Rest: Hebt der Proxy an und scheitert danach das Commit, steht die
Grenze ohne Zeile da. Das wird laut geloggt, mit den betroffenen Pseudonymen — eine
stille Abweichung wäre schlimmer als eine sichtbare.

⚠️ **Unbegrenzte Konten werden nicht angefasst.** `max_budget = None` heißt bei LiteLLM
„kein Limit". Darauf einen Betrag zu setzen, hieße, ein unbegrenztes Konto zu begrenzen —
das Gegenteil eines Zuschlags.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BudgetGrant
from app.litellm.client import LiteLLMClient

logger = logging.getLogger(__name__)

#: Gleichzeitige Proxy-Aufrufe — wie bei der Budget-Änderung je Stufe (`/budget`).
PARALLEL = 10


@dataclass
class Ergebnis:
    gebucht: list[str] = field(default_factory=list)
    #: Proxy nicht erreichbar oder Konto dort unbekannt — **keine** Zeile geschrieben,
    #: ein zweiter Versuch ist gefahrlos.
    fehlgeschlagen: list[str] = field(default_factory=list)
    #: Konten ohne Grenze — bewusst nicht angefasst.
    unbegrenzt: list[str] = field(default_factory=list)


async def buche_auf(
    db: AsyncSession,
    *,
    pseudonyme: list[str],
    betrag_usd: float,
    grund: str,
    erstellt_von: str,
    schuljahr: str,
    quelle_gruppe_id: Optional[int] = None,
    client_fabrik: Callable[[], LiteLLMClient] = LiteLLMClient,
) -> Ergebnis:
    """Bucht jedem Pseudonym `betrag_usd` auf. Committet selbst."""
    if betrag_usd <= 0:
        raise ValueError("Ein Zuschlag muss größer als null sein.")
    if not grund.strip():
        raise ValueError("Ein Zuschlag braucht einen Grund — die Tabelle ist das Protokoll.")

    ergebnis = Ergebnis()
    sem = asyncio.Semaphore(PARALLEL)
    # Eindeutig und stabil: Ein Pseudonym zweimal in der Liste (Gruppe + Einzelperson)
    # bekäme sonst den doppelten Betrag.
    ziele = list(dict.fromkeys(pseudonyme))

    async def eins(pseudonym: str) -> tuple[str, str]:
        async with sem:
            client = client_fabrik()
            try:
                info = await client.get_user(pseudonym)
                if info is None:
                    return pseudonym, "fehlgeschlagen"
                grenze = info.get("max_budget")
                if grenze is None:
                    return pseudonym, "unbegrenzt"
                await client.update_user_budget(
                    pseudonym, max_budget=round(grenze + betrag_usd, 6)
                )
                return pseudonym, "gebucht"
            except Exception:
                logger.warning("Zuschlag am Proxy gescheitert pseudonym=%s",
                               pseudonym, exc_info=True)
                return pseudonym, "fehlgeschlagen"
            finally:
                await client.close()

    ausgaenge = await asyncio.gather(*(eins(p) for p in ziele))

    # Zeilen erst nach allen Proxy-Aufrufen und nacheinander — eine AsyncSession ist
    # nicht für gleichzeitige Nutzung aus mehreren Koroutinen gedacht.
    for pseudonym, ausgang in ausgaenge:
        getattr(ergebnis, ausgang).append(pseudonym)
        if ausgang == "gebucht":
            db.add(BudgetGrant(
                pseudonym=pseudonym,
                schuljahr=schuljahr,
                betrag_usd=betrag_usd,
                grund=grund.strip(),
                erstellt_von=erstellt_von,
                quelle_gruppe_id=quelle_gruppe_id,
            ))

    try:
        await db.commit()
    except Exception:
        logger.error(
            "Zuschlag: Grenze am Proxy angehoben, aber Protokoll NICHT geschrieben — "
            "die Aufstockung wird diese Konten einfrieren, bis der Verbrauch aufholt. "
            "Betroffen: %s",
            ", ".join(ergebnis.gebucht),
        )
        raise
    return ergebnis
