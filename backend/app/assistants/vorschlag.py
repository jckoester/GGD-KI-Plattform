"""Assistenten-Vorschlag im Chat — Päckchen C2 (0.24), Plan „Assistenten-Vorschlag-C2-Plan".

Tippt eine Schüler:in eine Aufgabe in den Chat, für die es einen passenden Assistenten gibt,
bietet die Plattform den Wechsel an — als Rückfrage neben der Antwort, keine Automatik. Dieses
Modul entscheidet, **welche** Optionen der Dialog zeigt; den Dialog, den Wechsel und die
Ruheregel verdrahtet der Chat-Flow.

**Zwei Stufen** (C1-Messung, [[Messungen-Vorschlag/vorschlag-1]]: Embeddings allein trennen
Rückfall-Assistenten nicht von Alltag und Mathe):

1. **Vorfilter:** Je Kandidat das beste Auslöser-Beispiel (Kosinus-Distanz zum Vektor der
   Nachricht, den die Vorab-Suche ohnehin berechnet). Kandidat ist nur, wer näher als
   :data:`BAND` liegt.
2. **Klassifikator** im Band: ein kurzer Aufruf an ``settings.vorschlag_model`` über das
   Systemkonto (F1) — Nachricht und je Kandidat Name, Art, `suggestion_text` und die drei
   nächsten Beispiele; Antwort JSON. Gemessen (28.10.2026, Gate): Mistral-Small-24B trifft
   K1–K4; Denkmodelle brauchen zu lange.

**In einer Assistenten-Konversation** dieselben zwei Stufen (Jan, 29.10.2026, nach k5-1): Liegt
ein anderer Assistent näher als :data:`IM_ASSISTENTEN`, entscheidet ein Klassifikator mit der
letzten Nachricht des Assistenten als Kontext, ob die Nachricht zum laufenden Gespräch gehört
oder eine neue Aufgabe für einen anderen ist (:data:`SYSTEM_IM_ASSISTENTEN`). Ohne Kandidat
kein Aufruf; Standard ist bleiben, ein „beenden“ bietet der Vorschlag nicht an.

**Ruheregel** (F4): Wer in ``schon_vorgeschlagen`` steht, kommt nicht wieder; 0 steht für
„Assistent beenden“. Der Chat-Flow leert die Menge bei einem angenommenen Wechsel.

⚠️ **Die Ruheregel filtert das Ergebnis, nicht die Kandidaten** (Probe 28.10.2026): Nahm man den
schon angebotenen Stöchiometrie-Assistenten aus der Liste, blieb dem Klassifikator bei der
nächsten Stöchiometrie-Aufgabe nur „Reaktionsgleichungen“ — und er wählte es. Wer die Aufgabe
am besten trifft, muss er sehen; zeigen darf ihn der Dialog dann nicht mehr.

⚠️ **Schlägt etwas fehl, gibt es keinen Vorschlag** — die Antwort läuft davon unberührt.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistants.sichtbarkeit import Zugang, sichtbar_klausel
from app.config import settings
from app.db.models import Assistant, AssistantTriggerExample

logger = logging.getLogger(__name__)

#: Vorfilter: Kandidat ist, wessen bestes Beispiel näher liegt (C1: Positive 0,29–0,49).
BAND = 0.50
#: Vorfilter in der Assistenten-Konversation: Der Klassifikator wird nur gefragt, wenn ein anderer
#: Assistent — spezifisch oder Rückfall — mit seinem besten Beispiel näher liegt. Bewusst locker:
#: Es entscheidet das Modell, nicht die Schwelle. Embeddings allein trennten einen echten Wechsel
#: zwischen Rückfällen nicht von einer Folgefrage (k5-1). Das Mittel der drei nächsten Beispiele
#: (< 0,50) brachte live nichts (k5-5: ein Wechsel mehr, zwei falsche mehr) — es wird nur gemessen.
IM_ASSISTENTEN = 0.45
#: ⚠️ Bekannte Grenze von SYSTEM_IM_ASSISTENTEN (k5-4, eingefroren 29.10.2026): Eine Bitte, die nur
#: ein Fach nennt („Kannst du mir bei der Englisch-Hausaufgabe helfen?“, „kannst du mir auch was zu
#: geschichte erklären?“), löst einen Wechsel aus. Eine eigene Zeile dafür fing keinen der beiden
#: und kostete zwei richtige Wechsel (k5-6).
#: Wie viel der letzten Assistenten-Nachricht der Klassifikator sieht — das Ende, dort steht die Frage.
LETZTE_ANTWORT_ZEICHEN = 600
#: Kennung von „Assistent beenden“ in der Ruheregel. Seit K5-neu bietet der Vorschlag „beenden“
#: nicht mehr an; die Kennung bleibt für bestehende Ruheregeln und `assistent_beenden`.
BEENDEN_KENNUNG = 0
#: Wie viele Beispiele je Kandidat in den Prompt gehen.
BEISPIELE_IM_PROMPT = 3

SYSTEM = """Du ordnest die Nachricht einer Schülerin oder eines Schülers Assistenten einer Schulplattform zu.
Ein Assistent passt, wenn die Nachricht eine **Aufgabe oder ein konkretes Anliegen aus seiner Tätigkeit** ist,
bei der er begleiten kann: etwas rechnen, einen Versuch auswerten, einen Text analysieren, überarbeiten oder
planen, argumentieren, ein Referat vorbereiten, programmieren, für eine Arbeit lernen. Entscheidend ist die Art
der Tätigkeit, nicht das Fach oder das Thema — und nicht schon, dass ein Fachwort darin vorkommt.

