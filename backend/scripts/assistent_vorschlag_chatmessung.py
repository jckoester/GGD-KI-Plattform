#!/usr/bin/env python3
"""Messung „Assistent vorschlagen“ im echten Chat (Päckchen C2, Schritt 7).

    cd backend && VORSCHLAG_MODEL=system-vorschlag venv/bin/uvicorn app.main:app --port 8001 &
    venv/bin/python scripts/assistent_vorschlag_chatmessung.py --basis http://localhost:8001 \\
        --konto <pseudonym-anfang> --ziel "<Vault>/Plaene/Messungen-Vorschlag" --lauf chat-1

Anders als `assistent_vorschlag_klassifikator.py` geht hier jede Nachricht **durch den Chat**:
Sichtbarkeit, Vorab-Vektor, Klassifikator, Zeitlimit und Ruheregel wirken wie im Betrieb. Gemessen:

- **K1–K4** an den Optionen des Ereignisses `vorschlag` (Prüfsatz `assistent_vorschlag.yaml`, `faelle`),
  je Fall eine neue Konversation im freien Chat, als Schüler:in der Stufe des Falls.
- **K5** an `in_assistent`: neue Konversation mit dem aktuellen Assistenten; erwartet bleiben,
  wechsel (zu `wechsel_zu`) oder beenden.
- **K6** rechtzeitig: Anteil der Fälle mit Klassifikator-Aufruf, in denen der Vorschlag nicht am
  Zeitlimit scheiterte; dazu die Verzögerung nach dem Ende der Antwort (`message`).
- **K7** Kosten: Zuwachs von `system_spend` heute während des Laufs (enthält auch die Einbettungen
  der Vorab-Suche — eine Obergrenze), je Nachricht.

Konversationen werden danach gelöscht. ⚠️ Nur Entwicklung — echtes Budget des Schüler:innen-Kontos.
"""
import argparse
import importlib.util
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HIER = Path(__file__).resolve().parent


def _lade(name: str):
    spec = importlib.util.spec_from_file_location(name, HIER / f"{name}.py")
    modul = importlib.util.module_from_spec(spec)
    sys.modules[name] = modul
    spec.loader.exec_module(modul)
    return modul


def ergebnis_im_assistenten(optionen: list[dict] | None, namen: dict[int, str]) -> tuple[str, str | None]:
    """Was der Dialog in der Assistenten-Konversation anbot: bleiben, wechsel (zu wem), beenden."""
    if not optionen:
        return "bleiben", None
    if any(o["art"] == "beenden" for o in optionen):
        return "beenden", None
    return "wechsel", namen.get(optionen[0]["assistant_id"], str(optionen[0]["assistant_id"]))


def verweist(antwort: str, name: str) -> bool:
    """K9: Der erste Satz der Antwort nennt den Assistenten ``name``."""
    import re
    erster = re.split(r"(?<=[.!?])\s", antwort.strip(), maxsplit=1)[0].lower()
    return name.lower() in erster


def rechtzeitig(faelle: list[dict]) -> dict:
    """K6: Unter den Fällen mit Klassifikator-Aufruf (oder K5-Entscheidung) — wie viele
    scheiterten am Zeitlimit, und wie lange kam ein Vorschlag nach der Antwort?"""
    mit = [f for f in faelle if f.get("debug") and ("klassifikator" in f["debug"] or "abgebrochen" in f["debug"])]
    zeitlimit = [f for f in mit if (f["debug"] or {}).get("abgebrochen") == "Zeitlimit"]
    nach = [f["t_vorschlag"] - f["t_message"] for f in faelle
            if f.get("t_vorschlag") is not None and f.get("t_message") is not None]
    return {"aufrufe": len(mit), "zeitlimit": len(zeitlimit),
            "anteil_rechtzeitig": (len(mit) - len(zeitlimit)) / len(mit) if mit else None,
            "nach_antwort": sorted(round(x, 2) for x in nach)}


