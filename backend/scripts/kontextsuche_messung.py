#!/usr/bin/env python3
"""Nutzt ein Modell die Kontextsuche? Vergleich mehrerer Modell-Aliasse (Mistral-Testphase, 17.11.2026).

    python scripts/kontextsuche_messung.py --modelle chat-standard chat-standard-ionos-pausiert \\
        chat-komplex chat-komplex-ionos-pausiert --laeufe 4 --verlauf ergebnis.md

Hintergrund: gpt-oss-120b rief die Kontextsuche mit `reasoning_effort: low` nur in 4 von 16
Fällen auf, mit `high` in 15 von 16 (Messung 26.09.2026, Kommentar in `litellm_config`). Mistral
denkt nicht — ob es trotzdem sucht, misst dieses Skript an denselben Fragen
(`szenarien/ap7_chemie.txt`) und demselben Assistenten (Chemie, Prompt mit Such-Anweisung).

Je Modell, Frage und Lauf eine neue Konversation als Schüler:in (Messkonto wie
`assistent_messung.py`). Gezählt: Aufrufe der Such-Funktionen (`context_search`,
`list_context_nodes`, `get_context_node`), Angebot der Vorab-Suche, ein Stichwort der richtigen
Antwort (grob — zum Lesen steht die Antwort im Verlauf), Antwortzeit, Kosten. Die Konversationen
werden danach gelöscht. Nur auf Dev.
"""
from __future__ import annotations

import argparse
import re
import statistics
import sys
import time
from pathlib import Path

import httpx

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import chat_probe  # noqa: E402
from app.auth.dependencies import get_jwt_service  # noqa: E402
from app.config import settings  # noqa: E402

SUCHE = {"context_search", "list_context_nodes", "get_context_node"}

#: Stichwort der richtigen Antwort je Frage (Anfang der Frage → Muster). Grob; entscheidend ist
#: die Flammen-Frage — GHS02 steht im Knoten, nicht im Modell (Messung 26.09.2026).
STICHWORT = {
    "Was ist eine Oxidation": r"Sauerstoff|Elektronen",
    "Beim Sieden zerfällt": r"\b(nein|nicht|kein)\b.*(verdampf|Wasserdampf|gasförmig)|(verdampf|Wasserdampf).*\b(nicht|kein)",
    "Ist Salzsäure": r"\bja\b|ist eine (starke )?Säure",
    "Was bedeutet das Zeichen mit der Flamme": r"entzündbar|entflammbar|GHS\s?0?2",
    "Wie viel Gramm Magnesiumoxid": r"\b40(,0)?\s?g",
    "Wie heißt die Bindung": r"polare? (Atom|Elektronenpaar)bindung|kovalent",
}


def stichwort(frage: str) -> str | None:
    return next((m for anfang, m in STICHWORT.items() if frage.startswith(anfang)), None)


