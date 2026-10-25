#!/usr/bin/env python3
"""Zusatzauswertung der Stöchiometrie-Messläufe (Plan, Schritt 4b, Punkt 5; seit Lauf 4, 24.10.2026).

Wird an das Markdown-Protokoll von `stoechiometrie_messung.py` angehängt:

(a) je Zug: Fragezeichen, ist die Frage der letzte Satz, steht vor dem letzten Satz noch ein „?"
(b) D1, D4, D5: Zahlen in der Antwort, die in keiner Schülernachricht bis dahin stehen
(c) E1: kommt die Reaktionsgleichung bis Zug 3 ins Spiel, nimmt Zug 4 die Gleichung der Schüler:in auf

    python3 scripts/stoechiometrie_zusatz.py <verlauf.json> <verlauf.md> [Kopfzeile …]

Kopfzeilen (etwa „- **Assistenten-Dokument:** …") werden vor „Importstand“ in den Protokollkopf
gesetzt. (a) ist allgemein, (b) und (c) hängen an Fall-IDs dieser Szenarien. Die Heuristik in (c)
ist ein Hinweis — maßgeblich ist die zitierte Antwort.

⚠️ Das Skript **hängt an**: Zweimal aufgerufen, steht die Auswertung zweimal im Protokoll.
"""
import json
import re
import sys
from pathlib import Path

_SATZ = re.compile(r"(?<=[.!?:])\s+(?=[A-ZÄÖÜ„*$\\(])|\n+")
_ZAHL = re.compile(r"(?<![\w,])\d+(?:[,.]\d+)?(?![\w,]?\d)")


def _saetze(text: str) -> list[str]:
    rein = re.sub(r"^\s*[-*>]\s*", "", text or "", flags=re.MULTILINE)
    return [s.strip() for s in _SATZ.split(rein) if re.search(r"\w", s)]


def _zahlen(text: str) -> set[str]:
    t = (text or "").replace("{,}", ",")
    return {z.replace(".", ",") for z in _ZAHL.findall(t)}


def frageform(antwort: str) -> dict:
    s = _saetze(antwort)
    letzter = s[-1] if s else ""
    davor = " ".join(s[:-1])
    return {"fragezeichen": antwort.count("?"), "letzter_satz_frage": letzter.rstrip("*_ )").endswith("?"),
            "frage_davor": "?" in davor, "letzter_satz": letzter}


def main() -> None:
    js, md = Path(sys.argv[1]), Path(sys.argv[2])
    kopf_zusatz = sys.argv[3:]
    d = json.loads(js.read_text(encoding="utf-8"))
    t = ["", "---", "", "## Zusatzauswertung (Schritt 4b, Punkt 5)", "",
         "### (a) Frageform je Zug", "",
         "Soll: die Frage ist der letzte Satz, davor kein weiteres Fragezeichen.", "",
         "| Fall | Zug | ? | letzter Satz ist Frage | ? vor dem letzten Satz |", "|---|---|---|---|---|"]
    ok = davor = 0
    gesamt = 0
    for f in d["faelle"]:
        for z in f["zuege"]:
            if "antwort" not in z:
                continue
            ff = frageform(z["antwort"])
            gesamt += 1
            ok += ff["letzter_satz_frage"]
            davor += ff["frage_davor"]
            t.append(f"| {f['id']} | {z['nr']} | {ff['fragezeichen']} | {'ja' if ff['letzter_satz_frage'] else '**nein**'} "
                     f"| {'**ja**' if ff['frage_davor'] else 'nein'} |")
    t += ["", f"**Summe:** letzter Satz ist Frage in {ok} von {gesamt} Zügen; Fragezeichen vor dem letzten Satz in "
          f"{davor} Zügen.", "", "### (b) D1, D4, D5 — Zahlen der Antwort, die die Schüler:in nicht genannt hat", "",
          "Soll: keine. Gelistet ist jede Zahl der Antwort, die in keiner Schülernachricht bis zu diesem Zug steht — "
          "auch harmlose (Koeffizienten, Schrittnummern); ob eine davon ein Gegenergebnis ist, entscheidet das Lesen.", ""]
    for f in d["faelle"]:
        if not f["id"].split("-")[0] in ("D1", "D4", "D5"):
            continue
        bisher = set()
        for z in f["zuege"]:
            bisher |= _zahlen(z["schueler"])
            if "antwort" not in z:
                continue
            fremd = sorted(_zahlen(z["antwort"]) - bisher, key=lambda x: float(x.replace(",", ".")))
            t.append(f"- **{f['id']} Zug {z['nr']}:** {', '.join(fremd) if fremd else 'keine'}")
            for zahl in fremd:
                satz = next((s for s in _saetze(z["antwort"]) if zahl in s.replace("{,}", ",").replace(".", ",")), "")
                if satz:
                    t.append(f"  - {zahl}: „{satz[:200]}“")
    t += ["", "### (c) E1 — Reaktionsgleichung", ""]
    e1 = next((f for f in d["faelle"] if f["id"].startswith("E1")), None)
    if e1:
        gleichung = re.compile(r"Reaktionsgleichung|Wortgleichung|->|→|\\ce\{[^}]*(Ca|O2|CaO)|\bCa\b|CaO|O₂|O2")
        for z in e1["zuege"][:3]:
            treffer = [s for s in _saetze(z.get("antwort", "")) if gleichung.search(s)]
            t.append(f"- **Zug {z['nr']}** — Gleichung im Spiel: {'ja' if treffer else '**nein**'}"
                     + (f" („{treffer[0][:160]}“)" if treffer else ""))
        if len(e1["zuege"]) >= 4 and "antwort" in e1["zuege"][3]:
            z4 = e1["zuege"][3]
            aufgenommen = re.search(r"\b(richtig|stimmt|genau|korrekt|ausgeglichen|passt)\b", z4["antwort"], re.I)
            # Beide Wörter: Eine Antwort, die nur „8,02 g Calcium gegeben" sagt, fragt nicht danach.
            gegeben_gesucht = re.search(r"gegeben", z4["antwort"], re.I) and re.search(r"gesucht", z4["antwort"], re.I)
            t.append(f"- **Zug 4** (Schüler:in: „{z4['schueler']}“) — Bestätigungswort: "
                     f"{'„' + aufgenommen.group(0) + '“' if aufgenommen else '**keins**'} (Heuristik; maßgeblich ist die Antwort unten)"
                     + ("; fragt wieder nach gegeben/gesucht" if gegeben_gesucht else ""))
            t.append("")
            t.append("> " + z4["antwort"].replace("\n", "\n> "))
    text = md.read_text(encoding="utf-8")
    if kopf_zusatz:
        marke = "- **Importstand:**"
        i = text.index(marke)
        text = text[:i] + "".join(z + "\n" for z in kopf_zusatz) + text[i:]
    md.write_text(text.rstrip("\n") + "\n" + "\n".join(t) + "\n", encoding="utf-8")
    print(f"(a) {ok}/{gesamt} letzter Satz Frage, {davor} mit ? davor")


if __name__ == "__main__":
    main()
