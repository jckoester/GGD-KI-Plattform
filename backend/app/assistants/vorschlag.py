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

**In einer Assistenten-Konversation** genügen die Embeddings (C1, K5): Ein anderer Assistent
nur, wenn er um :data:`MARGE` näher liegt als der aktuelle; liegt die Nachricht weit vom
aktuellen weg (:data:`BEENDEN`), wird „Assistent beenden“ angeboten.

**Ruheregel** (F4): Wer in ``schon_vorgeschlagen`` steht, kommt nicht wieder; 0 steht für
„Assistent beenden“. Der Chat-Flow leert die Menge bei einem angenommenen Wechsel.

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
#: In der Assistenten-Konversation (K5, Lauf `vorschlag-2`, 28.10.2026): Schwelle für einen
#: spezifischen Treffer, Marge gegenüber dem aktuellen Assistenten, Schwelle fürs Beenden.
SPEZIFISCH_IM_ASSISTENTEN = 0.41
MARGE = 0.05
BEENDEN = 0.49
#: Kennung von „Assistent beenden“ in der Ruheregel.
BEENDEN_KENNUNG = 0
#: Wie viele Beispiele je Kandidat in den Prompt gehen.
BEISPIELE_IM_PROMPT = 3

SYSTEM = """Du ordnest die Nachricht einer Schülerin oder eines Schülers Assistenten einer Schulplattform zu.
Ein Assistent passt nur, wenn die Nachricht eine **Aufgabe aus seinem Gebiet** ist, bei der er begleiten kann —
nicht schon, wenn ein Fachwort darin vorkommt.

Keinen Assistenten wählst du bei:
- einer Frage nach einem Begriff oder einer Erklärung („Was ist ein Mol?“) — die beantwortet der normale Chat,
- Alltag, Organisatorischem, Small Talk,
- einer Aufgabe aus einem anderen Gebiet (etwa Mathematik ohne naturwissenschaftlichen Bezug),
- Referaten, Präsentationen, Gliederungen und dem Schreiben von Texten — auch wenn das Thema naturwissenschaftlich
  ist: Entscheidend ist die Art der Aufgabe, nicht ihr Thema.

Spezifische Assistenten haben eine eng umrissene Aufgabe; wähle sie nur, wenn genau diese Aufgabe gestellt ist.
Rückfall-Assistenten decken ein ganzes Gebiet ab; wähle einen, wenn die Aufgabe in sein Gebiet fällt, auch wenn
kein spezifischer passt.

Antworte nur mit JSON, ohne Erklärung: {"spezifisch": [Kennungen], "rueckfall": [Kennungen]} — leere Listen,
wenn keiner passt."""


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
    darunter höchstens zwei Rückfälle: die `fallbacks` der gewählten spezifischen, sonst die des
    Klassifikators. Nur Kandidaten (sichtbar, nicht schon vorgeschlagen)."""
    def schluessel(i):
        k = kandidaten[i]
        return (konversationsfach is None or k.subject_id != konversationsfach, k.abstand)
    gewaehlt = sorted((i for i in spez if i in kandidaten), key=schluessel)[:2]
    unter = [f for s in gewaehlt for f in kandidaten[s].fallbacks
             if f in kandidaten and kandidaten[f].art == "fallback"]
    rueckfaelle = list(dict.fromkeys(unter or [i for i in rueck if i in kandidaten]))[:2]
    return [Option(i, kandidaten[i].name, kandidaten[i].text, kandidaten[i].art)
            for i in gewaehlt + rueckfaelle]


def im_assistenten(aktuell: float, kandidaten: dict[int, Kandidat], beenden_erlaubt: bool) -> list[Option]:
    """K5: Wechsel zu einem spezifischen, der um die Marge näher liegt (und näher an seinen
    Beispielen als an seinen Gegenbeispielen) — sonst „beenden“, wenn die Nachricht weit vom
    aktuellen Assistenten liegt — sonst nichts."""
    andere = sorted((k for k in kandidaten.values()
                     if k.art == "specific" and k.abstand <= SPEZIFISCH_IM_ASSISTENTEN
                     and k.abstand < k.gegen and k.abstand + MARGE < aktuell),
                    key=lambda k: k.abstand)
    if andere:
        k = andere[0]
        return [Option(k.id, k.name, k.text, k.art)]
    if aktuell > BEENDEN and beenden_erlaubt:
        return [Option(BEENDEN_KENNUNG, "", "", "beenden")]
    return []


# ── Datenbank und Modell ─────────────────────────────────────────────────────


async def _kandidaten(
    db: AsyncSession, zugang: Zugang, vektor, ausschliessen: set[int], aktuell_id: int | None
) -> tuple[dict[int, Kandidat], float | None]:
    """Sichtbare Assistenten mit Vorschlag und Beispielen, je mit bestem Beispiel und
    Gegenbeispiel. Dazu der Abstand des aktuellen Assistenten (oder ``None``)."""
    sichtbar = (await db.execute(
        sa.select(Assistant).where(sichtbar_klausel(zugang), Assistant.suggest != "never")
    )).scalars().all()
    ids = [a.id for a in sichtbar if a.id not in ausschliessen and a.id != aktuell_id]
    abfrage_ids = ids + ([aktuell_id] if aktuell_id is not None else [])
    if not abfrage_ids:
        return {}, None
    distanz = AssistantTriggerExample.embedding.cosine_distance(vektor)
    zeilen = (await db.execute(
        sa.select(AssistantTriggerExample.assistant_id, AssistantTriggerExample.art,
                  sa.func.min(distanz))
        .where(AssistantTriggerExample.assistant_id.in_(abfrage_ids),
               AssistantTriggerExample.embedding_model == settings.embedding_model,
               AssistantTriggerExample.embedding.is_not(None))
        .group_by(AssistantTriggerExample.assistant_id, AssistantTriggerExample.art)
    )).all()
    beste: dict[tuple[int, str], float] = {(a, art): float(d) for a, art, d in zeilen}
    nach_id = {a.id: a for a in sichtbar}
    kandidaten = {
        i: Kandidat(
            id=i, name=nach_id[i].name, art=nach_id[i].suggest,
            text=(nach_id[i].suggestion_text or nach_id[i].description or "").strip(),
            subject_id=nach_id[i].subject_id, fallbacks=tuple(nach_id[i].fallbacks or ()),
            abstand=beste[(i, "beispiel")], gegen=beste.get((i, "gegenbeispiel"), float("inf")),
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


async def klassifiziere(nachricht: str, band: list[Kandidat], *, modell: str, client) -> dict:
    """Ein Aufruf über das Systemkonto. Wirft bei Netz- oder HTTP-Fehlern."""
    from app.litellm import systemkonto

    rumpf = {"model": modell, "temperature": 0, "max_tokens": 400, "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Nachricht: „{nachricht}“\n\nAssistenten:\n{prompt_kandidaten(band)}"},
    ]}
    beginn = time.monotonic()
    antwort = await client.post(f"{settings.litellm_proxy_url}/chat/completions", json=rumpf,
                                headers={"Authorization": f"Bearer {systemkonto.schluessel()}"})
    antwort.raise_for_status()
    await systemkonto.verbuche(antwort)
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
) -> Vorschlag | None:
    """Die Optionen des Dialogs — oder ``None``, wenn nichts vorzuschlagen ist."""
    if vektor is None:
        return None
    kandidaten, aktuell = await _kandidaten(db, zugang, vektor, schon_vorgeschlagen, aktuell_id)
    debug = {"kandidaten": {k.name: round(k.abstand, 3) for k in kandidaten.values()}}

    if aktuell_id is not None:
        if aktuell is None:          # aktueller Assistent ohne Beispiele: keine Bezugsgröße
            return None
        debug["aktuell"] = round(aktuell, 3)
        optionen = im_assistenten(aktuell, kandidaten, BEENDEN_KENNUNG not in schon_vorgeschlagen)
        return Vorschlag(optionen, debug) if optionen else None

    band = sorted((k for k in kandidaten.values() if k.abstand < BAND), key=lambda k: k.abstand)
    debug["band"] = [k.name for k in band]
    if not band or not settings.vorschlag_model:
        return None
    band = await _mit_beispielen(db, vektor, band)
    antwort = await klassifiziere(nachricht, band, modell=settings.vorschlag_model, client=client)
    debug |= {"klassifikator": antwort["roh"][:300], "dauer": round(antwort["dauer"], 2)}
    spez, rueck = lies_antwort(antwort["roh"], {k.id: k.art for k in band})
    optionen = zusammenstellen(spez, rueck, kandidaten, konversationsfach)
    return Vorschlag(optionen, debug) if optionen else None