Keinen Assistenten wählst du bei:
- einer Frage nach einem Begriff, einer Erklärung oder einem Sachverhalt („Was ist ein Mol?“, „Welche
  Programmiersprache nehmen wir in Informatik?“) — die beantwortet der normale Chat,
- Alltag, Organisatorischem, Small Talk, Stimmungen („keine Lust auf Hausaufgaben“),
- der Bitte, etwas fertig zu erledigen, statt Hilfe dabei zu wollen („Fass mir das Buch zusammen“, „Übersetz mir
  das“, „Schreib mir eine Entschuldigung“) — die Assistenten begleiten, sie erledigen nicht.

Spezifische Assistenten haben eine eng umrissene Aufgabe; wähle sie nur, wenn genau diese Aufgabe gestellt ist.
Rückfall-Assistenten decken je eine Tätigkeit ab; wähle den, dessen Tätigkeit die Nachricht verlangt, auch wenn
kein spezifischer passt. Nenne höchstens einen Rückfall-Assistenten — den, der am besten passt.

Antworte nur mit JSON, ohne Erklärung: {"spezifisch": [Kennungen], "rueckfall": [Kennungen]} — leere Listen,
wenn keiner passt."""

SYSTEM_IM_ASSISTENTEN = """Eine Schülerin oder ein Schüler arbeitet auf einer Schulplattform mit einem Assistenten und schreibt
eine neue Nachricht. Du entscheidest, ob sie zum laufenden Gespräch gehört oder eine neue Aufgabe ist, für die
einer der genannten anderen Assistenten da ist.

Zum laufenden Gespräch gehört:
- alles, was sich auf die laufende Aufgabe bezieht: eine Antwort auf die Frage des Assistenten, eine Rückfrage,
  ein Zwischenergebnis, eine Begriffsfrage, der nächste Schritt — auch eine Nebenfrage dazu (wie man etwas
  darstellt, rechnet, schreibt oder angibt), selbst wenn darin ein Wort vorkommt, das zur Tätigkeit eines anderen
  Assistenten passt. Der andere Assistent hätte die laufende Aufgabe nicht vor sich;
- eine Bitte um Hilfe in einem anderen Fach, ohne dass schon eine konkrete Aufgabe genannt ist — welche gemeint
  ist, klärt der aktuelle Assistent;
