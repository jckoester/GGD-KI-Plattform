#!/usr/bin/env python3
"""Gegenprobe „Diagramme zeichnen“ auswerten (0.36, Plan Schritt 5).

    venv/bin/python scripts/diagramme_auswerten.py <verlauf-*.json> …

Zieht ```mermaid, ```plot und ```circuitikz aus den Antworten der Protokolle von
`assistent_messung.py` (Szenarien `diagramme_zeichnen.yaml`) und prüft, ob sie sich zeichnen lassen:
Mermaid mit Pele roh und nach der Reparatur (`pele_pruefen.mjs`), Plot mit dem Plot-Renderer,
Schaltplan über den Render-Sidecar (muss laufen). Dazu bei Mermaid: LaTeX in Beschriftungen
(`\\(`, `\\ce`, `$`) und `style`-Zeilen — beides zeichnet Pele nicht so, wie gemeint.
"""
import asyncio
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


async def main(dateien: list[str]) -> None:
    zeilen = []  # (lauf, fall, modell, art, quelle)
    for datei in dateien:
        daten = json.loads(Path(datei).read_text(encoding="utf-8"))
        lauf = Path(datei).stem.removeprefix("verlauf-")
        for fall in daten["faelle"]:
            gefunden = False
            for zug in fall["zuege"]:
                for art, quelle in bloecke(zug.get("antwort", "")):
                    zeilen.append((lauf, fall["id"], zug.get("modell"), art, quelle))
                    gefunden = True
            if not gefunden:
                zeilen.append((lauf, fall["id"], None, "keins", ""))

    mermaid = [z for z in zeilen if z[3] == "mermaid"]
    pruef = json.loads(subprocess.run(
        ["node", str(HIER / "pele_pruefen.mjs")], input=json.dumps([z[4] for z in mermaid]),
        capture_output=True, text=True, check=True).stdout) if mermaid else []
    mermaid_ergebnis = {id(z): p for z, p in zip(mermaid, pruef)}

    summe = defaultdict(lambda: defaultdict(int))
    print(f"{'Lauf':<22}{'Fall':<16}{'Art':<9}Ergebnis")
    for z in zeilen:
        lauf, fall, _modell, art, quelle = z
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
                _render_sync(parse_plot_spec(quelle))
                befund = "gültig"
                s["plot gültig"] += 1
            except Exception as e:  # noqa: BLE001 — Messung, jede Ausnahme ist ein Befund
                befund = f"KAPUTT: {str(e)[:80]}"
            s["plot"] += 1
        else:
            try:
                await render_circuit(quelle)
                befund = "gültig"
                s["circuit gültig"] += 1
            except RenderError as e:
                befund = f"KAPUTT: {str(e)[:80]}"
            s["circuit"] += 1
        print(f"{lauf:<22}{fall:<16}{art:<9}{befund}")

    print()
    for lauf, s in summe.items():
        print(lauf + ": " + " · ".join(f"{k} {v}" for k, v in s.items()))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
