#!/usr/bin/env python3
"""Fragt der Assistent nach der Klassenstufe, obwohl sie im Systemtext steht?

    cd backend && venv/bin/uvicorn app.main:app --port 8001      # in einem Terminal
    venv/bin/python scripts/chat_probe.py --datei scripts/szenarien/stufe_nachfrage.txt \
        --stufe 9 --basis http://localhost:8001 --json > /tmp/vorher.json
    venv/bin/python scripts/stufe_nachfrage.py /tmp/vorher.json

⚠️ **Geprüft in beide Richtungen — und die erste Fassung war falsch.** Sie erkannte
den wörtlichen Satz aus dem Befund **nicht**: „…du in der 9. Klasse bist – stimmt
das?" Der Punkt in „9." beendete für den Satzzerleger den Satz, und das Muster kam
nicht darüber hinweg. Aufgefallen ist das erst, weil die **Ja-Seite** geprüft wurde;
an zwölf echten Antworten sagte das Instrument zuvor brav „nein", ohne je „ja" sagen
zu können.

Seither gilt: sechs Sätze müssen treffen (darunter der aus dem Befund), sechs echte
Rückfragen aus gemessenen Antworten dürfen **nicht** treffen. Wer die Muster ändert,
lässt beide Listen laufen — in diesem Projekt war das Messinstrument dreimal falsch,
und jedes Mal sah die Zahl plausibel aus.

**Messung vom 27.09.2026** (Testkonto `schueler09`, Klasse 9, `chat-standard`):
0 von 8 im freien Chat, 0 von 4 mit Schüler-Assistent. Kontrollprobe „In welcher Klasse
bin ich?" → „Du bist in der 9. Klasse" — das Modell hatte die Angabe also.


Kriterium **vorher festgelegt**: Die Antwort enthält ein Fragezeichen UND in demselben
Satz eine Wendung, die auf die Klassenstufe der fragenden Person zielt.

⚠️ Zweimal ist in diesem Projekt das Messinstrument schiefgegangen (gezählte
Aufzählungspunkte statt Rezepte; „natron" innerhalb von „Natronlauge"). Deshalb hier:
Satzweise geprüft, Wortgrenzen, und jeder Treffer wird ausgedruckt — ich sehe ihn an,
statt der Zahl zu glauben.
"""
import re
import sys

# ⚠️ **Satzzerlegung, die Ordnungszahlen überlebt.** „du in der 9. Klasse bist – stimmt
# das?" ist **ein** Satz; ein Zerleger, der an jedem Punkt trennt, macht daraus zwei und
# verliert den Zusammenhang zwischen „9." und „Klasse". Genau daran ist die erste Fassung
# dieses Skripts gescheitert: Sie hat den wörtlichen Satz aus dem Befund **nicht**
# erkannt. Deshalb wird nur getrennt, wo dem Punkt keine Ziffer vorausgeht.
SATZENDE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ„*\-])")


def saetze(text: str) -> list[str]:
    roh = SATZENDE.split(text)
    zusammen: list[str] = []
    for teil in roh:
        # „9. Klasse" — ein Bruchstück, das mit einer kleingeschriebenen Fortsetzung
        # beginnt oder dessen Vorgänger auf eine Ziffer endet, gehört an den vorigen.
        if zusammen and re.search(r"\d\.\s*$", zusammen[-1]):
            zusammen[-1] += " " + teil
        else:
            zusammen.append(teil)
    return [z.strip() for z in zusammen if z.strip()]


#: Wendungen, die auf die Klassenstufe **der fragenden Person** zielen.
#:
#: ⚠️ `[^?!]*` statt `[^.?!]*`: Zwischen „ich gehe davon aus" und „Klasse" steht im
#: Befund eine Ordnungszahl mit Punkt.
MUSTER = [
    r"\bin welche[rnm]? (klasse|klassenstufe|jahrgangsstufe|stufe)\b",
    r"\bwelche (klasse|klassenstufe|jahrgangsstufe)\b",
    r"\bwelche[nm]? (jahrgang|schuljahr)\b",
    r"\bbist du\b[^?!]*\b(klasse|klassenstufe|jahrgangsstufe|mittelstufe|oberstufe|unterstufe)\b",
    r"\bgehst du\b[^?!]*\b(klasse|stufe)\b",
    r"\b(ich gehe davon aus|ich nehme an|vermutlich|vermute)\b[^?!]*\b(klasse|stufe)\b",
    r"\b(klasse|klassenstufe|jahrgangsstufe)\b[^?!]*\b(stimmt das|richtig\?|oder\?)",
    r"\bwie alt bist du\b",
]
RE = [re.compile(m, re.IGNORECASE) for m in MUSTER]


def fragt_nach_stufe(antwort: str) -> str | None:
    """Der Satz, der nach der Stufe fragt — oder ``None``."""
    for satz in saetze(antwort):
        if "?" not in satz:
            continue
        for r in RE:
            if r.search(satz):
                return satz.strip()
    return None


if __name__ == "__main__":
    import json
    daten = json.load(open(sys.argv[1]))
    treffer = 0
    for eintrag in daten:
        satz = fragt_nach_stufe(eintrag.get("antwort", ""))
        marke = "FRAGT" if satz else "     "
        print(f"  {marke}  {eintrag['frage'][:42]:44} {satz or ''}")
        treffer += bool(satz)
    print(f"\n  {treffer} von {len(daten)} Antworten fragen nach der Klassenstufe")
