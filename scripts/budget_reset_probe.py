"""Misst, wie LiteLLM ein User-Budget **ohne** ``budget_duration`` behandelt.

Das Wochenmodell (``Budget-Wochenmodell-Plan.md``) setzt die Rücksetzung ab: ``max_budget``
soll die kumulierte Zuteilung sein, der Verbrauch das Schuljahr durchlaufen. Ob LiteLLM
das mitmacht, steht in keiner Dokumentation belastbar — und die Annahme trägt den ganzen
Plan. Also messen.

Vier Fragen:

  A. Setzt LiteLLM ein ``budget_reset_at``, wenn ``budget_duration`` fehlt?
     Ein gesetztes Datum hieße: Es wird zurückgesetzt, der Plan bräuchte einen anderen Weg.
  B. Bleibt ``spend`` erhalten, wenn nur ``max_budget`` erhöht wird?
     Das ist die Kernoperation des Wochenlaufs.
  C. Lässt sich eine bestehende ``budget_duration`` nachträglich entfernen?
     Entscheidet, ob die Umstellung bestehender Nutzer ohne Neuanlage geht.
  D. Greift die Grenze auch ohne Zeitraum?
     Sonst wäre ein Konto ohne ``budget_duration`` unbegrenzt — der gefährlichste Ausgang.

    python scripts/budget_reset_probe.py

Legt einen eigenen Testnutzer an und räumt ihn wieder ab.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import httpx

logger = logging.getLogger("budget_reset_probe")
REPO = Path(__file__).resolve().parent.parent


def _aus_env(name: str) -> str | None:
    pfad = REPO / ".env"
    if not pfad.exists():
        return None
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        k, _, v = zeile.partition("=")
        if k.strip() == name:
            return v.split("#")[0].strip().strip("'\"") or None
    return None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    basis = (_aus_env("LITELLM_PROXY_URL") or "http://localhost:4000").rstrip("/")
    master = _aus_env("LITELLM_MASTER_KEY")
    if not master:
        logger.error("LITELLM_MASTER_KEY fehlt in der .env.")
        return 1
    kopf = {"Authorization": f"Bearer {master}"}
    uid = f"probe-reset-{int(time.time())}"

    def info() -> dict:
        r = httpx.get(f"{basis}/user/info", headers=kopf, params={"user_id": uid}, timeout=30)
        d = r.json() if r.status_code == 200 else {}
        return d.get("user_info", d) or {}

    def zeige(titel: str) -> dict:
        i = info()
        logger.info(
            "   %-22s max_budget=%s  spend=%s  duration=%r  reset_at=%r",
            titel, i.get("max_budget"), i.get("spend"),
            i.get("budget_duration"), i.get("budget_reset_at"),
        )
        return i

    logger.info("Proxy: %s\nTestnutzer: %s\n", basis, uid)

    # ── A. Anlage OHNE budget_duration ──────────────────────────────────────────────
    r = httpx.post(f"{basis}/user/new", headers=kopf,
                   json={"user_id": uid, "max_budget": 0.10}, timeout=30)
    if r.status_code not in (200, 201):
        logger.error("Anlage fehlgeschlagen (%s): %s", r.status_code, r.text[:300])
        return 1
    logger.info("A. Angelegt mit max_budget=0.10, ohne budget_duration")
    a = zeige("nach Anlage")
    ohne_reset = not a.get("budget_reset_at") and not a.get("budget_duration")
    logger.info("   → %s\n", "kein Reset vorgesehen ✅" if ohne_reset
                else "⚠️ LiteLLM hat einen Zeitraum/Reset gesetzt")

    try:
        # ── B. max_budget erhöhen, spend muss stehen bleiben ────────────────────────
        vorher = a.get("spend")
        httpx.post(f"{basis}/user/update", headers=kopf,
                   json={"user_id": uid, "max_budget": 0.20}, timeout=30)
        b = zeige("nach Erhöhung")
        spend_stabil = b.get("spend") == vorher and b.get("max_budget") == 0.20
        logger.info("B. Erhöhung auf 0.20 → %s\n",
                    "spend unverändert ✅" if spend_stabil else "⚠️ spend hat sich geändert")

        # ── C. budget_duration setzen und wieder entfernen ──────────────────────────
        # Mehrere Schreibweisen, weil „null" in einer Prisma-Fassung auch schlicht
        # „Feld nicht anfassen" heißen kann.
        httpx.post(f"{basis}/user/update", headers=kopf,
                   json={"user_id": uid, "budget_duration": "1mo"}, timeout=30)
        zeige("mit duration=1mo")
        entfernbar = False
        for schreibweise in (None, "", "null"):
            httpx.post(f"{basis}/user/update", headers=kopf,
                       json={"user_id": uid, "budget_duration": schreibweise}, timeout=30)
            i = zeige(f"nach duration={schreibweise!r}")
            # ⚠️ `budget_duration` allein genügt als Kriterium NICHT: Der leere String
            # macht das Feld zwar falsy, LiteLLM setzt dann aber ein `budget_reset_at`
            # auf den Folgetag — der Verbrauch würde täglich genullt und das Budget wäre
            # praktisch unbegrenzt. Entfernt ist der Zeitraum nur, wenn BEIDES leer ist.
            if not i.get("budget_duration") and not i.get("budget_reset_at"):
                entfernbar = True
                logger.info("   → mit %r sauber entfernt", schreibweise)
                break
            if not i.get("budget_duration") and i.get("budget_reset_at"):
                logger.warning(
                    "   ⚠️ %r leert das Feld, hinterlässt aber reset_at=%r — "
                    "täglicher Reset, NICHT verwenden",
                    schreibweise, i.get("budget_reset_at"),
                )
        logger.info(
            "C. Zeitraum nachträglich entfernbar → %s\n",
            "ja ✅" if entfernbar
            else "⚠️ NEIN — Bestandsnutzer brauchen einen anderen Weg (Neuanlage/DB)",
        )

        # ── D. Greift die Grenze ohne Zeitraum überhaupt? ───────────────────────────
        # ⚠️ Eigener, FRISCHER Nutzer. Auf `uid` liegt nach C womöglich noch `1mo` —
        # dann würde hier die Rücksetzungs-Variante gemessen und fälschlich als Beleg
        # für den zeitraumlosen Fall gelesen.
        uid_d = f"{uid}-d"
        httpx.post(f"{basis}/user/new", headers=kopf,
                   json={"user_id": uid_d, "max_budget": 0.00002}, timeout=30)
        d_info = httpx.get(f"{basis}/user/info", headers=kopf,
                           params={"user_id": uid_d}, timeout=30).json()
        d_info = d_info.get("user_info", d_info) or {}
        logger.info("D. Frischer Nutzer ohne Zeitraum: duration=%r reset_at=%r",
                    d_info.get("budget_duration"), d_info.get("budget_reset_at"))
        if d_info.get("budget_duration"):
            logger.warning("   ⚠️ Zeitraum wurde gesetzt — Messung nicht aussagekräftig")
        kr = httpx.post(f"{basis}/key/generate", headers=kopf,
                        json={"user_id": uid_d, "models": ["chat-standard"]}, timeout=30)
        if kr.status_code != 200:
            logger.warning("D. Schlüssel nicht anlegbar (%s) — Frage offen", kr.status_code)
            return 0
        key = kr.json()["key"]
        anfrage = {"model": "chat-standard",
                   "messages": [{"role": "user", "content": "Sag genau: ok"}],
                   "max_tokens": 20}
        kopf_key = {"Authorization": f"Bearer {key}"}
        erst = httpx.post(f"{basis}/chat/completions", headers=kopf_key, json=anfrage, timeout=60)
        logger.info("   Erster Aufruf  → HTTP %s", erst.status_code)
        time.sleep(15)   # SpendLogs laufen verzögert
        nach = httpx.get(f"{basis}/user/info", headers=kopf,
                         params={"user_id": uid_d}, timeout=30).json()
        nach = nach.get("user_info", nach) or {}
        logger.info("   verbucht: spend=%s von max_budget=%s",
                    nach.get("spend"), nach.get("max_budget"))
        zweit = httpx.post(f"{basis}/chat/completions", headers=kopf_key, json=anfrage, timeout=60)
        logger.info("   Zweiter Aufruf → HTTP %s", zweit.status_code)
        greift = zweit.status_code != 200 and "budget" in zweit.text.lower()
        logger.info("   → %s", "Grenze greift auch ohne Zeitraum ✅" if greift
                    else "⚠️ Grenze greift NICHT — Konto wäre unbegrenzt!")
        if not greift:
            logger.info("   %s", zweit.text[:220])

        logger.info("\n" + "─" * 70)
        tragfaehig = ohne_reset and spend_stabil and greift
        logger.info("Wochenmodell auf diesem Weg tragfähig: %s",
                    "JA" if tragfaehig else "NEIN — Schritt 4 braucht einen anderen Weg")
        if not entfernbar:
            logger.info(
                "Offen bleibt die Umstellung des Bestands: `budget_duration` lässt sich\n"
                "über /user/update nicht löschen. Neuanlage oder direkter DB-Eingriff nötig."
            )
        return 0
    finally:
        httpx.post(f"{basis}/user/delete", headers=kopf,
                   json={"user_ids": [uid, f"{uid}-d"]}, timeout=30)
        logger.info("Testnutzer entfernt.")


if __name__ == "__main__":
    sys.exit(main())
