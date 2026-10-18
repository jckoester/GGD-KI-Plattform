"""Ein einzelner Modellaufruf außerhalb des Chats — im Namen einer Person (0.18).

Für Aufgaben, die neben dem Gespräch laufen: die Begriffe einer Stunde aus ihren
Phasentexten bestimmen (Plan „Begriffe aus den Phasentexten"), später der Nachlauf des
Planungsprofils. Muster ist die Titelgenerierung (`chat/router.py`, `_generate_title`):

* **Über den virtuellen Schlüssel der Person**, nicht den Master-Schlüssel. Der Aufruf
  geht aufs Budget der Person und steht in ihrer Abrechnung; ist das Budget erschöpft,
  lehnt der Proxy ab. Das Modell muss deshalb in der Allowlist ihres Teams stehen.
* **Nicht streamend, mit eigenem Zeitlimit.** Niemand wartet Token für Token.
* **Kein Fehler nach außen.** Das Ergebnis sagt, was schiefging (`fehler`); der Aufrufer
  entscheidet, ob er einen Hinweis zeigt oder schweigt.

⚠️ **Ob das Budget erschöpft ist, steht im Antwortkörper, nicht im Status**
(`app/litellm/errors.py`): LiteLLM 1.83.7 antwortet mit 400. Deshalb wird ein 400 erst
darauf geprüft, bevor er als „JSON-Modus unbekannt" gilt — sonst liefe bei leerem Budget
ein zweiter, ebenso abgelehnter Aufruf.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import httpx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import PseudonymAudit
from app.litellm.errors import ist_budget_erschoepft

logger = logging.getLogger(__name__)

Fehler = Literal["kein_modell", "kein_schluessel", "budget", "zeit", "abgelehnt"]


@dataclass
class Antwort:
    inhalt: str = ""
    kosten_usd: float = 0.0
    fehler: Fehler | None = None
    #: `False`, wenn der Proxy `response_format` ablehnte und ohne wiederholt wurde.
    json_modus: bool = True
    #: `finish_reason` — „length" heißt: `max_tokens` reichte nicht.
    ende: str | None = None

    @property
    def ok(self) -> bool:
        return self.fehler is None


async def schluessel_fuer(db: AsyncSession, pseudonym: str) -> str | None:
    """Der virtuelle LiteLLM-Schlüssel einer Person, oder `None`, wenn sie keinen hat."""
    return (await db.execute(
        sa.select(PseudonymAudit.litellm_key).where(PseudonymAudit.pseudonym == pseudonym)
    )).scalar_one_or_none()


async def einzelaufruf(
    schluessel: str | None,
    pseudonym: str,
    modell: str,
    nachrichten: list[dict],
    *,
    json_antwort: bool = False,
    max_tokens: int = 2000,
    temperatur: float = 0.0,
    zeitlimit: float = 30.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Antwort:
    """Ein Aufruf von `/chat/completions`. `transport` nur für Tests."""
    if not modell:
        return Antwort(fehler="kein_modell")
    if not schluessel:
        logger.info("Einzelaufruf übersprungen: kein virtueller Schlüssel für %s", pseudonym)
        return Antwort(fehler="kein_schluessel")

    rumpf: dict = {
        "model": modell,
        "messages": nachrichten,
        "stream": False,
        "temperature": temperatur,
        "max_tokens": max_tokens,
        "user": pseudonym,
    }
    if json_antwort:
        rumpf["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(
        base_url=settings.litellm_proxy_url,
        timeout=zeitlimit,
        verify=settings.litellm_verify_ssl,
        headers={"Authorization": f"Bearer {schluessel}"},
        transport=transport,
    ) as client:
        try:
            r = await client.post("/chat/completions", json=rumpf)
            if r.status_code != 200 and ist_budget_erschoepft(r.text):
                return Antwort(fehler="budget")
            json_modus = "response_format" in rumpf
            if r.status_code == 400 and json_modus:
                # Nicht jedes Modell hinter dem Proxy kennt den JSON-Modus.
                rumpf.pop("response_format")
                json_modus = False
                r = await client.post("/chat/completions", json=rumpf)
                if r.status_code != 200 and ist_budget_erschoepft(r.text):
                    return Antwort(fehler="budget")
            if r.status_code != 200:
                logger.warning("Einzelaufruf (%s) abgelehnt: HTTP %s %s", modell, r.status_code, r.text[:300])
                return Antwort(fehler="abgelehnt", json_modus=json_modus)
        except httpx.TimeoutException:
            logger.warning("Einzelaufruf (%s): Zeitlimit %.0f s überschritten", modell, zeitlimit)
            return Antwort(fehler="zeit")
        except httpx.HTTPError as exc:
            logger.warning("Einzelaufruf (%s) fehlgeschlagen: %s", modell, exc)
            return Antwort(fehler="abgelehnt")

    try:
        daten = r.json()
        wahl = (daten.get("choices") or [{}])[0]
    except (ValueError, AttributeError):
        logger.warning("Einzelaufruf (%s): Antwort ist kein lesbares JSON: %s", modell, r.text[:300])
        return Antwort(fehler="abgelehnt", json_modus=json_modus)
    try:
        kosten = float(r.headers.get("x-litellm-response-cost") or 0.0)
    except ValueError:
        kosten = 0.0
    return Antwort(
        inhalt=(wahl.get("message") or {}).get("content") or "",
        kosten_usd=kosten,
        json_modus=json_modus,
        ende=wahl.get("finish_reason"),
    )
