#!/usr/bin/env python3
"""Abnahme UP-8 Schritt 13: Wochenmuster gegen den tatsächlichen Plan prüfen.

Das ist **kein** Unit-Test — er braucht die echte Stundenplanquelle und liefe ohne sie
rot. Er beantwortet die Frage aus dem Plan: Stimmt das abgeleitete Wochenmuster mit dem
überein, was in den Wochen wirklich stand?

Geprüft wird in beide Richtungen, denn nur zusammen sind sie aussagekräftig:

* **Erfunden?** Zu jedem Mustereintrag muss es an genau so vielen Tagen echten Unterricht
  geben, wie das Muster behauptet (`gesehen`).
* **Übersehen?** Jede Stunde, die in **allen** Wochen an derselben Stelle stand, muss im
  Muster auftauchen. Ohne diese Richtung wäre ein Muster, das nur die Hälfte findet,
  fehlerfrei.

Verwendung:
    python scripts/verify_patterns.py            # Stichprobe über mehrere Lehrkräfte
    python scripts/verify_patterns.py AK BO      # gezielt
"""
import asyncio
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.calendar.base import LessonState
from app.calendar.groups import kein_unterricht_codes
from app.calendar.patterns import MUSTER_ZUSTAENDE, _gruppe, derive_patterns
from app.calendar.router import _unterrichtswochen
from app.calendar.service import get_adapter, list_kuerzel

# Letztes volles Musterfenster des Schuljahres 2025/26.
REFERENZ = date(2026, 6, 30)
WOCHEN = 4
STICHPROBE = 8


def _zaehle_echte_stunden(stunden, wochen, kein_unterricht):
    """Wie oft stand bei (Gruppe, Wochentag, Stunde) tatsächlich Unterricht?

    Gezählt wird nach denselben Regeln, nach denen das Muster zählt — sonst vergliche
    man zwei verschiedene Fragen und der Vergleich wäre wertlos.

    **Die Gruppe gehört in den Schlüssel.** Ohne sie zählt eine Klassenleitungsstunde,
    die zufällig auf derselben Position liegt wie die Deutschstunde einer anderen
    Lerngruppe, in denselben Topf — das erzeugt Abweichungen, die es nicht gibt.
    (Erste Fassung dieses Skripts meldete so 7 statt 2 Fälle.)
    """
    treffer = defaultdict(set)
    for l in stunden:
        if l.state not in MUSTER_ZUSTAENDE or l.start_period is None:
            continue
        if l.covering_for:
            continue
        if l.subject and l.subject.upper() in kein_unterricht:
            continue
        gruppe = _gruppe(l)
        if not gruppe.identifizierbar:
            continue
        woche = l.date - timedelta(days=l.date.weekday())
        if woche not in wochen:
            continue
        for versatz in range(max(1, l.periods)):
            treffer[(gruppe, l.date.weekday(), l.start_period + versatz)].add(woche)
    return treffer


async def pruefe(adapter, kuerzel, wochen, raster, kein_unterricht):
    stunden = []
    for woche in wochen:
        stunden.extend((await adapter.fetch_week(kuerzel, woche)).lessons)
    if not stunden:
        return None

    muster = derive_patterns(
        stunden, wochen=wochen, timegrid=raster, kein_unterricht=kein_unterricht
    )
    echt = _zaehle_echte_stunden(stunden, set(wochen), kein_unterricht)

    erfunden, falsch_gezaehlt, uebersehen = [], [], []

    belegt = set()
    for p in muster.proposals:
        for versatz in range(p.periods):
            stelle = (p.key, p.weekday, p.start_period + versatz)
            belegt.add(stelle)
            tatsaechlich = len(echt.get(stelle, ()))
            if tatsaechlich == 0:
                erfunden.append((p, stelle))
            elif tatsaechlich != p.gesehen:
                falsch_gezaehlt.append((p, stelle, tatsaechlich))

    # Andere Richtung: was in JEDER Woche stand, muss im Muster stehen.
    for stelle, gesehen_in in echt.items():
        if len(gesehen_in) == len(wochen) and stelle not in belegt:
            uebersehen.append(stelle)

    return {
        "kuerzel": kuerzel,
        "stunden": len(stunden),
        "muster": len(muster.proposals),
        "wochenstunden": sum(p.periods for p in muster.proposals),
        "unsicher": sum(1 for p in muster.proposals if p.gesehen < len(wochen)),
        "erfunden": erfunden,
        "falsch_gezaehlt": falsch_gezaehlt,
        "uebersehen": uebersehen,
        "zustaende": Counter(l.state.name for l in stunden),
    }


async def main(kuerzel_liste):
    wochen = _unterrichtswochen(REFERENZ, WOCHEN)
    kein_unterricht = kein_unterricht_codes()
    print(f"Musterfenster: {', '.join(w.isoformat() for w in wochen)}")
    print(f"Nicht-Unterricht-Kürzel: {sorted(kein_unterricht)}\n")

    adapter = get_adapter()
    async with adapter:
        raster = await adapter.timegrid(wochen[-1])
        if not kuerzel_liste:
            alle = await list_kuerzel()
            schritt = max(1, len(alle) // STICHPROBE)
            kuerzel_liste = alle[::schritt][:STICHPROBE]

        fehler = 0
        for k in kuerzel_liste:
            e = await pruefe(adapter, k, wochen, raster, kein_unterricht)
            if e is None:
                print(f"{k:>5}: keine Stunden im Fenster")
                continue
            status = "OK "
            if e["erfunden"] or e["falsch_gezaehlt"] or e["uebersehen"]:
                status = "!! "
                fehler += 1
            print(
                f"{status}{k:>5}: {e['stunden']:>3} Stunden → {e['muster']:>2} Muster, "
                f"{e['wochenstunden']:>2} Wochenstunden, {e['unsicher']} unsicher"
            )
            for p, stelle in e["erfunden"]:
                print(f"        ERFUNDEN  {stelle} ({p.key})")
            for p, stelle, tat in e["falsch_gezaehlt"]:
                print(f"        ZAEHLUNG  {stelle}: Muster {p.gesehen}, echt {tat}")
            for stelle in e["uebersehen"]:
                print(f"        UEBERSEHEN {stelle} — stand in allen {len(wochen)} Wochen")

    print(f"\n{len(kuerzel_liste)} Lehrkräfte geprüft, {fehler} mit Abweichung")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
