"""Zeitprüfung der Absprachen mit den Jahresverlaufsplänen (0.64, Päckchen AY Teil 2, Teil B, F5).

Rein, ohne Datenbank. Eine **Spanne** ist, wann ein Kapitel läuft: von–bis als (Klassenstufe,
Unterrichtswoche). Aus einem Jahresverlaufsplan kennt man die Wochen; ohne Plan nur die Stufen
des Curriculums (Woche `None`).

Prüfung je Art aus Sicht des Kapitels, das die Absprache trägt („hier“), gegen das Kapitel des
anderen Fachs („dort“):

- `vorher` — dort endet spätestens in der Woche, in der hier beginnt;
- `nachher` — dort beginnt frühestens in der Woche, in der hier endet;
- `gleichzeitig` — die Wochen überschneiden sich (Jan, 27.11.2026: als Versuch);
- `abgestimmt` — nichts zu prüfen.

Liegen die Kapitel in verschiedenen Stufen, entscheiden die Stufen, auch ohne Plan („Kl. 7 vor
Kl. 8“). In derselben Stufe ohne Wochen auf beiden Seiten bleibt es offen. Die Prüfung warnt nur.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

EINGEHALTEN, VERLETZT, OFFEN = "eingehalten", "verletzt", "offen"
#: Gründe für `offen`
HIER_OHNE_LAGE, DORT_OHNE_LAGE, OHNE_WOCHEN = "hier_ohne_lage", "dort_ohne_lage", "ohne_wochen"


@dataclass(frozen=True)
class Spanne:
    stufe_von: int
    stufe_bis: int
    #: Unterrichtswoche im Schuljahr (aus dem Jahresverlaufsplan), sonst None
    von_woche: Optional[int] = None
    bis_woche: Optional[int] = None
    beginn: Optional[date] = None
    ende: Optional[date] = None
    #: aus einem Entwurf des Jahresverlaufsplans
    entwurf: bool = False

    @property
    def mit_wochen(self) -> bool:
        return self.von_woche is not None and self.bis_woche is not None

    @property
    def von(self) -> tuple[int, int]:
        return (self.stufe_von, self.von_woche or 0)

    @property
    def bis(self) -> tuple[int, int]:
        return (self.stufe_bis, self.bis_woche or 0)


@dataclass(frozen=True)
class Ergebnis:
    ergebnis: str
    grund: Optional[str] = None


def kapitel_spannen(abschnitte: list[dict], lage_abschnitte: list[dict], stufe: int, *,
                    kapitel_von_sequenz: Optional[dict[str, str]] = None, entwurf: bool = False) -> dict[str, Spanne]:
    """Je Kapitel eines Jahresverlaufsplans seine Spanne. `abschnitte` aus `metadata.abschnitte`,
    `lage_abschnitte` aus `lage(...)` (gleiche Reihenfolge; Schlüssel `von_woche`, `bis_woche`,
    `beginn`, `ende`). Bei sequenzgenauer Planung bildet `kapitel_von_sequenz` die Sequenzen auf
    ihre Kapitel ab. Abschnitte ganz hinter dem Schuljahr (`beginn` None) zählen nicht."""
    gesammelt: dict[str, list] = {}
    for a, l in zip(abschnitte, lage_abschnitte):
        if a.get("puffer") or l.get("beginn") is None:
            continue
        ids = set(a.get("kapitel_ids") or [])
        for sid in a.get("sequenz_ids") or []:
            if (kid := (kapitel_von_sequenz or {}).get(str(sid))):
                ids.add(kid)
        for kid in ids:
            gesammelt.setdefault(str(kid), []).append(l)
    aus = {}
    for kid, ls in gesammelt.items():
        enden = [x["ende"] for x in ls if x.get("ende")]
        aus[kid] = Spanne(stufe, stufe, min(x["von_woche"] for x in ls), max(x["bis_woche"] for x in ls),
                          min(x["beginn"] for x in ls), max(enden) if enden else None, entwurf)
    return aus


def vereinen(spannen: Iterable[Spanne]) -> Optional[Spanne]:
    """Mehrere Spannen eines Kapitels (es steht in den Plänen zweier Stufen) zu einer."""
    s = sorted(spannen, key=lambda x: x.von)
    if not s:
        return None
    erst, letzt = s[0], max(s, key=lambda x: x.bis)
    mit = all(x.mit_wochen for x in s)
    return Spanne(erst.stufe_von, letzt.stufe_bis, erst.von_woche if mit else None, letzt.bis_woche if mit else None,
                  erst.beginn, letzt.ende, any(x.entwurf for x in s))


def _vergleich(hier: Spanne, dort: Spanne) -> Optional[str]:
    """`frueher`, `spaeter`, `beruehrt_vorn` (dort endet in der Woche, in der hier beginnt),
    `beruehrt_hinten`, `ueberschneidung` — oder None, wenn es sich ohne Wochen nicht sagen lässt."""
    if hier.mit_wochen and dort.mit_wochen:
        if dort.bis < hier.von:
            return "frueher"
        if dort.von > hier.bis:
            return "spaeter"
        if dort.bis == hier.von and dort.von < hier.von:
            return "beruehrt_vorn"
        if dort.von == hier.bis and dort.bis > hier.bis:
            return "beruehrt_hinten"
        return "ueberschneidung"
    if dort.stufe_bis < hier.stufe_von:
        return "frueher"
    if dort.stufe_von > hier.stufe_bis:
        return "spaeter"
    return None


def pruefe(art: str, hier: Optional[Spanne], dort: Optional[Spanne]) -> Optional[Ergebnis]:
    """Ob die Absprache mit dieser Art eingehalten ist; None bei `abgestimmt`."""
    if art not in ("vorher", "nachher", "gleichzeitig"):
        return None
    if hier is None:
        return Ergebnis(OFFEN, HIER_OHNE_LAGE)
    if dort is None:
        return Ergebnis(OFFEN, DORT_OHNE_LAGE)
    v = _vergleich(hier, dort)
    if v is None:
        return Ergebnis(OFFEN, OHNE_WOCHEN)
    if art == "vorher":
        return Ergebnis(EINGEHALTEN if v in ("frueher", "beruehrt_vorn") else VERLETZT)
    if art == "nachher":
        return Ergebnis(EINGEHALTEN if v in ("spaeter", "beruehrt_hinten") else VERLETZT)
    return Ergebnis(EINGEHALTEN if v in ("ueberschneidung", "beruehrt_vorn", "beruehrt_hinten") else VERLETZT)


def beschreibung(s: Optional[Spanne]) -> Optional[str]:
    """„Kl. 8, KW 38–40“ (mit Plan) oder „Kl. 7/8“ (nur Stufen)."""
    if s is None:
        return None
    stufen = f"Kl. {s.stufe_von}" if s.stufe_von == s.stufe_bis else f"Kl. {s.stufe_von}/{s.stufe_bis}" \
        if s.stufe_bis == s.stufe_von + 1 else f"Kl. {s.stufe_von}–{s.stufe_bis}"
    if not (s.mit_wochen and s.beginn):
        return stufen
    kw_von = s.beginn.isocalendar()[1]
    kw_bis = (s.ende or s.beginn).isocalendar()[1]
    kw = f"KW {kw_von}" if kw_von == kw_bis else f"KW {kw_von}–{kw_bis}"
    return f"{stufen}, {kw}{' (Entwurf)' if s.entwurf else ''}"