def _sek(t):
    return "—" if t is None else f"{t:.1f} s"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--modelle", nargs="+", required=True)
    p.add_argument("--laeufe", type=int, default=4)
    p.add_argument("--assistent", type=int, default=8)
    p.add_argument("--stufe", default="9")
    p.add_argument("--datei", type=Path, default=HIER / "szenarien" / "ap7_chemie.txt")
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--konto", default="", help="Pseudonym-Anfang des Schüler:innen-Kontos")
    p.add_argument("--gruppe", type=int, default=37,
                   help="Unterrichtsgruppe der Konversation; das Konto wird unter ihren Schüler:innen "
                        "gewählt (Assistent 8 ist für Gruppe 37 freigegeben, wie in AP7)")
    p.add_argument("--pause", type=float, default=1.0, help="Sekunden zwischen Anfragen (Drossel)")
    p.add_argument("--verlauf", type=Path, default=None)
    args = p.parse_args()
    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz.")

    fragen = [z.strip() for z in args.datei.read_text(encoding="utf-8").splitlines()
              if z.strip() and not z.startswith("#")]
    import psycopg2

    conn = psycopg2.connect(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT pa.pseudonym FROM pseudonym_audit pa "
                    + ("JOIN group_memberships gm ON gm.pseudonym = pa.pseudonym AND gm.group_id = %s "
                       if args.gruppe else "")
                    + "WHERE pa.roles::text LIKE '%%student%%' AND pa.litellm_key IS NOT NULL "
                      "AND pa.pseudonym LIKE %s ORDER BY pa.created_at LIMIT 1",
                    ((args.gruppe,) if args.gruppe else ()) + (args.konto + "%",))
        zeile = cur.fetchone()
    if not zeile:
        raise SystemExit("Kein Schüler:innen-Konto mit LiteLLM-Schlüssel gefunden.")
    schueler = zeile[0]
    token = get_jwt_service().issue(pseudonym=schueler, roles=["student"], grade=args.stufe)[0]

    ergebnisse: list[dict] = []
    with httpx.Client(base_url=args.basis, timeout=300.0, headers={"Cookie": f"session={token}"}) as client:
        for modell in args.modelle:
            for frage in fragen:
                for lauf in range(1, args.laeufe + 1):
                    try:
                        time.sleep(args.pause)
                        e = chat_probe.frage_stellen(client, frage, assistent=args.assistent,
                                                     gruppe=args.gruppe, modell=modell)
                    except (httpx.HTTPError, SystemExit) as f:
                        ergebnisse.append({"modell": modell, "frage": frage, "lauf": lauf, "abbruch": str(f)[:200]})
                        print(f"{modell:30} {frage[:40]:40} {lauf}  ✗ {str(f)[:80]}", flush=True)
                        continue
                    such = [w.get("tool") for w in e["werkzeuge"] if w.get("tool") in SUCHE]
                    muster = stichwort(frage)
                    treffer = bool(muster and re.search(muster, e["antwort"], re.I | re.S))
                    angebot = len((e.get("vorab_debug") or {}).get("angebot") or [])
                    ergebnisse.append({"modell": modell, "frage": frage, "lauf": lauf, "suche": len(such),
                                       "angebot": angebot, "treffer": treffer, "antwort": e["antwort"],
                                       "t_ende": e.get("t_ende"), "konversation": e["konversation"],
                                       "modell_genutzt": e["modell"]})
                    print(f"{modell:30} {frage[:40]:40} {lauf}  Suche {len(such)} · Angebot {angebot} · "
                          f"{'✓' if treffer else '✗'} · {_sek(e.get('t_ende'))}", flush=True)

    # Kosten (das Backend trägt sie im Hintergrund nach), dann aufräumen.
    ids = [r["konversation"] for r in ergebnisse if r.get("konversation")]
    ende = time.monotonic() + 60
    while True:
        with conn.cursor() as cur:
            cur.execute("SELECT conversation_id::text, cost_usd, cost_status FROM messages WHERE role = 'assistant' "
                        "AND conversation_id::text = ANY(%s)", (ids,))
            kosten = cur.fetchall()
        if not any(k[2] == "ausstehend" for k in kosten) or time.monotonic() > ende:
            break
        time.sleep(2)
    je_konv = {}
    for kid, usd, _ in kosten:
        je_konv[kid] = je_konv.get(kid, 0.0) + float(usd or 0)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE id::text = ANY(%s) AND pseudonym = %s", (ids, schueler))

    zeilen = ["# Kontextsuche je Modell", "",
              f"Assistent {args.assistent}, Stufe {args.stufe}, {len(fragen)} Fragen × {args.laeufe} Läufe "
              f"(`{args.datei.name}`). „Suche“ = Antworten mit mindestens einem Aufruf von "
              f"{', '.join(sorted(SUCHE))}; „Stichwort“ grob, die Antworten stehen darunter.", "",
              "| Modell | Antworten | mit Suche | Stichwort | Flamme: Suche · Stichwort | fertig (Median) | Kosten |",
              "|---|---|---|---|---|---|---|"]
    for modell in args.modelle:
        r = [x for x in ergebnisse if x["modell"] == modell and "abbruch" not in x]
        flamme = [x for x in r if x["frage"].startswith("Was bedeutet das Zeichen mit der Flamme")]
        zeiten = [x["t_ende"] for x in r if x.get("t_ende") is not None]
        usd = sum(je_konv.get(x["konversation"], 0.0) for x in r)
        zeilen.append(f"| {modell} | {len(r)} | {sum(1 for x in r if x['suche'])}/{len(r)} | "
                      f"{sum(x['treffer'] for x in r)}/{len(r)} | {sum(1 for x in flamme if x['suche'])}/{len(flamme)} · "
                      f"{sum(x['treffer'] for x in flamme)}/{len(flamme)} | "
                      f"{_sek(statistics.median(zeiten)) if zeiten else '—'} | {usd:.4f} $ |")
    zeilen += ["", "## Je Frage", "", "| Frage | " + " | ".join(args.modelle) + " |",
               "|---|" + "---|" * len(args.modelle)]
    for frage in fragen:
        zellen = []
        for modell in args.modelle:
            r = [x for x in ergebnisse if x["modell"] == modell and x["frage"] == frage and "abbruch" not in x]
            zellen.append(f"Suche {sum(1 for x in r if x['suche'])}/{len(r)} · ✓ {sum(x['treffer'] for x in r)}/{len(r)}")
        zeilen.append(f"| {frage[:50]} | " + " | ".join(zellen) + " |")
    zeilen += ["", "## Antworten", ""]
    for x in ergebnisse:
        zeilen.append(f"### {x['modell']} · {x['frage'][:60]} · Lauf {x['lauf']}")
        if "abbruch" in x:
            zeilen += ["", f"Abbruch: {x['abbruch']}", ""]
            continue
        zeilen += ["", f"Suche {x['suche']} · Angebot {x['angebot']} · Stichwort {'✓' if x['treffer'] else '✗'} · "
                       f"{_sek(x.get('t_ende'))} · `{x.get('modell_genutzt')}`", ""]
        zeilen += [("> " + z) if z else ">" for z in (x["antwort"] or "*(leer)*").splitlines()] + [""]
    text = "\n".join(zeilen) + "\n"
    if args.verlauf:
        args.verlauf.write_text(text, encoding="utf-8")
    print("\n".join(zeilen[:12 + len(args.modelle) + len(fragen) + 4]))


if __name__ == "__main__":
    main()
