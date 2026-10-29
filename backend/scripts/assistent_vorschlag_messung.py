#!/usr/bin/env python3
"""Vorlauf-Messung „Assistent vorschlagen" (Päckchen C1, Schritt 5).

    cd backend && venv/bin/python scripts/assistent_vorschlag_messung.py \\
        --ziel "<Vault>/Plaene/Messungen-Vorschlag" --lauf 1

**Die Frage:** Bringen die Auslöser-Beispiele den richtigen Assistenten in die Auswahl, ohne
Nachbarn, Begriffsfragen und Alltagssätze mitzuziehen? Prüfsatz und Kriterium K1–K5:
`scripts/szenarien/assistent_vorschlag.yaml` (Schritt 0).

**Was gemessen wird:** Je Prüftext **ein** Embedding (dasselbe Modell wie für die Beispiele,
`settings.embedding_model`, über den Proxy). Je Kandidat zählt das **beste** Beispiel — die
kleinste Kosinus-Distanz zu seinen Auslöser-Beispielen (`d_bsp`) —, dazu das beste Gegenbeispiel
(`d_gegen`). Kandidaten sind die Assistenten des Prüfsatzes, deren Klassenstufen die Stufe des
Falls einschließen (wie die Übersicht, `sichtbarkeit.py`).

**Abgetastet:**
- Schwelle **spezifisch** und Schwelle **Rückfall** getrennt (sie wirken auf verschiedene
  Assistenten), je mit und ohne **Gegenbeispiel-Regel** („trifft nur, wenn das beste Beispiel
  näher liegt als das beste Gegenbeispiel“). Bewertet nach K1–K4.
- Für die gewählten Schwellen: **Marge** und Schwelle **„Assistent beenden“** in der
  Assistenten-Konversation (K5).

Nichts wird gespeichert; die Nachrichten-Embeddings leben nur im Lauf. ⚠️ Nur Entwicklung.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HIER = Path(__file__).resolve().parent
PRUEFSATZ = HIER / "szenarien/assistent_vorschlag.yaml"

#: Unter diesem Abstand zu einem eingebetteten Beispiel oder Gegenbeispiel gilt ein Prüftext als
#: Fast-Dublette (Wortwahl nahezu gleich) — im Bericht genannt.
FAST_DUBLETTE = 0.20
RASTER_SPEZ = [round(0.30 + 0.01 * i, 2) for i in range(41)]    # 0,30 … 0,70
RASTER_RUECK = [round(0.30 + 0.01 * i, 2) for i in range(46)]   # 0,30 … 0,75
RASTER_MARGE = [round(0.01 * i, 2) for i in range(16)]          # 0,00 … 0,15
RASTER_BEENDEN = [round(0.40 + 0.01 * i, 2) for i in range(41)]  # 0,40 … 0,80


# ── Reine Funktionen (Unit-Test: tests/unit/test_assistent_vorschlag_messung.py) ──


def text_des_falls(fall: dict, szenarien: Path = HIER / "szenarien") -> str:
    """`text` oder der erste Schülerzug von `quelle` (`datei#fall-id`)."""
    if "text" in fall:
        return fall["text"]
    datei, fid = fall["quelle"].split("#")
    faelle = yaml.safe_load((szenarien / datei).read_text(encoding="utf-8"))["faelle"]
    return next(f for f in faelle if f["id"] == fid)["zuege"][0]["schueler"]


def kosinus_distanz(v: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """1 − cos zwischen ``v`` und jeder Zeile von ``matrix`` (wie pgvector ``<=>``)."""
    if matrix.size == 0:
        return np.array([])
    return 1.0 - (matrix @ v) / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(v))


@dataclass(frozen=True)
class Abstand:
    bsp: float          # bestes Auslöser-Beispiel
    gegen: float        # bestes Gegenbeispiel (inf, wenn keins)


def trifft(a: Abstand, schwelle: float, gegen_regel: bool) -> bool:
    return a.bsp <= schwelle and (not gegen_regel or a.bsp < a.gegen)


def auswahl(abstaende: dict[str, Abstand], art: dict[str, str], s_spez: float, s_rueck: float,
            gegen_regel: bool, ohne: str | None = None) -> list[str]:
    """Höchstens zwei spezifische Treffer (bester zuerst), dann höchstens zwei Rückfälle.
    ``abstaende`` enthält nur Kandidaten; ``ohne`` = der aktuelle Assistent der Konversation."""
    def treffer(typ, schwelle):
        namen = [n for n, a in abstaende.items()
                 if n != ohne and art[n] == typ and trifft(a, schwelle, gegen_regel)]
        return sorted(namen, key=lambda n: abstaende[n].bsp)[:2]
    return treffer("specific", s_spez) + treffer("fallback", s_rueck)


def bewerte_spezifisch(faelle, s, gegen_regel, art):
    """K1, K3, K4 für die spezifischen Assistenten bei Schwelle ``s``."""
    return _bewerte(faelle, art, "specific", s, gegen_regel)


def bewerte_rueckfall(faelle, s, gegen_regel, art):
    """K2, K3, K4 für den Rückfall bei Schwelle ``s``."""
    return _bewerte(faelle, art, "fallback", s, gegen_regel)


def _bewerte(faelle, art, typ, s, gegen_regel):
    namen = [n for n, t in art.items() if t == typ]
    pos = {n: [0, 0] for n in namen}        # [in Auswahl, gesamt]
    nachbar = {n: [0, 0] for n in namen}    # [Fehltreffer, gesamt]
    stoer = []                              # Begriff/Alltag mit einem Treffer dieses Typs
    for f in faelle:
        gewaehlt = [n for n in namen if n in f["abstaende"] and trifft(f["abstaende"][n], s, gegen_regel)]
        gewaehlt = sorted(gewaehlt, key=lambda n: f["abstaende"][n].bsp)[:2]
        for n in namen:
            if f["art"] == "positiv" and n in f["soll"]:
                pos[n][1] += 1
                pos[n][0] += n in gewaehlt
            if f["art"] in ("nachbar", "fachfremd") and n in f.get("nicht", []):
                nachbar[n][1] += 1
                nachbar[n][0] += n in gewaehlt
        if f["art"] in ("begriff", "alltag") and gewaehlt:
            stoer.append(f["kennung"])
    k_pos = all(t >= 4 * g / 5 for t, g in pos.values())
    k_stoer = not stoer
    k_nachbar = all(fehl <= max(1, g // 5) for fehl, g in nachbar.values())
    return {"schwelle": s, "gegen_regel": gegen_regel, "positiv": pos, "nachbar": nachbar,
            "stoer": stoer, "ok": k_pos and k_stoer and k_nachbar,
            "k_pos": k_pos, "k_stoer": k_stoer, "k_nachbar": k_nachbar}


def entscheidung_im_assistenten(abstaende, art, aktuell, s_spez, s_rueck, gegen_regel,
                                marge, s_beenden) -> tuple[str, str | None]:
    """`wechsel` (zu wem) oder `bleiben` — die reine Embedding-Regel K5-neu (29.10.2026), die
    der Dienst bis zum Klassifikator in der Assistenten-Konversation hatte: ein anderer Assistent
    unter 0,45 (Rückfall 0,30), näher an seinen Beispielen als an seinen Gegenbeispielen, um die
    Marge näher als der aktuelle (``marge`` für spezifische, 0,10 für Rückfälle). Bleibt als
    Vergleich; den Dienst misst `assistent_vorschlag_k5_messung.py`. ``s_spez``, ``s_rueck`` und
    ``s_beenden`` bleiben nur der Signatur halber."""
    IM_ASSISTENTEN, IM_ASSISTENTEN_RUECKFALL, MARGE_RUECKFALL = 0.45, 0.30, 0.10
    eigen = abstaende[aktuell].bsp
    andere = sorted((n for n, a in abstaende.items()
                     if n != aktuell
                     and a.bsp < (IM_ASSISTENTEN if art[n] == "specific" else IM_ASSISTENTEN_RUECKFALL)
                     and a.bsp < a.gegen
                     and a.bsp + (marge if art[n] == "specific" else MARGE_RUECKFALL) < eigen),
                    key=lambda n: abstaende[n].bsp)
    if andere:
        return "wechsel", andere[0]
    return "bleiben", None


def bewerte_k5(faelle, art, s_spez, s_rueck, gegen_regel, marge, s_beenden):
    fehler = {"bleiben": [], "wechsel": [], "beenden": []}
    for f in faelle:
        ergebnis, ziel = entscheidung_im_assistenten(f["abstaende"], art, f["aktuell"], s_spez, s_rueck,
                                                    gegen_regel, marge, s_beenden)
        richtig = ((ergebnis == f["erwartet"] and (ergebnis != "wechsel" or ziel == f.get("wechsel_zu")))
                   or ergebnis in (f.get("darf") or []))
        if not richtig:
            fehler[f["erwartet"]].append(f["text"][:40])
    ok = all(len(v) <= 1 for v in fehler.values())
    return {"marge": marge, "s_beenden": s_beenden, "fehler": fehler, "ok": ok,
            "fehler_gesamt": sum(len(v) for v in fehler.values())}


def bereiche(werte: list[dict]) -> list[tuple[float, float]]:
    """Zusammenhängende Schwellenbereiche mit ``ok`` — für den Bericht."""
    aus, start, vorher = [], None, None
    for w in werte:
        if w["ok"] and start is None:
            start = w["schwelle"]
        if not w["ok"] and start is not None:
            aus.append((start, vorher))
            start = None
        vorher = w["schwelle"]
    if start is not None:
        aus.append((start, vorher))
    return aus


# ── Datenbank und Embeddings ─────────────────────────────────────────────────


async def lade_assistenten(db, namen):
    import sqlalchemy as sa
    from app.config import settings
    from app.db.models import Assistant, AssistantTriggerExample
    zeilen = (await db.execute(sa.select(Assistant).where(Assistant.name.in_(namen)))).scalars().all()
    if len(zeilen) != len(namen):
        fehlt = set(namen) - {a.name for a in zeilen}
        raise SystemExit(f"Assistenten fehlen in der DB: {', '.join(sorted(fehlt))} — Seed laufen lassen.")
    info = {}
    for a in zeilen:
        beispiele = (await db.execute(sa.select(AssistantTriggerExample).where(
            AssistantTriggerExample.assistant_id == a.id,
            AssistantTriggerExample.embedding_model == settings.embedding_model,
            AssistantTriggerExample.embedding.is_not(None),
        ))).scalars().all()
        matrix = {art: np.array([np.asarray(b.embedding, dtype=float) for b in beispiele if b.art == art])
                  for art in ("beispiel", "gegenbeispiel")}
        if not len(matrix["beispiel"]):
            raise SystemExit(f"„{a.name}“ hat keine eingebetteten Beispiele — Seed bzw. embedding_backfill.")
        info[a.name] = {"id": a.id, "suggest": a.suggest, "min": a.min_grade, "max": a.max_grade,
                        "matrix": matrix, "n": {k: len(v) for k, v in matrix.items()}}
    return info


def abstaende_fuer(vektor, stufe, info):
    v = np.asarray(vektor, dtype=float)
    aus = {}
    for name, a in info.items():
        if (a["min"] or 1) <= stufe <= (a["max"] or 13):
            d_bsp = float(kosinus_distanz(v, a["matrix"]["beispiel"]).min())
            gegen = kosinus_distanz(v, a["matrix"]["gegenbeispiel"])
            aus[name] = Abstand(d_bsp, float(gegen.min()) if gegen.size else float("inf"))
    return aus


# ── Bericht ──────────────────────────────────────────────────────────────────


def _zahl(x: float) -> str:
    return "–" if x == float("inf") else f"{x:.3f}".replace(".", ",")


def bericht(kopf, faelle, im_assi, spez, rueck, k5, wahl, namen, fast_dubletten=()) -> str:
    t = [f"# Assistent vorschlagen — Vorlauf-Messung, Lauf {kopf['lauf']}", "",
         f"- **Datum:** {kopf['datum']}", f"- **Embedding-Modell:** `{kopf['modell']}`",
         "- **Beispiele:** " + " · ".join(f"{n}: {i['n']['beispiel']} Beispiele, {i['n']['gegenbeispiel']} Gegenbeispiele"
                                          for n, i in kopf["assistenten"].items()),
         f"- **Prüfsatz:** `scripts/szenarien/assistent_vorschlag.yaml`, {len(faelle)} Fälle + {len(im_assi)} in "
         "Assistenten-Konversationen; Kriterium K1–K5 dort im Kopf", ""]
    t += ["## Ergebnis", ""]
    for typ, werte in (("spezifisch", spez), ("Rückfall", rueck)):
        for g in (False, True):
            b = bereiche([w for w in werte if w["gegen_regel"] == g])
            t.append(f"- **Schwelle {typ}, {'mit' if g else 'ohne'} Gegenbeispiel-Regel:** "
                     + (", ".join(f"{_zahl(a)}–{_zahl(e)}" for a, e in b) if b else "**kein** Wert erfüllt das Kriterium"))
    if wahl:
        t.append(f"- **Gewählt für K5:** spezifisch {_zahl(wahl['s_spez'])}, Rückfall "
                 f"{_zahl(wahl['s_rueck']) if wahl['s_rueck'] else 'abgeschaltet (kein Wert erfüllt K2–K4)'}, "
                 f"Gegenbeispiel-Regel {'an' if wahl['gegen_regel'] else 'aus'} (jeweils Mitte des breitesten Bereichs)")
        beste = min(k5, key=lambda w: (w["fehler_gesamt"], -w["marge"])) if k5 else None
        ok = [w for w in k5 if w["ok"]]
        t.append(f"- **K5:** {len(ok)} von {len(k5)} Kombinationen (Marge × Beenden-Schwelle) erfüllen „je Art "
                 f"höchstens ein Fehler“" + (f"; wenigste Fehler ({beste['fehler_gesamt']}) z. B. bei Marge "
                 f"{_zahl(beste['marge'])}, Beenden {_zahl(beste['s_beenden'])}: "
                 + "; ".join(f"{k}: {', '.join(v) or '—'}" for k, v in beste["fehler"].items()) if beste else ""))
    if fast_dubletten:
        t.append(f"- ⚠️ **Fast-Dubletten** (Abstand < {_zahl(FAST_DUBLETTE)} zu einem eingebetteten Text): "
                 + "; ".join(f"„{txt}“ {_zahl(d)}" for d, txt in fast_dubletten))
    t += ["", "## Abstände je Fall (bestes Beispiel / bestes Gegenbeispiel)", "",
          "| Fall | Art | Kl. | soll | " + " | ".join(namen) + " |",
          "|---|---|---|---|" + "---|" * len(namen)]
    for f in faelle:
        zellen = []
        for n in namen:
            a = f["abstaende"].get(n)
            zellen.append("—" if a is None else f"{_zahl(a.bsp)} / {_zahl(a.gegen)}")
        t.append(f"| {f['kennung']} | {f['art']} | {f['stufe']} | {', '.join(f['soll']) or '—'} | " + " | ".join(zellen) + " |")
    t += ["", "## In der Assistenten-Konversation", "",
          "| Nachricht | aktuell | erwartet | " + " | ".join(namen) + " |", "|---|---|---|" + "---|" * len(namen)]
    for f in im_assi:
        zellen = []
        for n in namen:
            a = f["abstaende"].get(n)
            zellen.append("—" if a is None else f"{_zahl(a.bsp)} / {_zahl(a.gegen)}")
        ziel = f" → {f['wechsel_zu']}" if f.get("wechsel_zu") else ""
        t.append(f"| {f['text'][:50]} | {f['aktuell']} | {f['erwartet']}{ziel} | " + " | ".join(zellen) + " |")
    t += ["", "## Abtastung (Auszug: jede fünfte Schwelle)", ""]
    for typ, werte in (("spezifisch", spez), ("Rückfall", rueck)):
        t += [f"### {typ}", "", "| Schwelle | Regel | Positive | Nachbar-Fehltreffer | Begriff/Alltag | ok |",
              "|---|---|---|---|---|---|"]
        for w in werte:
            if round(w["schwelle"] * 100) % 5:
                continue
            t.append(f"| {_zahl(w['schwelle'])} | {'Gegen' if w['gegen_regel'] else '—'} | "
                     + "; ".join(f"{n}: {a}/{g}" for n, (a, g) in w["positiv"].items()) + " | "
                     + "; ".join(f"{n}: {a}/{g}" for n, (a, g) in w["nachbar"].items()) + f" | {len(w['stoer'])} | "
                     + ("✓" if w["ok"] else "") + " |")
        t.append("")
    return "\n".join(t) + "\n"


def _mitte(werte):
    b = bereiche(werte)
    if not b:
        return None
    a, e = max(b, key=lambda x: x[1] - x[0])
    return round((a + e) / 2, 2), e - a


async def main_async(args):
    from app.config import settings
    from app.context.embedding import generate_embeddings
    from app.db.session import AsyncSessionLocal

    satz = yaml.safe_load(PRUEFSATZ.read_text(encoding="utf-8"))
    namen = satz["assistenten"]["spezifisch"] + satz["assistenten"]["rueckfall"]
    async with AsyncSessionLocal() as db:
        info = await lade_assistenten(db, namen)
    art = {n: info[n]["suggest"] for n in namen}

    faelle = [{**f, "kennung": f.get("quelle", f.get("text", ""))[:45], "text": text_des_falls(f),
               "soll": f.get("soll") or [], "nicht": f.get("nicht") or []} for f in satz["faelle"]]
    im_assi = [dict(f) for f in satz["in_assistent"]]
    texte = [f["text"] for f in faelle] + [f["text"] for f in im_assi]
    vektoren = (await generate_embeddings(texte)).vektoren
    for f, v in zip(faelle + im_assi, vektoren):
        f["abstaende"] = abstaende_fuer(v, f["stufe"], info)
    # Fast-Dubletten: Ein Prüftext, der fast wörtlich unter den eingebetteten Texten steht, misst
    # wenig (der Unit-Test fängt nur wörtliche Gleichheit).
    nah = sorted(((min(min(a.bsp, a.gegen) for a in f["abstaende"].values()), f["text"][:50])
                  for f in faelle + im_assi if f["abstaende"]), key=lambda x: x[0])
    fast_dubletten = [(d, t) for d, t in nah if d < FAST_DUBLETTE]

    spez = [bewerte_spezifisch(faelle, s, g, art) for g in (False, True) for s in RASTER_SPEZ]
    rueck = [bewerte_rueckfall(faelle, s, g, art) for g in (False, True) for s in RASTER_RUECK]

    wahl, k5 = None, []
    kandidaten = []
    for g in (False, True):
        ms = _mitte([w for w in spez if w["gegen_regel"] == g])
        mr = _mitte([w for w in rueck if w["gegen_regel"] == g])
        if ms and mr:
            kandidaten.append((ms[1] + mr[1], g, ms[0], mr[0]))
    if not kandidaten:
        # Kein Rückfall-Wert erfüllt K2–K4: K5 trotzdem messen, mit abgeschaltetem Rückfall
        # (Schwelle 0) — Wechsel zwischen den spezifischen und „beenden“ hängen nicht daran.
        for g in (False, True):
            ms = _mitte([w for w in spez if w["gegen_regel"] == g])
            if ms:
                kandidaten.append((ms[1], g, ms[0], 0.0))
    if kandidaten:
        _, g, s_s, s_r = max(kandidaten)
        wahl = {"s_spez": s_s, "s_rueck": s_r, "gegen_regel": g}
        k5 = [bewerte_k5(im_assi, art, s_s, s_r, g, m, b) for m in RASTER_MARGE for b in RASTER_BEENDEN]

    kopf = {"lauf": args.lauf, "datum": datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y, %H:%M"),
            "modell": settings.embedding_model,
            "assistenten": {n: {"id": i["id"], "n": i["n"]} for n, i in info.items()}}
    text = bericht(kopf, faelle, im_assi, spez, rueck, k5, wahl, namen, fast_dubletten)
    if args.ziel:
        args.ziel.mkdir(parents=True, exist_ok=True)
        (args.ziel / f"vorschlag-{args.lauf}.md").write_text(text, encoding="utf-8")
        roh = {"kopf": kopf, "wahl": wahl,
               "faelle": [{k: v for k, v in f.items() if k != "abstaende"} | {
                   "abstaende": {n: [a.bsp, a.gegen if a.gegen != float("inf") else None]
                                 for n, a in f["abstaende"].items()}} for f in faelle + im_assi]}
        (args.ziel / f"vorschlag-{args.lauf}.json").write_text(json.dumps(roh, ensure_ascii=False, indent=1),
                                                                encoding="utf-8")
        print(f"Protokoll: {args.ziel / f'vorschlag-{args.lauf}.md'}")
    else:
        print(text)


def main() -> None:
    p = argparse.ArgumentParser(description="Vorlauf-Messung Assistent vorschlagen (C1 Schritt 5)")
    p.add_argument("--lauf", default="1")
    p.add_argument("--ziel", type=Path, default=None)
    args = p.parse_args()
    from app.config import settings
    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz.")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