def main() -> None:
    p = argparse.ArgumentParser(description="Assistent vorschlagen — Messung im echten Chat (C2 Schritt 7)")
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--konto", required=True, help="Pseudonym-Anfang eines Schüler:innen-Kontos")
    p.add_argument("--modell", default="chat-standard", help="Modell des freien Chats")
    p.add_argument("--lauf", default="chat-1")
    p.add_argument("--ziel", type=Path, required=True)
    args = p.parse_args()

    from app.auth.dependencies import get_jwt_service
    from app.config import settings
    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz.")
    chat_probe = _lade("chat_probe")
    entfall = _lade("entfall_messung")
    k = _lade("assistent_vorschlag_klassifikator")
    satz = yaml.safe_load((HIER / "szenarien/assistent_vorschlag.yaml").read_text(encoding="utf-8"))
    conn = entfall.verbindung()
    pseudonym = entfall._alle(conn, "SELECT pseudonym FROM pseudonym_audit WHERE pseudonym LIKE %s LIMIT 1",
                              args.konto + "%")[0][0]
    namen = {i: n for i, n in entfall._alle(conn, "SELECT id, name FROM assistants")}
    ids = {n: i for i, n in namen.items()}
    art = {n: s for n, s in entfall._alle(conn, "SELECT name, suggest FROM assistants")}
    vorher = entfall._eins(conn, "SELECT coalesce(sum(kosten_usd), 0) FROM system_spend WHERE tag = current_date") or 0

    faelle, im_assi, konversationen, abbrueche = [], [], [], []
    with httpx.Client(base_url=args.basis, timeout=300.0) as client:
        def fragen(text, stufe, assistent=None, vorher=None):
            token, _ = get_jwt_service().issue(pseudonym=pseudonym, roles=["student"], grade=str(stufe))
            client.cookies.set("session", token)
            # C4 (0.26): mitten im Gespräch — die letzte Antwort des Assistenten als Verlauf.
            verlauf = ([{"role": "user", "content": "(vorige Nachricht)"},
                        {"role": "assistant", "content": vorher}] if vorher else None)
            r = chat_probe.frage_stellen(client, text, assistent=assistent, gruppe=None,
                                         modell=None if assistent else args.modell, verlauf=verlauf)
            konversationen.append(r["konversation"])
            return r
        def sicher(*a, **kw):
            # Ein hängender Fall (ReadTimeout nach 300 s, 29.10.2026) soll nicht den ganzen Lauf
            # kosten: Er wird als Fehler protokolliert, und es geht weiter.
            try:
                return fragen(*a, **kw)
            except httpx.HTTPError as e:
                print(f"  ⚠️ {type(e).__name__}: {a[0][:60]}", flush=True)
                abbrueche.append(f"{type(e).__name__}: {a[0][:60]}")
                return {"vorschlag": None, "vorab_debug": None, "konversation": None,
                        "t_message": None, "t_vorschlag": None, "t_ende": None}

        for f in satz["faelle"]:
            text = k.C1.text_des_falls(f)
            r = sicher(text, f["stufe"])
            faelle.append({**f, "kennung": f.get("quelle", f.get("text", ""))[:45], "text": text,
                           "soll": f.get("soll") or [], "nicht": f.get("nicht") or [],
                           "gewaehlt": [namen.get(o["assistant_id"], "?") for o in r["vorschlag"] or []
                                        if o["art"] != "beenden"],
                           "debug": (r["vorab_debug"] or {}).get("vorschlag"),
                           **{x: r[x] for x in ("t_message", "t_vorschlag", "t_ende")}})
            print(f"{faelle[-1]['kennung'][:40]:<41} {f['art']:<9} → {', '.join(faelle[-1]['gewaehlt']) or '—'}", flush=True)
        for f in satz["in_assistent"]:
            r = sicher(f["text"], f["stufe"], assistent=ids[f["aktuell"]], vorher=f.get("vorher"))
            ergebnis, ziel = ergebnis_im_assistenten(r["vorschlag"], namen)
            # K9 (C5): Verweist die Antwort im ersten Satz auf den anderen Rückfall-Assistenten?
            if f.get("verweis_auf"):
                f = {**f, "k9": verweist(r.get("antwort") or "", f["verweis_auf"]),
                     "antwort_anfang": (r.get("antwort") or "").strip()[:160]}
            # `darf` (K5-neu): ein Dialog, der nicht verlangt, aber vertretbar ist (etwa „beenden“).
            richtig = ((ergebnis == f["erwartet"] and (ergebnis != "wechsel" or ziel == f.get("wechsel_zu")))
                       or ergebnis in (f.get("darf") or []))
            im_assi.append({**f, "ergebnis": ergebnis, "ziel": ziel, "richtig": richtig,
                            "debug": (r["vorab_debug"] or {}).get("vorschlag"),
                            **{x: r[x] for x in ("t_message", "t_vorschlag", "t_ende")}})
            print(f"{f['text'][:40]:<41} {f['erwartet']:<8} → {ergebnis}{' ' + ziel if ziel else ''}"
                  f"{'' if richtig else '  ✗'}", flush=True)

    nachher = entfall._eins(conn, "SELECT coalesce(sum(kosten_usd), 0) FROM system_spend WHERE tag = current_date") or 0
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE id::text = ANY(%s) AND pseudonym = %s",
                    ([str(x) for x in konversationen if x], pseudonym))
    conn.commit()
    conn.close()

    kk = k.bewerte(faelle, {n: art[n] for n in satz["assistenten"]["spezifisch"] + satz["assistenten"]["rueckfall"]})
    k5_fehler = {a: [f["text"][:40] for f in im_assi if f["erwartet"] == a and not f["richtig"]]
                 for a in ("bleiben", "wechsel", "beenden")}
    k6 = rechtzeitig(faelle + im_assi)
    n = len(faelle) + len(im_assi)
    kosten = float(nachher) - float(vorher)
    t = [f"# Assistent vorschlagen — Messung im Chat, Lauf {args.lauf}", "",
         f"- **Datum:** {datetime.now(timezone.utc).astimezone().strftime('%d.%m.%Y, %H:%M')}",
         f"- **Klassifikator:** `{settings.vorschlag_model or '(leer!)'}` · freier Chat: `{args.modell}`",
         f"- **Prüfsatz:** {len(faelle)} Fälle im freien Chat, {len(im_assi)} in Assistenten-Konversationen", "",
         "## Ergebnis", ""]
    t += [f"- **{x}:** {'✓' if kk[x] else '✗'}" for x in ("K1", "K2", "K3", "K4")]
    if abbrueche:
        t.append(f"- ⚠️ **Abgebrochene Fälle:** {len(abbrueche)} — " + "; ".join(abbrueche))
    k9 = [f for f in im_assi if "k9" in f]
    if k9:
        t.append(f"- **K9 (Rückfall → Rückfall, Verweis im ersten Satz):** "
                 f"{sum(f['k9'] for f in k9)}/{len(k9)} — "
                 + "; ".join(f"{f['text'][:30]} → {f['verweis_auf']}: {'✓' if f['k9'] else '✗'} "
                             f"(„{f.get('antwort_anfang', '')[:80]}…“)" for f in k9))
    t.append(f"- **K8 (Nachbarpaare, richtiger zuerst):** {'✓' if kk['K8'] else '✗'} — "
             f"{kk['k8_paare'] - len(kk['k8_fehl'])}/{kk['k8_paare']}"
             + (f"; daneben: {', '.join(kk['k8_fehl'])}" if kk["k8_fehl"] else ""))
    t.append("- **Positive im Dialog:** " + "; ".join(f"{a} {x}/{g}" for a, (x, g) in kk["positiv"].items()))
    t.append("- **Nachbar-Fehltreffer:** " + "; ".join(f"{a} {x}/{g}" for a, (x, g) in kk["nachbar"].items()))
    t.append(f"- **Begriff/Alltag mit Dialog:** {', '.join(kk['stoer']) or '—'}")
    t.append(f"- **K5 (je Art höchstens ein Fehler):** {'✓' if all(len(v) <= 1 for v in k5_fehler.values()) else '✗'} — "
             + "; ".join(f"{a}: {', '.join(v) or '—'}" for a, v in k5_fehler.items()))
    if k6["aufrufe"]:
        t.append(f"- **K6 rechtzeitig:** {k6['aufrufe'] - k6['zeitlimit']} von {k6['aufrufe']} "
                 f"({k6['anteil_rechtzeitig']:.0%}; Ziel ≥ 90 %); Vorschlag nach dem Ende der Antwort: "
                 + (f"Median {statistics.median(k6['nach_antwort']):.1f} s, längster {max(k6['nach_antwort']):.1f} s"
                    if k6["nach_antwort"] else "—"))
    t.append(f"- **K7 Kosten Systemkonto:** {kosten:.5f} je Lauf, {kosten / n:.5f} je Nachricht (Ziel ≤ 0,0005; "
             "mit Einbettungen, also Obergrenze)")
    t += ["", "## Je Fall (freier Chat)", "", "| Fall | Art | Kl. | soll | Dialog | Debug |", "|---|---|---|---|---|---|"]
    for f in faelle:
        t.append(f"| {f['kennung']} | {f['art']} | {f['stufe']} | {', '.join(f['soll']) or '—'} | "
                 f"{', '.join(f['gewaehlt']) or '—'} | {json.dumps(f['debug'], ensure_ascii=False)[:160] if f['debug'] else '—'} |")
    t += ["", "## In der Assistenten-Konversation", "", "| Nachricht | aktuell | erwartet | Dialog | ok |", "|---|---|---|---|---|"]
    for f in im_assi:
        t.append(f"| {f['text'][:50]} | {f['aktuell']} | {f['erwartet']}{' → ' + f['wechsel_zu'] if f.get('wechsel_zu') else ''}"
                 f" | {f['ergebnis']}{' → ' + f['ziel'] if f['ziel'] else ''} | {'✓' if f['richtig'] else '✗'} |")
    args.ziel.mkdir(parents=True, exist_ok=True)
    (args.ziel / f"vorschlag-{args.lauf}.md").write_text("\n".join(t) + "\n", encoding="utf-8")
    print(f"Protokoll: {args.ziel / f'vorschlag-{args.lauf}.md'}")


if __name__ == "__main__":
    main()
