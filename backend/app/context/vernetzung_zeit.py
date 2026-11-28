"""Zeit der Vernetzung (Päckchen BE, Teil A, Schritt 2): Schuljahr je Stufe, Lage der Kapitel.

Rein, ohne Datenbank. Eine **Lage** sagt, wann ein Kapitel in einer Stufe läuft: Unterrichtswoche
von–bis und woher das kommt — aus einem beschlossenen Jahresverlaufsplan (`plan`), einem Entwurf
(`entwurf`) oder geschätzt aus Reihenfolge und Stunden des Curriculums (`geschaetzt`, F3).

Entschieden (Jan, 28.11.2026, Plan `Vernetzung-Zeitachse-BE-Plan`):

- **F3:** Ohne Plan schätzt die Ansicht: Kapitelstunden ÷ Wochenstunden der Stufe, der Reihe
  nach; ein Curriculum über zwei Stufen füllt erst die eine, dann die andere. Fehlen Stunden oder
  Wochenstunden, teilen sich die Kapitel die Wochen gleich. Die Zeitprüfung der Absprachen nutzt
  die Schätzung nicht (`als_spanne`).
- **F13:** Jede Stufe hat ihr Schuljahr — alle dasselbe („Schuljahr“, laufendes oder kommendes)
  oder der Weg einer Klasse (Stufe s im Jahr laufend + (s − Bezugsstufe)).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from app.context.absprachen_zeit import Spanne
from app.context.editions import parse_schuljahr_start

PLAN, ENTWURF, GESCHAETZT = "plan", "entwurf", "geschaetzt"
SCHULJAHR, WEG = "schuljahr", "weg"


@dataclass(frozen=True)
class Lage:
    stufe: int
    von_woche: int
    bis_woche: int
    quelle: str

    def als_dict(self) -> dict:
        return {"stufe": self.stufe, "von_woche": self.von_woche, "bis_woche": self.bis_woche,
                "quelle": self.quelle}


def schuljahr_text(start: int) -> str:
    """2026 → „2026/27“."""
    return f"{start}/{(start + 1) % 100:02d}"


def verschoben(schuljahr: str, jahre: int) -> str:
    return schuljahr_text(parse_schuljahr_start(schuljahr) + jahre)


def schuljahre(stufen: Iterable[int], aktuelles: str, *, modus: str = SCHULJAHR,
               schuljahr: Optional[str] = None, bezugsstufe: Optional[int] = None) -> dict[int, str]:
    """Je Stufe ihr Schuljahr. `schuljahr`: alle Stufen in diesem Jahr (Vorgabe: das laufende).
    `weg`: die Klasse, die im laufenden Jahr in `bezugsstufe` ist."""
    stufen = sorted(set(stufen))
    if modus == WEG:
        if bezugsstufe is None:
            raise ValueError("Für den Weg einer Klasse fehlt die Bezugsstufe")
        return {s: verschoben(aktuelles, s - bezugsstufe) for s in stufen}
    return {s: schuljahr or aktuelles for s in stufen}


def plan_lagen(abschnitte: list[dict], stufe: int, quelle: str, *,
               kapitel_von_sequenz: Optional[dict[str, str]] = None,
               wochen_im_jahr: Optional[int] = None) -> dict[str, Lage]:
    """Je Kapitel eines Plans seine Lage, aus der Dauer der Abschnitte der Reihe nach — wie
    `verlaufsplan_zeit.lage`, aber ohne Kalender (die Wochen zählen auch ohne ihn).

    Puffer zählen mit, tragen aber kein Kapitel. Hinter dem Schuljahr (`wochen_im_jahr`) zählt
    nichts. Bei sequenzgenauer Planung bildet `kapitel_von_sequenz` die Sequenzen ab."""
    gesammelt: dict[str, list[tuple[int, int]]] = {}
    pos = 1
    for a in abschnitte:
        dauer = max(1, int(a.get("wochen") or 1))
        von, bis = pos, pos + dauer - 1
        pos = bis + 1
        if a.get("puffer") or (wochen_im_jahr is not None and von > wochen_im_jahr):
            continue
        if wochen_im_jahr is not None:
            bis = min(bis, wochen_im_jahr)
        ids = {str(k) for k in a.get("kapitel_ids") or []}
        for sid in a.get("sequenz_ids") or []:
            if (kid := (kapitel_von_sequenz or {}).get(str(sid))):
                ids.add(str(kid))
        for kid in ids:
            gesammelt.setdefault(kid, []).append((von, bis))
    return {kid: Lage(stufe, min(v for v, _ in w), max(b for _, b in w), quelle) for kid, w in gesammelt.items()}


def schaetzen(kapitel: list[tuple[str, Optional[float]]], stufen: list[int],
              wochenstunden: dict[int, Optional[float]], wochen: dict[int, int]) -> dict[str, list[Lage]]:
    """Lage der Kapitel eines Curriculums ohne Plan (F3).

    `kapitel`: (Kennung, Stunden) in Reihenfolge; `stufen`: die Stufen, die das Curriculum hier
    bedient, aufsteigend; `wochen`: Unterrichtswochen je Stufe. Mit Stunden und Wochenstunden
    dauert ein Kapitel Stunden ÷ Wochenstunden der Stufe, in der es beginnt; sonst teilen sich alle
    Kapitel die Wochen gleich. Ein Kapitel über die Grenze zweier Stufen bekommt in jeder eine
    Lage; was über die letzte Stufe hinausreicht, wird am Ende abgeschnitten."""
    stufen = [s for s in sorted(set(stufen)) if wochen.get(s)]
    if not kapitel or not stufen:
        return {}
    gesamt = sum(wochen[s] for s in stufen)
    mit_stunden = all(std for _, std in kapitel) and all(wochenstunden.get(s) for s in stufen)

    # Fortlaufende Wochen über die Stufen: Stufe i beginnt bei versatz[i]
    versatz, x = {}, 0
    for s in stufen:
        versatz[s] = x
        x += wochen[s]

    def stufe_bei(t: float) -> int:
        for s in reversed(stufen):
            if t >= versatz[s]:
                return s
        return stufen[0]

    aus: dict[str, list[Lage]] = {}
    t = 0.0
    for kid, std in kapitel:
        if t >= gesamt:
            break
        dauer = std / wochenstunden[stufe_bei(t)] if mit_stunden else gesamt / len(kapitel)
        anfang, ende = t, min(t + max(dauer, 0.5), gesamt)
        t = anfang + max(dauer, 0.5)
        for s in stufen:
            lo, hi = versatz[s], versatz[s] + wochen[s]
            a, e = max(anfang, lo), min(ende, hi)
            if e - a <= 0:
                continue
            von = int(a - lo) + 1
            bis = max(von, int(-(-(e - lo) // 1)))   # aufrunden
            aus.setdefault(kid, []).append(Lage(s, von, min(bis, wochen[s]), GESCHAETZT))
    return aus


def als_spanne(lagen: list[Lage], stufen_des_curriculums: Optional[tuple[int, int]] = None) -> Optional[Spanne]:
    """Für die Zeitprüfung (`absprachen_zeit.pruefe`): aus Plänen mit Wochen, aus einer Schätzung
    nur die Stufen — eine Schätzung beweist keine Verletzung (F3)."""
    if not lagen:
        if stufen_des_curriculums and stufen_des_curriculums[0] is not None:
            von, bis = stufen_des_curriculums
            return Spanne(von, bis if bis is not None else von)
        return None
    s = sorted(lagen, key=lambda l: (l.stufe, l.von_woche))
    erst, letzt = s[0], max(s, key=lambda l: (l.stufe, l.bis_woche))
    if any(l.quelle == GESCHAETZT for l in s):
        return Spanne(erst.stufe, letzt.stufe)
    return Spanne(erst.stufe, letzt.stufe, erst.von_woche, letzt.bis_woche,
                  entwurf=any(l.quelle == ENTWURF for l in s))
