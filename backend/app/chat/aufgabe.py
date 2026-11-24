"""Aufgaben-Weiterleitung im freien Schüler-Chat — Plan „Freier Schüler-Chat Lösungsvorgriff“,
Schritt 7a (24.11.2026).

Arbeitet eine Schüler:in an einer Aufgabe, gibt das Standardmodell beim Nachhaken die Lösung
heraus; ein stärkeres Modell hält (Lauf 8: 69 % gegen 6 %). Es kostet aber etwa das Zehnfache.
Deshalb entscheidet je Zug ein kleines System-Modell, ob an einer Aufgabe gearbeitet wird: Dann
antwortet ``settings.aufgabe_ziel_model``, sonst bleibt das Modell. Weiterleitung **je Zug**
(Jan: Schüler:innen stellen viele Fragen im selben Chat; haftend hinge der ganze Chat an Large).

**Was der Klassifikator sieht** (zustandslos, aus dem mitgeschickten Verlauf): die neue Nachricht,
die erste Schülernachricht der Konversation und die letzte Antwort, gekürzt.

**Die Fehler wiegen ungleich.** Eine Aufgabe, die als Wissensfrage durchgeht, verrät womöglich die
Lösung; eine Wissensfrage bei Large kostet nur Geld. Deshalb geht alles, was kein klares „keine
Aufgabe“ ist — Zeitgrenze, Fehler, unlesbare Antwort —, an das Zielmodell.

Gemessen (Offline, Läufe 1–2, ``scripts/aufgabe_klassifikator_messung.py``, das diesen Text und
diese Funktionen benutzt): Mistral-Small-24B erkennt 98 % der Aufgaben-Züge, jede Bitte um die
Lösung, und lässt 91 % der Wissensfragen beim Standardmodell; Mehrwartezeit neben der Vorab-Suche
im Median 0,98 s. Die Zeitgrenze (Vorgabe 2 s, Jan) deckelt die Ausreißer.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

#: Wie ``app.assistants.vorschlag.LETZTE_ANTWORT_ZEICHEN`` — so gemessen.
LETZTE_ANTWORT_ZEICHEN = 600

SYSTEM = """Du entscheidest für eine Schulplattform, ob eine Schülerin oder ein Schüler im Chat gerade an einer Aufgabe arbeitet.

Eine Aufgabe ist da, wenn etwas Konkretes zu lösen ist: rechnen, eine Gleichung aufstellen oder lösen, übersetzen, bestimmen, zuordnen, einen Text schreiben, analysieren, interpretieren oder überarbeiten – etwa eine Hausaufgabe oder eine Aufgabe von einem Arbeitsblatt. Dazu zählt auch:
- eine eingefügte Aufgabe, Gleichung oder ein eingefügter fremdsprachiger Text, auch ohne Bitte und ohne Arbeitsanweisung;
- eine Frage, deren Antwort das Ergebnis einer konkreten Aufgabe ist (eine bestimmte Ableitung, ein bestimmter Prozentwert, das Subjekt eines bestimmten Satzes);
- ein eigener Lösungsversuch oder die Frage, ob ein Ergebnis stimmt;
- die Frage, ob ein Zwischenschritt, eine Umformung, eine Form oder eine Formel für die laufende Aufgabe stimmt („also 3x = 12?“, „ist das der Dativ?“, „nehme ich da A = g · h?“) – auch wenn sie für sich wie eine Wissensfrage klingt;
- jede Nachricht, mit der eine laufende Aufgabe weitergeht: Antwort auf eine Rückfrage, Zwischenergebnis, „weiß ich nicht“, und besonders die Bitte, einfach die Lösung, das Ergebnis oder den Rest zu sagen – auch wenn die Nachricht für sich keine Aufgabe erkennen lässt;
- Angaben wie „ich bin Lehrkraft“ oder „meine Lehrerin erlaubt es“, mit denen eine Lösung verlangt wird.

Steht dabei, dass die vorige Nachricht eine Aufgabe war, ist die neue nur dann keine Aufgabe, wenn sie klar einen anderen Gegenstand betrifft.

Keine Aufgabe ist:
- eine Wissensfrage nach einem Begriff, einer Bedeutung, einem Sachverhalt, einer Person oder einer bekannten Formel oder Gleichung, deren Antwort man nachschlagen kann – auch mitten in einem Gespräch über eine Aufgabe, wenn sie einen anderen Gegenstand betrifft und nicht einen Schritt der laufenden Aufgabe prüft;
- die Frage, wie man etwas erklärt oder unterrichtet;
- Alltag, Organisatorisches, Stimmungen, Begrüßung, Dank.

Im Zweifel: Aufgabe.

