#!/usr/bin/env python3
"""Eine Frage durch den echten Chat schicken und **mitlesen, was dabei passiert**.

    python scripts/chat_probe.py --assistent 8 --gruppe 37 "Was ist eine Oxidation?"
    python scripts/chat_probe.py --assistent 8 --datei szenarien.txt --json > vorher.json

⚠️ **Nur für Entwicklungs- und Testinstanzen.** Das Skript stellt sich seinen eigenen
Sitzungs-Token aus (wie die Integrationstests, weil die Passwörter in
`test_users.yaml` gehasht sind) und fährt damit echte Modellaufrufe auf Kosten des
Budgets. Auf einer Produktivinstanz hätte beides nichts verloren; es weigert sich bei
``ENVIRONMENT=production``.

**Wozu es gebraucht wird.** Der Nachgang zu Paket 9/AP7 verlangt vor und nach jeder
Änderung dieselbe Messung an denselben Szenarien. Aus der Datenbank ist das nicht zu
haben: `messages` kennt nur `user` und `assistant` — **Werkzeugaufrufe werden nicht
gespeichert**. Sichtbar sind sie allein im Rohstrom der Antwort (`event: tool_status`),
und den wertet die Oberfläche nicht aus. Dieses Skript liest ihn mit.

⚠️ **Was auch hier nicht zu sehen ist:** die Suchanfrage, die das Modell gewählt hat,
und die Treffer. `tool_status` trägt nur Werkzeugname und Runde; die Argumente bleiben
bewusst draußen, weil dort der Suchtext der Nutzer:in steht. Wer die Treffer braucht,
stellt die Suche mit demselben Profil nach.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.dependencies import get_jwt_service
from app.config import settings


def frage_stellen(
    client: httpx.Client, frage: str, *, assistent: int | None, gruppe: int | None,
    modell: str | None = None,
) -> dict:
    """Eine Frage senden und den Rohstrom auswerten.

    ⚠️ **Die Ereignisgrenze ist die Leerzeile.** Ein SSE-Block ohne `event:`-Zeile ist
    ein Standardereignis (die Token der Antwort). Wer den zuletzt gelesenen Namen über
    die Leerzeile hinaus stehen lässt, zählt den halben Antworttext als
    Werkzeugaufruf — beim ersten Versuch genau so passiert.
    """
    rumpf: dict = {"messages": [{"role": "user", "content": frage}]}
    if assistent is not None:
        rumpf["assistant_id"] = assistent
    if gruppe is not None:
        rumpf["group_id"] = gruppe
    if modell is not None:
        rumpf["model_id"] = modell

    werkzeuge: list[dict] = []
    stuecke: list[str] = []
    ereignisse: dict[str, int] = {}

    with client.stream("POST", "/chat", json=rumpf) as strom:
        if strom.status_code != 200:
            strom.read()
            raise SystemExit(f"HTTP {strom.status_code}: {strom.text[:400]}")
        name: str | None = None
        for zeile in strom.iter_lines():
            if not zeile.strip():
                name = None                      # Blockende
                continue
            if zeile.startswith("event: "):
                name = zeile[7:].strip()
                ereignisse[name] = ereignisse.get(name, 0) + 1
                continue
            if not zeile.startswith("data: "):
                continue
            nutzlast = zeile[6:]
            if name == "tool_status":
                werkzeuge.append(json.loads(nutzlast))
            elif name is None and nutzlast != "[DONE]":
                try:
                    brocken = json.loads(nutzlast)["choices"][0]["delta"]
                    stuecke.append(brocken.get("content") or "")
                except (KeyError, IndexError, json.JSONDecodeError):
                    pass

    antwort = "".join(stuecke)
    return {
        "frage": frage,
        "werkzeuge": werkzeuge,
        "ereignisse": ereignisse,
        "antwort": antwort,
        # Die Kennzahlen aus dem Messplan (N8): Kürze und Rückfragen sind das, was die
        # neue Präambel ändern soll — sie hier mitzuzählen erspart das Nachzählen von
        # Hand und macht zwei Läufe vergleichbar.
        **kennzahlen(antwort),
    }


#: Überschrift und Aufzählungspunkt in der Antwort — beides zählt, weil der Befund aus
#: AP7 nicht „zu lang" hieß, sondern „zu viel auf einmal": Gliederungen wie „Was du jetzt
#: noch überlegen könntest" mit Leitfragen, Reflexionsanstößen und Versuchsideen unter
#: einer Frage, die mit drei Sätzen beantwortet wäre. Die Wortzahl allein sieht das nicht.
_UEBERSCHRIFT = re.compile(r"^#{1,6} ", re.MULTILINE)
_LISTENPUNKT = re.compile(r"^\s*(?:[-*+]|\d+\.)\s", re.MULTILINE)


def kennzahlen(antwort: str) -> dict:
    """Die vier Formkennzahlen aus dem Messplan (N8).

    ⚠️ **`fragezeichen` ist eine Näherung für „Rückfragen".** Eine rhetorische Frage
    mitten im Text zählt mit, eine Rückfrage ohne Fragezeichen nicht. Für den Vergleich
    zweier Läufe genügt das; für eine Einzelaussage nicht.
    """
    return {
        "woerter": len(antwort.split()),
        "fragezeichen": antwort.count("?"),
        "ueberschriften": len(_UEBERSCHRIFT.findall(antwort)),
        "listenpunkte": len(_LISTENPUNKT.findall(antwort)),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Eine Frage durch den echten Chat schicken")
    p.add_argument("fragen", nargs="*", help="Eine oder mehrere Fragen")
    p.add_argument("--datei", type=Path, help="Datei mit einer Frage je Zeile")
    p.add_argument("--assistent", type=int, default=None)
    p.add_argument("--gruppe", type=int, default=None)
    p.add_argument("--modell", default=None,
                   help="Modell-Alias, sonst das des Assistenten (z. B. chat-komplex)")
    p.add_argument("--pseudonym", default="probe-schueler",
                   help="Pseudonym für den Token; für Budget und Gruppenbezug relevant")
    p.add_argument("--stufe", default="9", help="Jahrgang im Token (Zeichenkette)")
    p.add_argument("--rolle", default="student", choices=["student", "teacher"])
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--json", action="store_true", help="Ergebnis als JSON ausgeben")
    args = p.parse_args()

    if settings.environment == "production":
        p.error(
            "Nicht auf einer Produktivinstanz: Das Skript stellt sich einen eigenen "
            "Sitzungs-Token aus und verbraucht echtes Budget."
        )

    fragen = list(args.fragen)
    if args.datei:
        fragen += [z.strip() for z in args.datei.read_text(encoding="utf-8").splitlines()
                   if z.strip() and not z.startswith("#")]
    if not fragen:
        p.error("Keine Frage angegeben")

    # ⚠️ **Jede Frage in einer eigenen Konversation.** Im Testlauf vom 26.09.2026 stand
    # Szenario (f) an sechster Stelle, nach fünf ausführlichen Antworten des Modells —
    # und fiel anders aus als allein gestellt. Ein Messlauf, der die Fragen aneinander
    # hängt, misst auch den Gesprächsverlauf mit. Wer genau den prüfen will, ruft das
    # Skript mit mehreren Fragen und `--verlauf` … das gibt es (noch) nicht; dann von
    # Hand in der Oberfläche.
    token, _ = get_jwt_service().issue(
        pseudonym=args.pseudonym, roles=[args.rolle], grade=args.stufe
    )
    ergebnisse = []
    with httpx.Client(base_url=args.basis, timeout=300.0,
                      headers={"Cookie": f"session={token}"}) as client:
        for frage in fragen:
            ergebnisse.append(
                frage_stellen(client, frage, assistent=args.assistent,
                              gruppe=args.gruppe, modell=args.modell)
            )

    if args.json:
        print(json.dumps(ergebnisse, ensure_ascii=False, indent=2))
        return
    for e in ergebnisse:
        werkzeuge = ", ".join(
            f"{w['tool']} (Runde {w['round']})" for w in e["werkzeuge"]
        ) or "KEIN Werkzeugaufruf"
        print(f"\n{'─' * 78}\n▸ {e['frage']}")
        print(f"  Werkzeuge: {werkzeuge}")
        print(f"  {e['woerter']} Wörter, {e['fragezeichen']} Fragezeichen, "
              f"{e['ueberschriften']} Überschriften, {e['listenpunkte']} Listenpunkte\n")
        print(e["antwort"])


if __name__ == "__main__":
    main()