- die Bitte, etwas fertig zu erledigen statt Hilfe dabei („Schreib mir …“, „Mach mir …“) — die Assistenten
  begleiten, sie erledigen nicht;
- Alltag, Stimmungen, Unverständliches und eine weitere Aufgabe derselben Tätigkeit.

Eine neue Aufgabe ist es nur, wenn die Nachricht eine konkrete Aufgabe nennt, die mit der laufenden nichts zu tun
hat — oft angekündigt („neues Thema“, „kurz was anderes“, „ich hab noch …“) —, und diese Aufgabe die Tätigkeit
eines der anderen Assistenten verlangt.

Im Zweifel: laufendes Gespräch.

Antworte nur mit JSON, ohne weiteren Text: {"bezug": "<ein kurzer Satz: worauf bezieht sich die Nachricht?>",
"neue_aufgabe": Kennung oder null}."""


@dataclass(frozen=True)
class Kandidat:
    id: int
    name: str
    art: str                         # specific | fallback
    text: str                        # suggestion_text, sonst Beschreibung
    subject_id: int | None
    fallbacks: tuple[int, ...]
    abstand: float                   # bestes Auslöser-Beispiel
    gegen: float                     # bestes Gegenbeispiel (inf ohne)
    mittel: float = float("inf")     # Mittel der drei nächsten Beispiele — nur gemessen (k5-5)
    beispiele: tuple[str, ...] = ()


@dataclass(frozen=True)
class Option:
    assistant_id: int                # BEENDEN_KENNUNG für „Assistent beenden“
    name: str
    text: str
    art: str                         # specific | fallback | beenden


@dataclass
class Vorschlag:
    optionen: list[Option]
    #: Für den Messkanal (`vorab_debug.vorschlag`) — nie ins Log, die Nachricht ist Nutzereingabe.
    debug: dict = field(default_factory=dict)


# ── Reine Funktionen ─────────────────────────────────────────────────────────


def prompt_kandidaten(kandidaten: list[Kandidat]) -> str:
    zeilen = []
    for k in kandidaten:
        zeilen.append(f"- Kennung {k.id} · {'spezifisch' if k.art == 'specific' else 'Rückfall'} · "
                      f"„Assistent für {k.name}“: {k.text}")
        zeilen += [f"    Beispiel: {b}" for b in k.beispiele]
    return "\n".join(zeilen)


def lies_antwort(roh: str, erlaubt: dict[int, str]) -> tuple[list[int], list[int]]:
    """JSON aus der Modellantwort — auch im Codeblock oder mit Text drumherum. Nur erlaubte
    Kennungen der passenden Art, ohne Dubletten. Unlesbares heißt „keiner“."""
    m = re.search(r"\{.*\}", roh or "", re.S)
    try:
        daten = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        daten = {}
    if not isinstance(daten, dict):
        return [], []

    def ids(feld, art):
        aus = []
        for x in daten.get(feld) or []:
            try:
                i = int(x)
            except (TypeError, ValueError):
                continue
            if erlaubt.get(i) == art and i not in aus:
                aus.append(i)
        return aus
    return ids("spezifisch", "specific"), ids("rueckfall", "fallback")


def zusammenstellen(
    spez: list[int], rueck: list[int], kandidaten: dict[int, Kandidat], konversationsfach: int | None = None
) -> list[Option]:
    """F7: höchstens zwei spezifische — ein passendes Konversationsfach zuerst, dann der nähere —,
    darunter die Rückfälle: die `fallbacks` der gewählten spezifischen (höchstens zwei), sonst
    **der erste** des Klassifikators. Nur Kandidaten (sichtbar, nicht schon vorgeschlagen).

    Ein Rückfall statt zwei (0.26, Messung r3, V1): Wo der zweitgenannte falsch war, war der
    erstgenannte fast immer richtig — zwölf Rückfälle sind Nachbarn, zwei davon anzubieten hieß
    meist, den falschen mitzubieten."""
    def schluessel(i):
        k = kandidaten[i]
        return (konversationsfach is None or k.subject_id != konversationsfach, k.abstand)
    gewaehlt = sorted((i for i in spez if i in kandidaten), key=schluessel)[:2]
    unter = [f for s in gewaehlt for f in kandidaten[s].fallbacks
             if f in kandidaten and kandidaten[f].art == "fallback"]
    rueckfaelle = (list(dict.fromkeys(unter))[:2] if unter
                   else [i for i in rueck if i in kandidaten][:1])
    return [Option(i, kandidaten[i].name, kandidaten[i].text, kandidaten[i].art)
            for i in gewaehlt + rueckfaelle]


def im_assistenten_band(kandidaten: dict[int, Kandidat]) -> list[Kandidat]:
    """Wer in der Assistenten-Konversation dem Klassifikator vorgelegt wird: jeder andere
    Assistent, dessen bestes Beispiel näher liegt als :data:`IM_ASSISTENTEN`, der nächste zuerst.
    Leer heißt bleiben, ohne Aufruf — so fallen die ankerlosen Folgefragen („hä?“, „stimmt das
    so?“) weiter still durch."""
    return sorted((k for k in kandidaten.values() if k.abstand < IM_ASSISTENTEN), key=lambda k: k.abstand)


def lies_wechsel(roh: str, erlaubt: set[int]) -> int | None:
    """Die Kennung der neuen Aufgabe — oder ``None`` für das laufende Gespräch. Unlesbares und
    fremde Kennungen heißen bleiben."""
    m = re.search(r"\{.*\}", roh or "", re.S)
    try:
        daten = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return None
    if not isinstance(daten, dict):
        return None
    try:
        i = int(daten.get("neue_aufgabe"))
    except (TypeError, ValueError):
        return None
    return i if i in erlaubt else None


def prompt_im_assistenten(nachricht: str, aktuell: tuple[str, str], letzte_antwort: str | None,
                          band: list[Kandidat]) -> str:
    letzte = (letzte_antwort or "").strip()
    if len(letzte) > LETZTE_ANTWORT_ZEICHEN:
        letzte = "…" + letzte[-LETZTE_ANTWORT_ZEICHEN:]
    return (f"Aktueller Assistent: „Assistent für {aktuell[0]}“: {aktuell[1]}\n\n"
            f"Letzte Nachricht des Assistenten: „{letzte or '(keine)'}“\n\n"
            f"Neue Nachricht: „{nachricht}“\n\n"
            f"Andere Assistenten:\n{prompt_kandidaten(band)}")


# ── Datenbank und Modell ─────────────────────────────────────────────────────


async def _kandidaten(
    db: AsyncSession, zugang: Zugang, vektor, aktuell_id: int | None
) -> tuple[dict[int, Kandidat], float | None]:
    """Sichtbare Assistenten mit Vorschlag und Beispielen, je mit bestem Beispiel und
    Gegenbeispiel. Dazu der Abstand des aktuellen Assistenten (oder ``None``)."""
    sichtbar = (await db.execute(
        # „Versteckt“ heißt: nur über Link und Einstiege (0.22) — nie im Vorschlag.
        sa.select(Assistant).where(sichtbar_klausel(zugang), Assistant.suggest != "never",
                                   Assistant.visibility != "hidden")
    )).scalars().all()
    ids = [a.id for a in sichtbar if a.id != aktuell_id]
    abfrage_ids = ids + ([aktuell_id] if aktuell_id is not None else [])
    if not abfrage_ids:
        return {}, None
    distanz = AssistantTriggerExample.embedding.cosine_distance(vektor)
    je = (
        sa.select(AssistantTriggerExample.assistant_id, AssistantTriggerExample.art, distanz.label("d"),
                  sa.func.row_number().over(
                      partition_by=(AssistantTriggerExample.assistant_id, AssistantTriggerExample.art),
                      order_by=distanz).label("rang"))
        .where(AssistantTriggerExample.assistant_id.in_(abfrage_ids),
               AssistantTriggerExample.embedding_model == settings.embedding_model,
               AssistantTriggerExample.embedding.is_not(None))
    ).subquery()
    zeilen = (await db.execute(
        sa.select(je.c.assistant_id, je.c.art, sa.func.min(je.c.d), sa.func.avg(je.c.d))
        .where(je.c.rang <= BEISPIELE_IM_PROMPT)
        .group_by(je.c.assistant_id, je.c.art)
    )).all()
    beste: dict[tuple[int, str], float] = {(a, art): float(d) for a, art, d, _ in zeilen}
    mittel: dict[int, float] = {a: float(m) for a, art, _, m in zeilen if art == "beispiel"}
    nach_id = {a.id: a for a in sichtbar}
    kandidaten = {
        i: Kandidat(
            id=i, name=nach_id[i].name, art=nach_id[i].suggest,
            text=(nach_id[i].suggestion_text or nach_id[i].description or "").strip(),
            subject_id=nach_id[i].subject_id, fallbacks=tuple(nach_id[i].fallbacks or ()),
            abstand=beste[(i, "beispiel")], gegen=beste.get((i, "gegenbeispiel"), float("inf")),
            mittel=mittel[i],
        )
        for i in ids if (i, "beispiel") in beste
    }
    aktuell = beste.get((aktuell_id, "beispiel")) if aktuell_id is not None else None
    return kandidaten, aktuell


async def _mit_beispielen(db: AsyncSession, vektor, band: list[Kandidat]) -> list[Kandidat]:
    """Die :data:`BEISPIELE_IM_PROMPT` nächsten Beispiele je Kandidat im Band."""
    distanz = AssistantTriggerExample.embedding.cosine_distance(vektor)
    zeilen = (await db.execute(
        sa.select(AssistantTriggerExample.assistant_id, AssistantTriggerExample.text_)
        .where(AssistantTriggerExample.assistant_id.in_([k.id for k in band]),
               AssistantTriggerExample.art == "beispiel",
               AssistantTriggerExample.embedding_model == settings.embedding_model,
               AssistantTriggerExample.embedding.is_not(None))
        .order_by(AssistantTriggerExample.assistant_id, distanz)
    )).all()
    texte: dict[int, list[str]] = {}
    for aid, txt in zeilen:
        if len(texte.setdefault(aid, [])) < BEISPIELE_IM_PROMPT:
            texte[aid].append(txt)
    return [Kandidat(**{**k.__dict__, "beispiele": tuple(texte.get(k.id, []))}) for k in band]


async def klassifiziere(nachricht: str, band: list[Kandidat], *, modell: str, client, marke=None) -> dict:
    """Ein Aufruf über das Systemkonto. Wirft bei Netz- oder HTTP-Fehlern."""
    return await _aufruf(SYSTEM, f"Nachricht: „{nachricht}“\n\nAssistenten:\n{prompt_kandidaten(band)}",
                         modell=modell, client=client, marke=marke)


async def _aufruf(system: str, inhalt: str, *, modell: str, client, marke=None) -> dict:
    from app.litellm import systemkonto

    rumpf = {"model": modell, "temperature": 0, "max_tokens": 400, "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": inhalt},
    ]}
    beginn = time.monotonic()
    # Ein zweiter Versuch bei 5xx: In der Live-Probe (28.10.2026) antwortete der Anbieter einmal
    # mit 500. Das Zeitlimit des Aufrufers gilt für beide Versuche zusammen.
    for versuch in (1, 2):
        antwort = await client.post(f"{settings.litellm_proxy_url}/chat/completions", json=rumpf,
                                    headers={"Authorization": f"Bearer {systemkonto.schluessel()}"})
        if marke:
            marke(f"http_{versuch}_{antwort.status_code}")
        if antwort.status_code < 500:
            break
    antwort.raise_for_status()
    await systemkonto.verbuche(antwort)
    if marke:
        marke("verbucht")
    return {"roh": antwort.json()["choices"][0]["message"].get("content") or "",
            "dauer": time.monotonic() - beginn}


async def vorschlagen(
    db: AsyncSession,
    *,
    nachricht: str,
    vektor,
    zugang: Zugang,
    aktuell_id: int | None,
    schon_vorgeschlagen: set[int],
    konversationsfach: int | None,
    client,
    zeiten: dict | None = None,
    letzte_antwort: str | None = None,
) -> Vorschlag | None:
    """Die Optionen des Dialogs — oder ``None``, wenn nichts vorzuschlagen ist.

    ``zeiten`` (0.26, Befund chat-r1): Sekunden seit dem Start je Stufe. Der Aufrufer hält das
    Wörterbuch, damit es auch nach einem Zeitlimit zeigt, wie weit der Vorschlag kam.

    ``letzte_antwort``: die letzte Nachricht des Assistenten — Kontext für den Klassifikator in
    der Assistenten-Konversation."""
    zeiten = {} if zeiten is None else zeiten
    t0 = time.monotonic()

    def marke(stufe: str) -> None:
        zeiten[stufe] = round(time.monotonic() - t0, 2)

    if vektor is None:
        return None
    kandidaten, aktuell = await _kandidaten(db, zugang, vektor, aktuell_id)
    marke("kandidaten")
    debug = {"kandidaten": {k.name: round(k.abstand, 3) for k in kandidaten.values()}, "zeiten": zeiten}

    def ohne_schon(optionen: list[Option]) -> Vorschlag | None:
        gezeigt = [o for o in optionen if o.assistant_id not in schon_vorgeschlagen]
        if len(gezeigt) < len(optionen):
            debug["ruheregel"] = [o.assistant_id for o in optionen if o.assistant_id in schon_vorgeschlagen]
        return Vorschlag(gezeigt, debug) if gezeigt else None

    if aktuell_id is not None:
        if aktuell is None:          # aktueller Assistent ohne Beispiele: keine Bezugsgröße
            return None
        debug["aktuell"] = round(aktuell, 3)
        band = im_assistenten_band(kandidaten)
        debug["band"] = [k.name for k in band]
        if not band or not settings.vorschlag_model:
            return None
        eigen = await db.get(Assistant, aktuell_id)
        band = await _mit_beispielen(db, vektor, band)
        marke("beispiele")
        antwort = await _aufruf(
            SYSTEM_IM_ASSISTENTEN,
            prompt_im_assistenten(nachricht, (eigen.name, (eigen.suggestion_text or eigen.description or "").strip()),
                                  letzte_antwort, band),
            modell=settings.vorschlag_model, client=client, marke=marke)
        marke("klassifikator")
        debug |= {"klassifikator": antwort["roh"][:300], "dauer": round(antwort["dauer"], 2)}
        ziel = lies_wechsel(antwort["roh"], {k.id for k in band})
        if ziel is None:
            return None
        k = kandidaten[ziel]
        return ohne_schon([Option(k.id, k.name, k.text, k.art)])

    band = sorted((k for k in kandidaten.values() if k.abstand < BAND), key=lambda k: k.abstand)
    debug["band"] = [k.name for k in band]
    if not band or not settings.vorschlag_model:
        return None
    band = await _mit_beispielen(db, vektor, band)
    marke("beispiele")
    antwort = await klassifiziere(nachricht, band, modell=settings.vorschlag_model, client=client, marke=marke)
    marke("klassifikator")
    debug |= {"klassifikator": antwort["roh"][:300], "dauer": round(antwort["dauer"], 2)}
    spez, rueck = lies_antwort(antwort["roh"], {k.id: k.art for k in band})
    return ohne_schon(zusammenstellen(spez, rueck, kandidaten, konversationsfach))