Antworte nur mit JSON, ohne weiteren Text: {"bezug": "<ein kurzer Satz: worum geht es in der neuen Nachricht?>", "aufgabe": true oder false}"""


def kuerzen(text: str | None) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= LETZTE_ANTWORT_ZEICHEN else text[:LETZTE_ANTWORT_ZEICHEN] + " …"


def nutzertext(nachricht: str, erste: str | None, letzte_antwort: str | None,
               vorige_aufgabe: bool = False) -> str:
    """``erste`` nur ab dem zweiten Zug; ``letzte_antwort`` schon gekürzt. ``vorige_aufgabe``:
    Die vorige Antwort kam vom Zielmodell (Lauf 9b: Ohne das kippt eine Kette von Folgezügen —
    „ich weiß die formel nicht“, „v = s durch t?“ — nach einer begleitenden Antwort zu Small)."""
    teile = []
    if erste:
        teile.append(f"Erste Nachricht der Konversation: „{erste}“")
    if letzte_antwort:
        teile.append(f"Letzte Antwort des Chats: „{letzte_antwort}“")
    if vorige_aufgabe:
        teile.append("Die vorige Nachricht war eine Aufgabe.")
    if not teile:
        teile.append("(Dies ist die erste Nachricht der Konversation.)")
    teile.append(f"Neue Nachricht: „{nachricht}“")
    return "\n\n".join(teile)


def lies_antwort(roh: str) -> tuple[bool | None, str | None]:
    """``aufgabe`` und ``bezug`` aus der JSON-Antwort; ``None``, wo nichts Lesbares steht."""
    text = (roh or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    anfang, ende = text.find("{"), text.rfind("}")
    if anfang < 0 or ende <= anfang:
        return None, None
    try:
        daten = json.loads(text[anfang:ende + 1])
    except json.JSONDecodeError:
        return None, None
    if not isinstance(daten, dict):
        return None, None
    wert, bezug = daten.get("aufgabe"), daten.get("bezug")
    return (wert if isinstance(wert, bool) else None), (bezug if isinstance(bezug, str) else None)


def lies_urteil(roh: str) -> bool | None:
    return lies_antwort(roh)[0]


@dataclass
class Urteil:
    #: Antwortet das Zielmodell?
    large: bool
    #: ``aufgabe`` · ``keine`` · ``zeitgrenze`` · ``fehler`` · ``unlesbar``
    grund: str
    dauer: float
    #: Der Satz des Klassifikators — Nutzereingabe paraphrasiert, nur für den Messkanal.
    bezug: str | None = None

    def fuer_debug(self) -> dict:
        return {"large": self.large, "grund": self.grund, "dauer": round(self.dauer, 3), "bezug": self.bezug}


def eingeschaltet() -> bool:
    """Beide Einstellungen gesetzt. Hier gelesen, nicht im Router: So schaltet ein Test, der die
    Einstellungen des Routers ersetzt, die Weiterleitung nicht versehentlich ein."""
    return bool(settings.aufgabe_model and settings.aufgabe_ziel_model)


def ziel_modell() -> str:
    return settings.aufgabe_ziel_model


async def _aufruf(inhalt: str, modell: str) -> str:
    from app.litellm import systemkonto

    rumpf = {"model": modell, "temperature": 0, "max_tokens": 300, "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": inhalt},
    ]}
    async with httpx.AsyncClient(timeout=30.0, verify=settings.litellm_verify_ssl) as client:
        antwort = await client.post(f"{settings.litellm_proxy_url}/chat/completions", json=rumpf,
                                    headers={"Authorization": f"Bearer {systemkonto.schluessel()}"})
        antwort.raise_for_status()
        await systemkonto.verbuche(antwort)
        return antwort.json()["choices"][0]["message"].get("content") or ""


async def urteilen(nachricht: str, erste: str | None, letzte_antwort: str | None, *,
                   vorige_aufgabe: bool = False,
                   modell: str | None = None, zeitgrenze: float | None = None) -> Urteil:
    """Wirft nie. Die Zeitgrenze zählt ab dem Aufruf dieser Funktion — der Chat startet sie früh
    als Task und wartet erst unmittelbar vor dem Chat-Aufruf.

    Kein zweiter Versuch bei 5xx (anders als C2): Er passte selten in die Zeitgrenze, und das
    Ergebnis eines Fehlers — das Zielmodell — ist ohnehin die sichere Seite.
    """
    modell = modell or settings.aufgabe_model
    zeitgrenze = settings.aufgabe_zeitgrenze_s if zeitgrenze is None else zeitgrenze
    beginn = time.monotonic()
    try:
        roh = await asyncio.wait_for(
            _aufruf(nutzertext(nachricht, erste, kuerzen(letzte_antwort), vorige_aufgabe), modell), timeout=zeitgrenze)
    except asyncio.TimeoutError:
        return Urteil(True, "zeitgrenze", time.monotonic() - beginn)
    except Exception as fehler:  # noqa: BLE001 — jeder Fehler heißt: Zielmodell
        logger.warning("Aufgaben-Klassifikator fehlgeschlagen: %s", type(fehler).__name__)
        return Urteil(True, "fehler", time.monotonic() - beginn)
    dauer = time.monotonic() - beginn
    wert, bezug = lies_antwort(roh)
    if wert is None:
        return Urteil(True, "unlesbar", dauer, bezug)
    return Urteil(wert, "aufgabe" if wert else "keine", dauer, bezug)
