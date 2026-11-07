#!/usr/bin/env python3
"""Gegenprobe „Diagramme zeichnen“ auswerten (0.36, Plan Schritt 5).

    venv/bin/python scripts/diagramme_auswerten.py [--seite übersicht.html] <verlauf-*.json> …

Zieht ```mermaid, ```plot und ```circuitikz aus den Antworten der Protokolle von
`assistent_messung.py` (Szenarien `diagramme_zeichnen.yaml`) und prüft, ob sie sich zeichnen lassen:
Mermaid mit Pele roh und nach der Reparatur (`pele_pruefen.mjs`), Plot mit dem Plot-Renderer,
Schaltplan über den Render-Sidecar (muss laufen). Dazu bei Mermaid: LaTeX in Beschriftungen
(`\\(`, `\\ce`, `$`) und `style`-Zeilen — beides zeichnet Pele nicht so, wie gemeint.

`--seite` (0.37): eine HTML-Übersicht mit jedem gezeichneten Schaltplan bzw. Funktionsgraphen neben
Frage und Prüfkriterien (`muss`) und einem Kästchen „fachlich richtig“ — zum Abhaken von Hand.
Was nicht zeichnet, steht mit Fehlermeldung und Quelltext da.
"""
import argparse
import asyncio
import html
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

from app.render.plot import _render_sync, parse_plot_spec  # noqa: E402
from app.render.sidecar import render_circuit  # noqa: E402
from app.render.errors import RenderError  # noqa: E402

ZAUN = re.compile(r"```[ \t]*(mermaid|plot|circuitikz|circuittikz|circuit)[ \t]*\n(.*?)```", re.S | re.I)
LATEX = re.compile(r"\\\(|\\\[|\\ce\{|\\frac|\$[^$\n]+\$")


def bloecke(antwort: str):
    for art, quelle in ZAUN.findall(antwort or ""):
        art = art.lower()
        yield ("circuit" if art.startswith("circ") else art), quelle.strip()


def seite_schreiben(ziel: Path, eintraege: list[dict]) -> None:
    """Übersicht zum fachlichen Abhaken: je Eintrag Frage, Kriterien, Bild oder Fehler."""
    teile = ["<!doctype html><meta charset=utf-8><title>Diagramme — Übersicht</title><style>",
             "body{font-family:sans-serif;margin:1rem;max-width:1100px}"
             ".e{border-top:1px solid #ccc;padding:.6rem 0;display:grid;grid-template-columns:1fr 1.3fr;gap:1rem}"
             ".bild svg{max-width:100%;height:auto;background:#fff}"
             ".kaputt{color:#af3029}pre{font-size:.7rem;white-space:pre-wrap;background:#f2f0e5;padding:.4rem}"
             "</style>", f"<p>{len(eintraege)} Diagramme. Kästchen anklicken, wenn fachlich richtig.</p>"]
    for e in eintraege:
        kriterien = "".join(f"<li>{html.escape(k)}</li>" for k in e["muss"])
        bild = e["svg"] if e["svg"] else f"<p class=kaputt>{html.escape(e['befund'])}</p>"
        teile.append(
            f"<div class=e><div><b>{html.escape(e['lauf'])} · {html.escape(e['fall'])}</b><br>"
            f"<i>{html.escape(e['frage'])}</i><ul>{kriterien}</ul>"
            f"<label><input type=checkbox> fachlich richtig</label>"
            f"<details><summary>Quelltext</summary><pre>{html.escape(e['quelle'])}</pre></details></div>"
            f"<div class=bild>{bild}</div></div>")
    ziel.write_text("\n".join(teile), encoding="utf-8")


async def main(dateien: list[str], seite: Path | None = None) -> None:
    zeilen = []  # (lauf, fall, modell, art, quelle, frage, muss)
    for datei in dateien:
        daten = json.loads(Path(datei).read_text(encoding="utf-8"))
        lauf = Path(datei).stem.removeprefix("verlauf-")
        for fall in daten["faelle"]:
            gefunden = False
            for zug in fall["zuege"]:
                for art, quelle in bloecke(zug.get("antwort", "")):
                    zeilen.append((lauf, fall["id"], zug.get("modell"), art, quelle,
                                   zug.get("schueler", ""), zug.get("muss") or []))
                    gefunden = True
            if not gefunden:
                zug = fall["zuege"][0] if fall["zuege"] else {}
                zeilen.append((lauf, fall["id"], None, "keins", "", zug.get("schueler", ""),
                               zug.get("muss") or []))

    mermaid = [z for z in zeilen if z[3] == "mermaid"]
    pruef = json.loads(subprocess.run(
        ["node", str(HIER / "pele_pruefen.mjs")], input=json.dumps([z[4] for z in mermaid]),
        capture_output=True, text=True, check=True).stdout) if mermaid else []
    mermaid_ergebnis = {id(z): p for z, p in zip(mermaid, pruef)}

    summe = defaultdict(lambda: defaultdict(int))
    fuer_seite = []
    print(f"{'Lauf':<22}{'Fall':<16}{'Art':<9}Ergebnis")
    for z in zeilen:
        lauf, fall, _modell, art, quelle, frage, muss = z
        svg = None
        s = summe[lauf]
        if art == "keins":
            befund = "kein Diagramm in der Antwort"
            s["ohne Diagramm"] += 1
        elif art == "mermaid":
            p = mermaid_ergebnis[id(z)]
            latex, style = bool(LATEX.search(quelle)), bool(re.search(r"^\s*style\s", quelle, re.M))
            befund = ("gültig" if p["roh"] else ("repariert" if p["repariert"] else f"KAPUTT: {p['fehler']}"))
            befund += (" · LaTeX" if latex else "") + (" · style" if style else "")
            s["mermaid"] += 1
            s["mermaid roh gültig"] += p["roh"]
            s["mermaid nach Reparatur"] += p["repariert"]
            s["mermaid mit LaTeX"] += latex
            s["mermaid mit style"] += style
        elif art == "plot":
            try:
                svg = _render_sync(parse_plot_spec(quelle))
                befund = "gültig"
                s["plot gültig"] += 1
            except Exception as e:  # noqa: BLE001 — Messung, jede Ausnahme ist ein Befund
                befund = f"KAPUTT: {str(e)[:80]}"
            s["plot"] += 1
        else:
            try:
                svg = await render_circuit(quelle)
                befund = "gültig"
                s["circuit gültig"] += 1
            except RenderError as e:
                befund = f"KAPUTT: {str(e)[:80]}"
            s["circuit"] += 1
        print(f"{lauf:<22}{fall:<16}{art:<9}{befund}")
        if art in ("circuit", "plot", "keins"):
            fuer_seite.append({"lauf": lauf, "fall": fall, "frage": frage, "muss": muss,
                               "quelle": quelle, "svg": svg, "befund": befund})

    print()
    for lauf, s in summe.items():
        print(lauf + ": " + " · ".join(f"{k} {v}" for k, v in s.items()))


    if seite:
        seite_schreiben(seite, fuer_seite)
        print(f"\nÜbersicht: {seite}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seite", type=Path, default=None, help="HTML-Übersicht zum fachlichen Abhaken")
    p.add_argument("dateien", nargs="+")
    a = p.parse_args()
    asyncio.run(main(a.dateien, a.seite))
