#!/usr/bin/env python3
"""Kennt das Modell die Ionenladungen aus dem „Periodensystem der Grundbausteine"? (26.10.2026)

    python scripts/ionenladungen_probe.py                      # chat-komplex und chat-standard, je 3×
    python scripts/ionenladungen_probe.py --modell chat-komplex --wiederholungen 5

Anlass: Plan Reaktionsgleichungs-Assistent. Im Unterricht entnehmen die Schüler:innen die Formeln
von Salzen den Ionenladungen im PSE der Grundbausteine. Kennt das Modell diese Ladungen sicher,
braucht es dafür keinen Knoten im Wissensspeicher (Jan, 26.10.2026).

Gefragt wird **direkt über den LiteLLM-Proxy** (Master-Schlüssel, Kosten auf dem Systemkonto),
ohne Plattform-Systemtext: Es geht um das Modellwissen, nicht um den Assistenten. Je Element wird
die Antwort gegen `szenarien/ionenladungen.yaml` geprüft: `haupt` muss vorkommen, außer
`haupt` und `zulaessig` darf nichts vorkommen.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

HIER = Path(__file__).resolve().parent
REFERENZ = HIER / "szenarien/ionenladungen.yaml"

FRAGE = (
    "Nenne für jedes der folgenden Elemente die Ladung(en) seiner häufigsten einatomigen Ionen, "
    "so wie sie in einem Schul-Periodensystem stehen: {elemente}. "
    'Antworte nur mit JSON: {{"Na": [1], "Fe": [2, 3], ...}} — Ladungen als ganze Zahlen mit Vorzeichen.'
)


def pruefen(antwort: dict, referenz: dict) -> dict[str, str]:
    """Je Element: 'ok', 'fehlt <haupt>' oder 'falsch <ladung>'."""
    befund = {}
    for el, ref in referenz.items():
        haupt, erlaubt = set(ref["haupt"]), set(ref["haupt"]) | set(ref.get("zulaessig") or [])
        ist = {int(x) for x in (antwort.get(el) or [])}
        falsch, fehlt = ist - erlaubt, haupt - ist
        befund[el] = ("falsch " + ",".join(f"{x:+d}" for x in sorted(falsch)) if falsch else
                      "fehlt " + ",".join(f"{x:+d}" for x in sorted(fehlt)) if fehlt else "ok")
    return befund


def fragen(modell: str, elemente: list[str]) -> dict:
    with httpx.Client(base_url=settings.litellm_proxy_url, timeout=300.0,
                      headers={"Authorization": f"Bearer {settings.litellm_master_key}"}) as c:
        r = c.post("/chat/completions", json={
            "model": modell, "messages": [{"role": "user", "content": FRAGE.format(elemente=", ".join(elemente))}]})
        r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"] or ""
    treffer = re.search(r"\{.*\}", text, re.S)
    return json.loads(treffer.group(0)) if treffer else {}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--modell", action="append", default=None)
    p.add_argument("--wiederholungen", type=int, default=3)
    args = p.parse_args()
    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz.")
    referenz = yaml.safe_load(REFERENZ.read_text(encoding="utf-8"))["elemente"]
    for modell in args.modell or ["chat-komplex", "chat-standard"]:
        fehler: dict[str, list[str]] = {}
        for _ in range(args.wiederholungen):
            for el, b in pruefen(fragen(modell, list(referenz)), referenz).items():
                if b != "ok":
                    fehler.setdefault(el, []).append(b)
        ok = len(referenz) - len(fehler)
        print(f"\n{modell}: {ok}/{len(referenz)} Elemente in allen {args.wiederholungen} Läufen richtig")
        for el, b in sorted(fehler.items()):
            print(f"  {el}: {len(b)}/{args.wiederholungen} — {'; '.join(b)}")


if __name__ == "__main__":
    main()
