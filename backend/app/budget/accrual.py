"""Wöchentliche Aufstockung der Budget-Obergrenze.

Das Budget wird **nicht zurückgesetzt**. ``max_budget`` am LiteLLM-User ist die kumulierte
Zuteilung, der Verbrauch läuft das Schuljahr durch; dieser Lauf hebt die Obergrenze je
Unterrichtswoche um den konfigurierten Wochenbetrag an. Ungenutztes wandert dadurch von
selbst in die nächsten Wochen — es muss nichts „übertragen" werden.

Damit daraus kein Ansparkonto wird, eilt die Obergrenze dem Verbrauch höchstens
``vorsprung_wochen`` Wochenbeträge voraus. Das ist die Tempobegrenzung, die im
Monatsmodell die Rücksetzung übernommen hat: Ein übernommenes Konto oder eine Klasse, die
den Bildgenerator entdeckt, richtet höchstens diesen Schaden an — ein Bild kostet rund
vierzig Chat-Nachrichten.

    neue_grenze = min( bisherige_grenze + fehlende_wochen × wochenbetrag,
                       verbrauch        + vorsprung_wochen × wochenbetrag )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.budget.schulwochen import Unterrichtswoche, woche_am, wochen_bis
from app.budget.tiers import vorsprung_wochen
from app.db.models import BudgetAccrual
from app.planning.calendar import SchoolYearConfig, load_school_year

logger = logging.getLogger(__name__)


@dataclass
class Zuteilung:
    """Was für eine Nutzerin zu tun ist — oder warum nichts."""

    neue_grenze_usd: Optional[float]
    gebuchte_wochen: int
    bis_woche: Optional[int]
    grund: str = ""
    #: Erste Zuteilung eines neuen Schuljahres. Dann wird der Verbrauch **mit**
    #: zurückgesetzt — sonst zählte der des Vorjahres gegen das neue Budget, und die
    #: angezeigte Obergrenze wüchse über die Jahre ins Sinnlose.
    jahreswechsel: bool = False

    @property
    def zu_tun(self) -> bool:
        return self.neue_grenze_usd is not None


def berechne(
    *,
    wochenbetrag_usd: float,
    aktuelle_grenze_usd: Optional[float],
    verbrauch_usd: float,
    fehlende_wochen: int,
    vorsprung: int,
) -> float:
    """Die neue Obergrenze. Reine Rechnung, ohne Datenbank und ohne Proxy.

    ``fehlende_wochen`` kann > 1 sein, wenn ein Lauf ausgefallen ist. Das Nachholen ist
    **automatisch begrenzt**: Der zweite Term deckelt unabhängig davon, wie viele Wochen
    nachzuholen sind. Wer sechs Wochen nichts genutzt hat, bekommt danach trotzdem nur den
    Vorsprung — sonst wäre der ausgefallene Cron ein Freibrief.
    """
    gewachsen = (aktuelle_grenze_usd or 0.0) + fehlende_wochen * wochenbetrag_usd
    gedeckelt = verbrauch_usd + vorsprung * wochenbetrag_usd
    # Nie unter die bestehende Grenze: Eine Kürzung wäre für die Nutzerin ein plötzlich
    # verschwundenes Guthaben, und der Deckel soll bremsen, nicht wegnehmen.
    return round(max(min(gewachsen, gedeckelt), aktuelle_grenze_usd or 0.0), 4)


async def plane(
    db: AsyncSession,
    pseudonym: str,
    *,
    wochenbetrag_usd: Optional[float],
    aktuelle_grenze_usd: Optional[float],
    verbrauch_usd: float,
    stichtag: date,
    cfg: Optional[SchoolYearConfig] = None,
    neuaufbau: bool = False,
) -> Zuteilung:
    """Ermittelt die Zuteilung für **eine** Nutzerin, ohne sie zu schreiben.

    ``neuaufbau=True`` ist der einmalige Sonderfall nach der Umstellung vom Monatsmodell:
    Die bestehende Grenze wird **ignoriert** statt geschützt, weil sie einen Monatsbetrag
    trägt und die Schutzregel sie sonst monatelang stehen ließe. Nur so, nie im Regellauf —
    sonst wäre die Zusicherung „es wird nie gekürzt" wertlos.
    """
    if not wochenbetrag_usd:
        return Zuteilung(None, 0, None, "kein Wochenbetrag konfiguriert")

    c = cfg or load_school_year()
    woche: Optional[Unterrichtswoche] = woche_am(stichtag, c)
    if woche is None:
        # Ferien oder außerhalb des Schuljahres — es gibt nichts zuzuteilen.
        return Zuteilung(None, 0, None, "keine Unterrichtswoche")

    if neuaufbau:
        # Die alte Grenze wird verworfen — aber **auf dem Verbrauch aufgesetzt**, nicht
        # bei null. Sonst läge die neue Grenze unter dem bereits Verbrauchten und die
        # Nutzerin wäre ab sofort gesperrt; bei einem Wochenbetrag von wenigen Cent für
        # den Rest des Schuljahres. Wer den Verbrauch mit zurücksetzt (Schuljahresbeginn),
        # landet ohnehin bei genau einem Wochenbetrag.
        return Zuteilung(
            berechne(
                wochenbetrag_usd=wochenbetrag_usd,
                aktuelle_grenze_usd=verbrauch_usd,
                verbrauch_usd=verbrauch_usd,
                fehlende_wochen=1,
                vorsprung=vorsprung_wochen(),
            ),
            1,
            woche.index,
        )

    stand = await db.get(BudgetAccrual, pseudonym)
    jahreswechsel = stand is not None and stand.schuljahr != c.schuljahr

    if jahreswechsel:
        # **Der einzige Reset, den es gibt.** Verbrauch und Obergrenze des Vorjahres
        # gehen NICHT ein: Sonst zählte der alte Verbrauch gegen das neue Budget, die
        # Schutzregel „nie kürzen" hielte die alte Grenze das ganze Jahr über fest, und
        # nicht Verbrauchtes wanderte ins nächste Schuljahr — entgegen der Zusage, die
        # in der Admin-Oberfläche steht.
        #
        # Der Verbrauch wird beim Schreiben genullt (`Zuteilung.jahreswechsel`), deshalb
        # steht die neue Grenze bei genau einem Wochenbetrag.
        return Zuteilung(
            round(wochenbetrag_usd, 4), 1, woche.index, jahreswechsel=True
        )

    if stand is None:
        # Erstzuteilung. Bewusst **kein** rückwirkendes Nachholen ab Woche 1: Wer im März
        # dazukommt, hat nicht seit September Anspruch. Für den Ausfall eines Laufs
        # braucht es das nicht — dafür gibt es den Vergleich mit `letzte_woche`.
        #
        # Und bewusst **ohne** Verbrauchs-Reset: Wer hier landet, kann aus der Umstellung
        # vom Monatsmodell kommen und einen echten Verbrauch tragen.
        fehlende = 1
    else:
        offen = [w for w in wochen_bis(stichtag, c) if w.index > stand.letzte_woche]
        if not offen:
            return Zuteilung(None, 0, stand.letzte_woche, "diese Woche bereits gebucht")
        fehlende = len(offen)

    neue = berechne(
        wochenbetrag_usd=wochenbetrag_usd,
        aktuelle_grenze_usd=aktuelle_grenze_usd,
        verbrauch_usd=verbrauch_usd,
        fehlende_wochen=fehlende,
        vorsprung=vorsprung_wochen(),
    )
    return Zuteilung(neue, fehlende, woche.index)


async def merke(
    db: AsyncSession, pseudonym: str, *, bis_woche: int, schuljahr: str
) -> None:
    """Schreibt den Merkposten fort. Erst aufrufen, wenn der Proxy bestätigt hat."""
    stand = await db.get(BudgetAccrual, pseudonym)
    if stand is None:
        db.add(
            BudgetAccrual(
                pseudonym=pseudonym, schuljahr=schuljahr, letzte_woche=bis_woche
            )
        )
    else:
        stand.schuljahr = schuljahr
        stand.letzte_woche = bis_woche


async def zurueckgestellte(db: AsyncSession, schuljahr: str) -> list[str]:
    """Pseudonyme, deren Merkposten noch aus einem früheren Schuljahr stammt."""
    result = await db.execute(
        select(BudgetAccrual.pseudonym).where(BudgetAccrual.schuljahr != schuljahr)
    )
    return [row[0] for row in result.fetchall()]
