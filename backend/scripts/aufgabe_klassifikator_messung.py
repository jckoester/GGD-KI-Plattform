#!/usr/bin/env python3
"""Offline-Messung: Aufgaben-Klassifikator für den freien Schüler-Chat (Plan „Freier Schüler-Chat
Lösungsvorgriff“, Schritt 7a, 24.11.2026).

    cd backend && venv/bin/python scripts/aufgabe_klassifikator_messung.py \\
        --modell system-vorschlag --modell chat-standard --lauf 1 \\
        --ziel "<Vault>/Plaene/Messungen-Rollenbehauptung"

**Frage:** Erkennt ein kleines System-Modell je Schüler-Zug, ob an einer Aufgabe gearbeitet wird
(→ Large) oder nicht (→ Small)? Gemessen wird nur der Klassifikator, ohne Chat-Läufe: Die Züge
kommen aus vorhandenen Verläufen (mit der echten Antwort davor) und aus neuen Fällen
(`scripts/szenarien/aufgabe_klassifikator.yaml`).

**Was der Klassifikator sieht** (zustandslos): neue Nachricht, erste Nachricht der Konversation,
letzte Antwort des Chats (gekürzt wie in C2).

**Ausgewertet** (Zielwerte Jan, 24.11.2026): Aufgabe erkannt ≥ 95 %, in Folgezügen 100 %;
Wissensfragen und Sonstiges bleiben ≥ 80 % bei Small; Dauer Median ≤ 1 s, höchstens 1,5 s.
Weiterleitung A (je Zug) und B (haftend ab der ersten erkannten Aufgabe) aus denselben Urteilen.

Nichts wird gespeichert. ⚠️ Nur Entwicklung — Kosten trägt das Systemkonto.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
HIER = Path(__file__).resolve().parent

# Text und Lesen des Urteils kommen aus dem Chat — gemessen wird, was dort läuft.
from app.chat.aufgabe import SYSTEM, kuerzen as _kuerzen, lies_urteil  # noqa: E402
from app.chat.aufgabe import nutzertext as _nutzertext  # noqa: E402

ZIEL_AUFGABE = 0.95
ZIEL_FOLGEZUG = 1.0
ZIEL_SMALL = 0.80
ZIEL_MEDIAN_S = 1.0
ZIEL_MAX_S = 1.5
#: Mit `--mit-vorigem` (ab Lauf 4): das vorige Urteil als Kontext, wie im Chat.
MIT_VORIGER = False




# ── Reine Funktionen (Unit-Test: tests/unit/test_aufgabe_klassifikator_messung.py) ────────────


def etikett_fuer(fall_id: str, zug: int, etiketten: dict, einzeln: dict) -> str | None:
    """Etikett eines Transkript-Zugs: Präfix der Kennung bis zum ersten „-“, Ausnahmen je Zug."""
    praefix = fall_id.split("-", 1)[0]
    return einzeln.get(f"{praefix}/{zug}") or etiketten.get(praefix)


def elemente_aus_transkript(daten: dict, quelle: str, etiketten: dict, einzeln: dict) -> list[dict]:
    """Ein Element je Schüler-Zug eines Verlaufs; Fälle ohne Etikett fallen weg."""
    elemente = []
    for fall in daten["faelle"]:
        zuege = fall.get("zuege") or []
        if not zuege:
            continue
        erste = zuege[0].get("schueler") or ""
        for i, z in enumerate(zuege, start=1):
            etikett = etikett_fuer(fall["id"], i, etiketten, einzeln)
            if etikett is None or not z.get("schueler"):
                continue
            elemente.append({
                "kennung": f"{quelle}:{fall['id']}/{i}", "konversation": f"{quelle}:{fall['id']}", "zug": i,
                "art": "transkript", "etikett": etikett, "nachricht": z["schueler"],
                "erste": erste if i > 1 else None,
                "letzte_antwort": _kuerzen(zuege[i - 2].get("antwort")) if i > 1 else None,
            })
    return elemente


def elemente_aus_faellen(faelle: list[dict]) -> list[dict]:
    """Neue Fälle; mit `erste` wird die erste Nachricht als eigener Zug (Art „vorlauf“) mitgemessen."""
    elemente = []
    for f in faelle:
        konv = f"neu:{f['id']}"
        if f.get("erste"):
            elemente.append({"kennung": f"{konv}/1", "konversation": konv, "zug": 1, "art": "vorlauf",
                             "etikett": f.get("erste_etikett", "aufgabe"), "nachricht": f["erste"], "erste": None,
                             "letzte_antwort": None})
        elemente.append({"kennung": f"{konv}/{2 if f.get('erste') else 1}", "konversation": konv,
                         "zug": 2 if f.get("erste") else 1, "art": f["art"], "etikett": f["etikett"],
                         "nachricht": f["nachricht"], "erste": f.get("erste"),
                         "letzte_antwort": _kuerzen(f.get("letzte_antwort"))})
    return elemente


def nutzertext(e: dict) -> str:
    return _nutzertext(e["nachricht"], e.get("erste"), e.get("letzte_antwort"), bool(e.get("vorige_aufgabe")))


def vorige_setzen(elemente: list[dict]) -> list[dict]:
    """``vorige_aufgabe`` je Folgezug aus dem **Etikett** des vorigen Zugs derselben Konversation —
    so, als hätte der Klassifikator dort richtig geurteilt (im Chat: die vorige Antwort kam vom
    Zielmodell)."""
    vorher: dict[str, dict] = {}
    for e in sorted(elemente, key=lambda x: (x["konversation"], x["zug"])):
        v = vorher.get(e["konversation"])
        e["vorige_aufgabe"] = bool(v and v["zug"] == e["zug"] - 1 and v["etikett"] == "aufgabe")
        vorher[e["konversation"]] = e
    return elemente


def mehrheit(urteile: list[bool | None]) -> bool | None:
    """Mehrheit der lesbaren Urteile; Gleichstand zählt als Aufgabe (der billigere Fehler)."""
    gueltig = [u for u in urteile if u is not None]
    if not gueltig:
        return None
    return sum(gueltig) * 2 >= len(gueltig)


def zur_large(urteil: bool | None) -> bool:
    """Ohne lesbares Urteil wie „Aufgabe“: Im Zweifel Large (der billigere Fehler)."""
    return urteil is not False


def auswerten(elemente: list[dict]) -> dict:
    """Quoten je Aufruf (alle Wiederholungen) und Weiterleitung A/B je Konversation (Mehrheit)."""
    def quote(auswahl, soll_large: bool):
        aufrufe = [u for e in auswahl for u in e["urteile"]]
        treffer = sum(zur_large(u) == soll_large for u in aufrufe)
        return treffer, len(aufrufe)

    aufgabe = [e for e in elemente if e["etikett"] == "aufgabe"]
    erste = [e for e in aufgabe if e["zug"] == 1]
    folge = [e for e in aufgabe if e["zug"] > 1]
    small = [e for e in elemente if e["etikett"] in ("wissensfrage", "sonst")]
    stabil = [e for e in elemente if len(set(e["urteile"])) == 1]

    fehler_aufgabe = sorted({e["kennung"] for e in aufgabe if not all(zur_large(u) for u in e["urteile"])})
    fehler_small = sorted({e["kennung"] for e in small if any(zur_large(u) for u in e["urteile"])})

    # Weiterleitung je Konversation, nach Mehrheitsurteil je Zug.
    konv: dict[str, list[dict]] = {}
    for e in elemente:
        konv.setdefault(e["konversation"], []).append(e)
    a_large = b_large = gesamt = 0
    b_vorgriff, a_vorgriff = [], []
    for zuege in konv.values():
        haftet = False
        for e in sorted(zuege, key=lambda z: z["zug"]):
            m = zur_large(mehrheit(e["urteile"]))
            haftet = haftet or m
            gesamt += 1
            a_large += m
            b_large += haftet
            if e["etikett"] == "aufgabe" and not m:
                a_vorgriff.append(e["kennung"])
            if e["etikett"] == "aufgabe" and not haftet:
                b_vorgriff.append(e["kennung"])
    return {
        "aufgabe": quote(aufgabe, True), "erste": quote(erste, True), "folge": quote(folge, True),
        "small": quote(small, False),
        "stabil": (len(stabil), len(elemente)),
        "fehler_aufgabe": fehler_aufgabe, "fehler_small": fehler_small,
        "A": {"large": a_large, "gesamt": gesamt, "aufgabe_verfehlt": a_vorgriff},
        "B": {"large": b_large, "gesamt": gesamt, "aufgabe_verfehlt": b_vorgriff},
    }


def nach_art(elemente: list[dict]) -> dict[str, tuple[int, int]]:
    """Je Art: Aufrufe mit dem richtigen Ziel (Large bei Aufgabe, sonst Small)."""
    aus: dict[str, list[int]] = {}
    for e in elemente:
        if e["etikett"] == "beobachtet":
            continue
        soll = e["etikett"] == "aufgabe"
        a = aus.setdefault(e["art"], [0, 0])
        for u in e["urteile"]:
            a[0] += zur_large(u) == soll
            a[1] += 1
    return {k: (v[0], v[1]) for k, v in aus.items()}


# ── Modellaufruf ─────────────────────────────────────────────────────────────


async def klassifiziere(client, modell: str, e: dict) -> dict:
    import httpx

    from app.config import settings
    from app.litellm import systemkonto
    from app.litellm.systemkonto import kosten_aus_antwort

    rumpf = {"model": modell, "temperature": 0, "max_tokens": 300, "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": nutzertext(e)},
    ]}
    beginn = time.monotonic()
    for _ in (1, 2):                    # ein zweiter Versuch bei 5xx (Anbieter)
        try:
            antwort = await client.post(f"{settings.litellm_proxy_url}/chat/completions", json=rumpf,
                                        headers={"Authorization": f"Bearer {systemkonto.schluessel()}"})
        except httpx.HTTPError as fehler:
            return {"roh": "", "dauer": time.monotonic() - beginn, "usd": None, "fehler": type(fehler).__name__}
        if antwort.status_code < 500:
            break
    dauer = time.monotonic() - beginn
    if antwort.status_code != 200:
        return {"roh": "", "dauer": dauer, "usd": None, "fehler": f"HTTP {antwort.status_code}: {antwort.text[:160]}"}
    await systemkonto.verbuche(antwort)
    daten = antwort.json()
    return {"roh": daten["choices"][0]["message"].get("content") or "", "dauer": dauer,
            "usd": kosten_aus_antwort(antwort)}


# ── Bericht ──────────────────────────────────────────────────────────────────


def _pz(t: int, n: int) -> str:
    return f"{t} von {n} ({round(100 * t / n)} %)" if n else "—"


def _median_p90(werte: list[float]) -> tuple[float, float] | None:
    w = sorted(werte)
    return (statistics.median(w), w[int(0.9 * (len(w) - 1))]) if w else None


def _zeilen_suche(aufrufe: list[dict]) -> list[str]:
    """Mit `--mit-suche`: Dauer der Vorab-Suche und was der Klassifikator darüber hinaus braucht."""
    paare = [(a["dauer"], a["suche"]) for a in aufrufe if not a.get("fehler") and a.get("suche") is not None]
    if not paare:
        return []
    s = _median_p90([su for _, su in paare])
    m = _median_p90([max(0.0, k - su) for k, su in paare])
    f = lambda mp: f"{mp[0]:.2f} s / {mp[1]:.2f} s".replace(".", ",")
    return [f"| Vorab-Suche, gleichzeitig, Median / 90 % | | {f(s)} | |",
            f"| Mehrwartezeit (Klassifikator länger als Suche) Median / 90 % | ≤ 1 s, höchstens 1,5 s | {f(m)} | "
            f"{'✓' if m[0] <= ZIEL_MEDIAN_S and m[1] <= ZIEL_MAX_S else '✗'} |"]


def bericht_modell(modell: str, elemente: list[dict], aufrufe: list[dict]) -> list[str]:
    r = auswerten(elemente)
    dauern = sorted(a["dauer"] for a in aufrufe if not a.get("fehler"))
    kosten = [a["usd"] for a in aufrufe if a.get("usd") is not None]
    fehler = [a["fehler"] for a in aufrufe if a.get("fehler")]
    unlesbar = sum(1 for a in aufrufe if not a.get("fehler") and lies_urteil(a["roh"]) is None)
    median = statistics.median(dauern) if dauern else None
    p90 = dauern[int(0.9 * (len(dauern) - 1))] if dauern else None

    def ok(t_n, ziel):
        t, n = t_n
        return "✓" if n and t / n >= ziel else "✗"

    t = [f"## `{modell}`", "",
         "| Größe | Ziel | Ergebnis | |", "|---|---|---|---|",
         f"| Aufgabe erkannt, alle Züge | ≥ 95 % | {_pz(*r['aufgabe'])} | {ok(r['aufgabe'], ZIEL_AUFGABE)} |",
         f"| davon erster Zug | | {_pz(*r['erste'])} | |",
         f"| davon Folgezüge (Nachhaken, Antwort auf Rückfrage) | 100 % | {_pz(*r['folge'])} | {ok(r['folge'], ZIEL_FOLGEZUG)} |",
         f"| Wissensfrage/Sonstiges bleibt bei Small | ≥ 80 % | {_pz(*r['small'])} | {ok(r['small'], ZIEL_SMALL)} |",
         f"| Dauer Median / 90 % | ≤ 1 s, höchstens 1,5 s | "
         + (f"{median:.2f} s / {p90:.2f} s".replace(".", ",") if median is not None else "—")
         + f" | {'✓' if median is not None and median <= ZIEL_MEDIAN_S and p90 <= ZIEL_MAX_S else '✗'} |",
         *_zeilen_suche(aufrufe),
         f"| gleiches Urteil in allen Wiederholungen | | {_pz(*r['stabil'])} | |",
         f"| Kosten je Aufruf | | {(statistics.mean(kosten) if kosten else 0):.6f} USD | |".replace("0.", "0,", 1),
         f"| Fehler / unlesbar | | {len(fehler)} / {unlesbar} | |", "",
         "**Je Art** (Aufrufe mit richtigem Ziel): "
         + "; ".join(f"{a} {_pz(*tn)}" for a, tn in nach_art(elemente).items()), "",
         f"**Weiterleitung A (je Zug):** {_pz(r['A']['large'], r['A']['gesamt'])} der Züge bei Large; "
         f"Aufgabe verfehlt (Mehrheit): {', '.join(r['A']['aufgabe_verfehlt']) or '—'}", "",
         f"**Weiterleitung B (haftend):** {_pz(r['B']['large'], r['B']['gesamt'])} der Züge bei Large; "
         f"Aufgabe verfehlt (Mehrheit): {', '.join(r['B']['aufgabe_verfehlt']) or '—'}", "",
         f"**Aufgabe nicht in allen Wiederholungen erkannt:** {', '.join(r['fehler_aufgabe']) or '—'}", "",
         f"**Wissensfrage/Sonstiges mindestens einmal zu Large:** {', '.join(r['fehler_small']) or '—'}", ""]
    beob = [e for e in elemente if e["etikett"] == "beobachtet"]
    if beob:
        t.append("**Beobachtet** (zählt nicht): " + "; ".join(
            f"{e['kennung']} {''.join('A' if zur_large(u) else 's' for u in e['urteile'])}" for e in beob))
        t.append("")
    if fehler:
        t.append(f"⚠️ Fehler: {'; '.join(sorted(set(fehler)))[:500]}")
        t.append("")
    return t


# ── Lauf ─────────────────────────────────────────────────────────────────────


def pruefsatz(ziel: str) -> list[dict]:
    szenario = yaml.safe_load((HIER / "szenarien" / "aufgabe_klassifikator.yaml").read_text(encoding="utf-8"))
    tr = szenario["transkripte"]
    basis: list[dict] = []
    for datei in tr["dateien"]:
        daten = json.loads((Path(ziel) / datei).read_text(encoding="utf-8"))
        quelle = datei.removeprefix("verlauf-").removesuffix(".json")
        basis += elemente_aus_transkript(daten, quelle, tr["etiketten"], tr.get("einzeln") or {})
    basis = basis + elemente_aus_faellen(szenario["faelle"])
    return vorige_setzen(basis) if MIT_VORIGER else basis


async def _schuelerkonto() -> str:
    import sqlalchemy as sa

    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        return (await db.execute(sa.text(
            "SELECT pseudonym FROM pseudonym_audit WHERE roles::text LIKE '%student%' "
            "AND litellm_key IS NOT NULL ORDER BY created_at LIMIT 1"))).scalar_one()


async def _suche(pseudonym: str, nachricht: str) -> float:
    """Die Vorab-Suche wie im freien Chat (ohne Assistent, ohne Konversation) — nur lesend."""
    from app.context.service import kontext_fuer_frage
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        beginn = time.monotonic()
        await kontext_fuer_frage(assistant_id=None, pseudonym=pseudonym, query_text=nachricht, chat_id=None,
                                 db=db, rollen=["student"], jwt_stufe="8")
        return time.monotonic() - beginn


async def laufen(args) -> None:
    import httpx

    basis = pruefsatz(args.ziel)
    ergebnis = {}
    if args.aus:
        # Neu auswerten mit den Urteilen eines früheren Laufs (geänderte Etiketten, keine Aufrufe).
        alt = json.loads(Path(args.aus).read_text(encoding="utf-8"))["modelle"]
        for modell in args.modell:
            urteile = {e["kennung"]: (e["urteile"], e.get("roh")) for e in alt[modell]["elemente"]}
            elemente = [dict(e, urteile=urteile[e["kennung"]][0], roh=urteile[e["kennung"]][1]) for e in basis]
            ergebnis[modell] = (elemente, alt[modell]["aufrufe"])
        print(f"{len(basis)} Züge neu ausgewertet aus {args.aus}")
    else:
        print(f"{len(basis)} Züge × {args.wiederholungen} Wiederholungen × {len(args.modell)} Modelle"
              + (" mit Vorab-Suche" if args.mit_suche else ""))
        konto = await _schuelerkonto() if args.mit_suche else None
        sperre = asyncio.Semaphore(args.parallel)
        async with httpx.AsyncClient(timeout=60.0) as client:
            for modell in args.modell:
                elemente = [dict(e, urteile=[]) for e in basis]
                aufrufe: list[dict] = []

                async def eins(e):
                    async with sperre:
                        if konto:
                            # Gleichzeitig, wie es im Chat liefe: Klassifikator und Vorab-Suche.
                            a, suche = await asyncio.gather(klassifiziere(client, modell, e),
                                                            _suche(konto, e["nachricht"]))
                            a["suche"] = suche
                        else:
                            a = await klassifiziere(client, modell, e)
                    a["kennung"] = e["kennung"]
                    aufrufe.append(a)
                    e["urteile"].append(None if a.get("fehler") else lies_urteil(a["roh"]))
                    e.setdefault("roh", []).append(a["roh"])

                for _ in range(args.wiederholungen):
                    await asyncio.gather(*(eins(e) for e in elemente))
                ergebnis[modell] = (elemente, aufrufe)
                print(f"  {modell}: fertig")

    datum = datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")
    t = [f"# Aufgaben-Klassifikator, Lauf {args.lauf}", "",
         f"- **Datum:** {datum}",
         f"- **Prüfsatz:** `scripts/szenarien/aufgabe_klassifikator.yaml`, {len(basis)} Züge "
         f"({sum(e['etikett'] == 'aufgabe' for e in basis)} Aufgabe, "
         f"{sum(e['etikett'] in ('wissensfrage', 'sonst') for e in basis)} Wissensfrage/Sonstiges, "
         f"{sum(e['etikett'] == 'beobachtet' for e in basis)} beobachtet)",
         (f"- **Neu ausgewertet** aus `{Path(args.aus).name}` (Urteile und Dauern von dort, keine Aufrufe)"
          if args.aus else
          f"- **Wiederholungen:** {args.wiederholungen}, parallel {args.parallel}, Systemkonto, `temperature` 0"
          + ("; Vorab-Suche gleichzeitig zu jedem Aufruf (freier Chat, Klasse 8, nur lesend)"
             if args.mit_suche else "")
          + ("; Folgezüge mit dem vorigen Etikett als Kontext („Die vorige Nachricht war eine Aufgabe.“)"
             if MIT_VORIGER else "")),
         "- **Ohne lesbares Urteil** zählt wie „Aufgabe“ (Large).", ""]
    for modell, (elemente, aufrufe) in ergebnis.items():
        t += bericht_modell(modell, elemente, aufrufe)
    ziel = Path(args.ziel)
    (ziel / f"klassifikator-{args.lauf}.md").write_text("\n".join(t), encoding="utf-8")
    (ziel / f"klassifikator-{args.lauf}.json").write_text(json.dumps(
        {"system": SYSTEM, "modelle": {m: {"elemente": el, "aufrufe": au} for m, (el, au) in ergebnis.items()}},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Bericht: {ziel / f'klassifikator-{args.lauf}.md'}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--modell", action="append", required=True, help="mehrfach möglich")
    p.add_argument("--lauf", required=True)
    p.add_argument("--ziel", required=True, help="Ordner mit den Verläufen; dorthin geht auch der Bericht")
    p.add_argument("--wiederholungen", type=int, default=3)
    p.add_argument("--aus", default=None, help="JSON eines früheren Laufs neu auswerten, ohne Aufrufe")
    p.add_argument("--mit-suche", action="store_true",
                   help="Vorab-Suche gleichzeitig zu jedem Aufruf laufen lassen und ihre Dauer messen")
    p.add_argument("--parallel", type=int, default=2)
    p.add_argument("--mit-vorigem", action="store_true",
                   help="Folgezüge bekommen das Etikett des vorigen Zugs als Kontext (wie im Chat)")
    args = p.parse_args()
    global MIT_VORIGER
    MIT_VORIGER = args.mit_vorigem
    asyncio.run(laufen(args))


if __name__ == "__main__":
    main()
