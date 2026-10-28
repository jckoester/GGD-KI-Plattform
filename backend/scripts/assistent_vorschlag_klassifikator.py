#!/usr/bin/env python3
"""Gate-Messung „Assistent vorschlagen", Stufe 2: Klassifikator im Band (Päckchen C2, Schritt 1).

    cd backend && venv/bin/python scripts/assistent_vorschlag_klassifikator.py \\
        --modell chat-standard --ziel "<Vault>/Plaene/Messungen-Vorschlag" --lauf k1

**Warum:** C1 Schritt 5 ([[Messungen-Vorschlag/vorschlag-1]]) zeigte, dass Embeddings allein K1–K4
nicht tragen — spezifisch nur in einem Fenster von 0,01, Rückfall gar nicht. Folgerung: Embeddings
als **Vorfilter**, über die Kandidaten im Band entscheidet ein kurzer Modellaufruf.

**Ablauf je Fall** (Prüfsatz `scripts/szenarien/assistent_vorschlag.yaml`, nur `faelle`; K5 bleibt
bei den Embeddings, siehe `assistent_vorschlag_messung.py`):

1. Kandidaten = Assistenten des Prüfsatzes, deren Klassenstufen die Stufe einschließen.
2. **Band:** Kandidat ist, wessen bestes Auslöser-Beispiel näher als ``--band`` liegt (Vorgabe 0,50).
   Kein Kandidat im Band → kein Aufruf, keine Auswahl (F2).
3. **Klassifikator:** ein Aufruf an ``--modell`` über das **Systemkonto** (F1), mit der Nachricht und
   je Kandidat Name, Art (spezifisch/Rückfall), `suggestion_text` und den drei nächstliegenden
   Beispielen. Antwort JSON ``{"spezifisch": [...], "rueckfall": [...]}`` mit Kennungen.
4. **Auswahl** wie im Dialog (F7): höchstens zwei spezifische, darunter höchstens zwei Rückfälle —
   die `fallbacks` der gewählten spezifischen, sonst die Rückfälle des Klassifikators.

Gemessen: K1–K4 (Kopf des Prüfsatzes), Anteil der Fälle mit Aufruf, Dauer (Median, 90 %) und Kosten
je Aufruf. **Gate** (Plan C2, Schritt 1): K1–K4 erfüllt, Dauer im Median unter 2 s.

Nichts wird gespeichert. ⚠️ Nur Entwicklung — Kosten trägt das Systemkonto.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HIER = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("assistent_vorschlag_messung", HIER / "assistent_vorschlag_messung.py")
C1 = importlib.util.module_from_spec(_spec)
sys.modules["assistent_vorschlag_messung"] = C1      # @dataclass braucht das Modul im Register
_spec.loader.exec_module(C1)

BAND = 0.50
_AUFWAND = {"wert": "low"}


def args_aufwand():
    return _AUFWAND["wert"]
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


# ── Reine Funktionen (Unit-Test: tests/unit/test_assistent_vorschlag_klassifikator.py) ──


def im_band(abstaende: dict, band: float = BAND) -> list[str]:
    """Kandidaten, deren bestes Beispiel näher als ``band`` liegt — nächster zuerst."""
    return sorted((n for n, a in abstaende.items() if a.bsp < band), key=lambda n: abstaende[n].bsp)


def prompt_kandidaten(kandidaten: list[dict]) -> str:
    """Kandidatenliste für den Nutzerteil des Prompts."""
    zeilen = []
    for k in kandidaten:
        zeilen.append(f"- Kennung {k['id']} · {'spezifisch' if k['art'] == 'specific' else 'Rückfall'} · "
                      f"„Assistent für {k['name']}“: {k['text']}")
        zeilen += [f"    Beispiel: {b}" for b in k["beispiele"]]
    return "\n".join(zeilen)


def lies_antwort(roh: str, erlaubt: dict[int, str]) -> tuple[list[int], list[int]]:
    """JSON aus der Modellantwort — auch in Codeblock oder mit Text drumherum. Nur erlaubte
    Kennungen, je Liste ohne Dubletten. Unlesbares heißt „keiner“."""
    m = re.search(r"\{.*\}", roh or "", re.S)
    try:
        daten = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        daten = {}

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


def auswahl(spez: list[int], rueck: list[int], fallbacks: dict[int, list[int]], erlaubt: dict[int, str]
            ) -> list[int]:
    """F7: höchstens zwei spezifische; Rückfälle = `fallbacks` der gewählten, sonst die des
    Klassifikators — höchstens zwei, nur Kandidaten."""
    spez = spez[:2]
    unter = [f for s in spez for f in fallbacks.get(s, []) if erlaubt.get(f) == "fallback"]
    rueck = list(dict.fromkeys(unter or rueck))[:2]
    return spez + rueck


def bewerte(faelle: list[dict], namen_art: dict[str, str]) -> dict:
    """K1–K4 über die Auswahl je Fall (Feld ``gewaehlt``: Namen)."""
    pos = {n: [0, 0] for n in namen_art}
    nachbar = {n: [0, 0] for n in namen_art}
    stoer = []
    for f in faelle:
        g = set(f["gewaehlt"])
        for n in namen_art:
            if f["art"] == "positiv" and n in f["soll"]:
                pos[n][1] += 1
                pos[n][0] += n in g
            if f["art"] in ("nachbar", "fachfremd") and n in f["nicht"]:
                nachbar[n][1] += 1
                nachbar[n][0] += n in g
        if f["art"] in ("begriff", "alltag") and g:
            stoer.append(f["kennung"])
    k1 = all(t >= 4 * g / 5 for n, (t, g) in pos.items() if namen_art[n] == "specific")
    k2 = all(t >= 4 * g / 5 for n, (t, g) in pos.items() if namen_art[n] == "fallback")
    k3 = not stoer
    k4 = all(fehl <= max(1, g // 5) for fehl, g in nachbar.values())
    return {"positiv": pos, "nachbar": nachbar, "stoer": stoer, "K1": k1, "K2": k2, "K3": k3, "K4": k4,
            "ok": k1 and k2 and k3 and k4}


# ── Modellaufruf ─────────────────────────────────────────────────────────────


async def klassifiziere(client, modell: str, nachricht: str, kandidaten: list[dict]) -> dict:
    from app.config import settings
    from app.litellm import systemkonto
    from app.litellm.systemkonto import kosten_aus_antwort

    # ⚠️ Beide Modelle denken vor der Antwort (Reasoning): Mit `max_tokens` 200 war die Grenze
    # verbraucht, bevor die Antwort kam — Inhalt leer (Lauf k1, 28.10.2026). Deshalb Luft nach
    # oben und wenig Denkaufwand.
    rumpf = {"model": modell, "temperature": 0, "max_tokens": 2000,
             **({"reasoning_effort": args_aufwand()} if args_aufwand() != "none" else {}),
             "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Nachricht: „{nachricht}“\n\nAssistenten:\n{prompt_kandidaten(kandidaten)}"},
    ]}
    beginn = time.monotonic()
    import httpx

    for versuch in (1, 2):              # ein zweiter Versuch bei 5xx (Anbieter)
        try:
            antwort = await client.post(f"{settings.litellm_proxy_url}/chat/completions", json=rumpf,
                                        headers={"Authorization": f"Bearer {systemkonto.schluessel()}"})
        except httpx.HTTPError as fehler:
            return {"roh": "", "dauer": time.monotonic() - beginn, "usd": None, "tokens": {},
                    "fehler": f"{type(fehler).__name__}"}
        if antwort.status_code < 500:
            break
    dauer = time.monotonic() - beginn
    if antwort.status_code != 200:
        return {"roh": "", "dauer": dauer, "usd": None, "tokens": {},
                "fehler": f"HTTP {antwort.status_code}: {antwort.text[:160]}"}
    await systemkonto.verbuche(antwort)
    daten = antwort.json()
    return {"roh": daten["choices"][0]["message"].get("content") or "", "dauer": dauer,
            "usd": kosten_aus_antwort(antwort), "tokens": daten.get("usage") or {}}


async def lade(db, namen):
    """Wie C1, dazu Texte der Beispiele, `suggestion_text` und `fallbacks` (IDs)."""
    import sqlalchemy as sa
    from app.config import settings
    from app.db.models import Assistant, AssistantTriggerExample

    info = await C1.lade_assistenten(db, namen)
    for name, i in info.items():
        a = await db.get(Assistant, i["id"])
        zeilen = (await db.execute(sa.select(AssistantTriggerExample).where(
            AssistantTriggerExample.assistant_id == a.id, AssistantTriggerExample.art == "beispiel",
            AssistantTriggerExample.embedding_model == settings.embedding_model,
            AssistantTriggerExample.embedding.is_not(None)))).scalars().all()
        i["texte"] = [z.text_ for z in zeilen]
        i["vektoren"] = np.array([np.asarray(z.embedding, dtype=float) for z in zeilen])
        i["suggestion_text"] = (a.suggestion_text or a.description or "").strip()
        i["fallbacks"] = list(a.fallbacks or [])
    return info


def naechste_beispiele(vektor, i, n=BEISPIELE_IM_PROMPT) -> list[str]:
    d = C1.kosinus_distanz(np.asarray(vektor, dtype=float), i["vektoren"])
    return [i["texte"][j] for j in np.argsort(d)[:n]]


# ── Bericht ──────────────────────────────────────────────────────────────────


def bericht(kopf: dict, faelle: list[dict], ergebnis: dict) -> str:
    dauern = [f["aufruf"]["dauer"] for f in faelle if f.get("aufruf")]
    kosten = [f["aufruf"]["usd"] for f in faelle if f.get("aufruf") and f["aufruf"]["usd"] is not None]
    mit = [f for f in faelle if f.get("aufruf")]
    t = [f"# Assistent vorschlagen — Klassifikator im Band, Lauf {kopf['lauf']}", "",
         f"- **Datum:** {kopf['datum']}", f"- **Klassifikator:** `{kopf['modell']}` (Systemkonto)",
         f"- **Embedding:** `{kopf['embedding']}`, Band < {str(kopf['band']).replace('.', ',')}",
         f"- **Denkaufwand:** `reasoning_effort` {kopf['aufwand']}",
         f"- **Prüfsatz:** `scripts/szenarien/assistent_vorschlag.yaml`, {len(faelle)} Fälle (K5 nicht hier)", "",
         "## Ergebnis", ""]
    for k in ("K1", "K2", "K3", "K4"):
        t.append(f"- **{k}:** {'✓' if ergebnis[k] else '✗'}")
    t.append("- **Positive in der Auswahl:** " + "; ".join(f"{n} {a}/{g}" for n, (a, g) in ergebnis["positiv"].items()))
    t.append("- **Nachbar-Fehltreffer:** " + "; ".join(f"{n} {a}/{g}" for n, (a, g) in ergebnis["nachbar"].items()))
    t.append(f"- **Begriff/Alltag mit Auswahl:** {', '.join(ergebnis['stoer']) or '—'}")
    leer = [f["kennung"] + (f" ({f['aufruf']['fehler']})" if f["aufruf"].get("fehler") else "")
            for f in faelle if f.get("aufruf") and not f["aufruf"]["roh"].strip()]
    t.append(f"- ⚠️ **Leere Antworten:** {len(leer)}" + (f" — {'; '.join(leer)}" if leer else ""))
    nach_art = {}
    for f in faelle:
        nach_art.setdefault(f["art"], [0, 0])
        nach_art[f["art"]][1] += 1
        nach_art[f["art"]][0] += bool(f.get("aufruf"))
    t.append(f"- **Mit Aufruf:** {len(mit)} von {len(faelle)} Fällen ("
             + ", ".join(f"{a} {m}/{g}" for a, (m, g) in nach_art.items()) + ")")
    if dauern:
        q = sorted(dauern)
        t.append(f"- **Dauer je Aufruf:** Median {statistics.median(dauern):.2f} s, 90 % ≤ "
                 f"{q[min(len(q) - 1, int(0.9 * len(q)))]:.2f} s, längster {max(dauern):.2f} s")
    if kosten:
        t.append(f"- **Kosten:** {sum(kosten):.5f} USD für {len(kosten)} Aufrufe (Mittel {sum(kosten) / len(kosten):.5f};"
                 f" je Fall über alle {sum(kosten) / len(faelle):.5f})")
    t.append(f"- **Gate (K1–K4, Median < 2 s, keine leere Antwort):** "
             f"{'erfüllt' if ergebnis['ok'] and not leer and dauern and statistics.median(dauern) < 2 else 'nicht erfüllt'}")
    t += ["", "## Je Fall", "", "| Fall | Art | Kl. | soll | im Band | Klassifikator | Auswahl | s |",
          "|---|---|---|---|---|---|---|---|"]
    for f in faelle:
        a = f.get("aufruf") or {}
        t.append(f"| {f['kennung']} | {f['art']} | {f['stufe']} | {', '.join(f['soll']) or '—'} | "
                 + (", ".join(f"{n} {f['abstaende'][n].bsp:.3f}".replace(".", ",") for n in f["band"]) or "—")
                 + f" | {(a.get('roh') or '—').replace(chr(10), ' ')[:80]} | {', '.join(f['gewaehlt']) or '—'} | "
                 + (f"{a['dauer']:.2f}" if a else "") + " |")
    return "\n".join(t) + "\n"


async def main_async(args):
    import httpx
    from app.config import settings
    from app.context.embedding import generate_embeddings
    from app.db.session import AsyncSessionLocal

    satz = yaml.safe_load(C1.PRUEFSATZ.read_text(encoding="utf-8"))
    namen = satz["assistenten"]["spezifisch"] + satz["assistenten"]["rueckfall"]
    async with AsyncSessionLocal() as db:
        info = await lade(db, namen)
    namen_art = {n: info[n]["suggest"] for n in namen}
    id_name = {i["id"]: n for n, i in info.items()}

    faelle = [{**f, "kennung": f.get("quelle", f.get("text", ""))[:45], "text": C1.text_des_falls(f),
               "soll": f.get("soll") or [], "nicht": f.get("nicht") or []} for f in satz["faelle"]]
    if args.nur_art:
        faelle = [f for f in faelle if f["art"] in args.nur_art]
    vektoren = (await generate_embeddings([f["text"] for f in faelle])).vektoren

    async with httpx.AsyncClient(timeout=60.0, verify=settings.litellm_verify_ssl) as client:
        for f, v in zip(faelle, vektoren):
            f["abstaende"] = C1.abstaende_fuer(v, f["stufe"], info)
            f["band"] = im_band(f["abstaende"], args.band)
            f["gewaehlt"] = []
            if not f["band"]:
                continue
            kand = [{"id": info[n]["id"], "name": n, "art": info[n]["suggest"], "text": info[n]["suggestion_text"],
                     "beispiele": naechste_beispiele(v, info[n])} for n in f["band"]]
            erlaubt = {k["id"]: k["art"] for k in kand}
            f["aufruf"] = await klassifiziere(client, args.modell, f["text"], kand)
            spez, rueck = lies_antwort(f["aufruf"]["roh"], erlaubt)
            f["gewaehlt"] = [id_name[i] for i in
                             auswahl(spez, rueck, {info[n]["id"]: info[n]["fallbacks"] for n in f["band"]}, erlaubt)]
            print(f"{f['kennung'][:40]:<41} {f['art']:<9} band {len(f['band'])} → {', '.join(f['gewaehlt']) or '—'}"
                  f"  ({f['aufruf']['dauer']:.2f} s)", flush=True)

    ergebnis = bewerte(faelle, namen_art)
    kopf = {"lauf": args.lauf, "datum": datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y, %H:%M"),
            "modell": args.modell, "embedding": settings.embedding_model, "band": args.band, "aufwand": args.aufwand}
    text = bericht(kopf, faelle, ergebnis)
    if args.ziel:
        args.ziel.mkdir(parents=True, exist_ok=True)
        (args.ziel / f"vorschlag-{args.lauf}.md").write_text(text, encoding="utf-8")
        roh = {"kopf": kopf, "ergebnis": {k: v for k, v in ergebnis.items()},
               "faelle": [{k: v for k, v in f.items() if k != "abstaende"}
                          | {"abstaende": {n: a.bsp for n, a in f["abstaende"].items()}} for f in faelle]}
        (args.ziel / f"vorschlag-{args.lauf}.json").write_text(json.dumps(roh, ensure_ascii=False, indent=1),
                                                                encoding="utf-8")
        print(f"Protokoll: {args.ziel / f'vorschlag-{args.lauf}.md'}")
    else:
        print(text)


def main() -> None:
    p = argparse.ArgumentParser(description="Gate-Messung Assistent vorschlagen, Klassifikator im Band (C2 Schritt 1)")
    p.add_argument("--modell", default="chat-standard", help="Modell-Alias des Klassifikators")
    p.add_argument("--band", type=float, default=BAND, help="Vorfilter: bestes Beispiel näher als dieser Abstand")
    p.add_argument("--lauf", default="k1")
    p.add_argument("--ziel", type=Path, default=None)
    p.add_argument("--aufwand", default="low",
                   help="reasoning_effort des Klassifikators (low, medium, high; none = nicht senden)")
    p.add_argument("--nur-art", action="append", dest="nur_art", default=None,
                   help="nur Fälle dieser Art (positiv, nachbar, begriff, alltag, fachfremd)")
    args = p.parse_args()
    _AUFWAND["wert"] = args.aufwand
    from app.config import settings
    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz.")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
