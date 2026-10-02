"""Hochrechnung des Schuljahresverbrauchs.

Die Schule bindet sich auf eine Jahressumme (`Wochenbetrag × Unterrichtswochen`). Ob sie
darunter bleibt, weiß im Juli jeder — dann nützt es niemandem mehr. **Der Sinn dieser
Rechnung ist, es im März zu wissen**: Zeichnet sich ab, dass nur ein Bruchteil abfließt,
kann die Schule die Wochenbeträge fürs zweite Halbjahr anheben, statt am Jahresende einen
Rest zu verwalten.

Die Hochrechnung ist bewusst **linear** — verbrauchte Wochen hoch auf alle Wochen. Etwas
Klügeres wäre Schein­genauigkeit: Der Verbrauch schwankt mit Klassenarbeitsphasen und
Projekttagen, und niemand hat Daten aus Vorjahren, an denen sich ein Saisonmuster ablesen
ließe. Was die Rechnung stattdessen liefert, ist ein ehrliches Maß für ihre eigene
Belastbarkeit: die Zahl der Wochen, auf denen sie beruht.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

#: Unter so vielen Wochen ist die Hochrechnung Rauschen — eine einzelne Projektwoche
#: verdoppelt sie. Sie wird trotzdem gezeigt, aber als unsicher gekennzeichnet: Sie ganz
#: zu verschweigen hieße, die Administration bis Weihnachten im Dunkeln zu lassen.
BELASTBAR_AB_WOCHEN = 4


@dataclass(frozen=True)
class Hochrechnung:
    verbraucht_eur: float
    wochen_vergangen: int
    wochen_gesamt: int
    #: Erwarteter Jahresverbrauch. ``None``, solange keine Woche vergangen ist.
    erwartet_eur: Optional[float]
    #: Was die Schule zugesagt hat (Summe über alle Stufen × Nutzerzahl × Wochen).
    zugeteilt_eur: Optional[float]
    belastbar: bool

    @property
    def auslastung(self) -> Optional[float]:
        """Erwarteter Verbrauch als Anteil der Zusage (0–1+). ``None`` ohne Zusage."""
        if not self.zugeteilt_eur or self.erwartet_eur is None:
            return None
        return self.erwartet_eur / self.zugeteilt_eur


def hochrechnen(
    *,
    verbraucht_eur: float,
    wochen_vergangen: int,
    wochen_gesamt: int,
    zugeteilt_eur: Optional[float] = None,
) -> Hochrechnung:
    """Lineare Fortschreibung des bisherigen Verbrauchs auf das ganze Schuljahr."""
    erwartet: Optional[float] = None
    if wochen_vergangen > 0 and wochen_gesamt > 0:
        erwartet = round(verbraucht_eur / wochen_vergangen * wochen_gesamt, 2)

    return Hochrechnung(
        verbraucht_eur=round(verbraucht_eur, 2),
        wochen_vergangen=wochen_vergangen,
        wochen_gesamt=wochen_gesamt,
        erwartet_eur=erwartet,
        zugeteilt_eur=round(zugeteilt_eur, 2) if zugeteilt_eur else None,
        belastbar=wochen_vergangen >= BELASTBAR_AB_WOCHEN,
    )


# ── Verlauf: Ist gegen Soll, Woche für Woche (0.12, Paket 2, AP2) ─────────────


@dataclass(frozen=True)
class Verlaufspunkt:
    montag: date
    #: Kumulierte Zusage bis einschließlich dieser Woche.
    soll_eur: float
    #: Kumulierter Verbrauch — ``None`` für Wochen, die noch nicht begonnen haben.
    ist_eur: Optional[float]
    #: Unterrichtswoche? Ferienwochen bekommen keine Zuteilung — die Soll-Linie bleibt
    #: dort flach, der Verbrauch darf weiterlaufen.
    unterricht: bool


def verlauf(
    *,
    beginn: date,
    ende: date,
    unterrichts_montage: set[date],
    wochensumme_eur: float,
    ist_je_woche: dict[date, float],
    heute: date,
) -> list[Verlaufspunkt]:
    """Je Kalenderwoche des Schuljahres: kumulierte Zusage und kumulierter Verbrauch.

    ⚠️ **Die Soll-Linie ist eine Treppe, keine Gerade.** Sie wächst nur in
    Unterrichtswochen — genau wie die Zuteilung selbst (`accrual.py`). Eine Gerade über
    das ganze Jahr läge in den Herbst- und Weihnachtsferien über der Wirklichkeit und
    würde die Schule im Januar fälschlich beruhigen: Der Abstand zum Verbrauch sähe
    größer aus, als die Zusage tatsächlich ist.

    Die x-Achse sind deshalb **Kalenderwochen**, nicht Unterrichtswochen: Nur so sind
    die Ferien als flache Stufe überhaupt zu sehen.

    Der Verbrauch darf in den Ferien steigen — wer Guthaben angesammelt hat, kann es
    nutzen. Gezählt wird, was tatsächlich verbraucht wurde.
    """
    def montag_von(d: date) -> date:
        return d - timedelta(days=d.weekday())

    punkte: list[Verlaufspunkt] = []
    soll = 0.0
    ist = 0.0
    heute_montag = montag_von(heute)
    montag = montag_von(beginn)
    letzter = montag_von(ende)
    while montag <= letzter:
        unterricht = montag in unterrichts_montage
        if unterricht:
            soll += wochensumme_eur
        if montag <= heute_montag:
            ist += ist_je_woche.get(montag, 0.0)
            ist_wert: Optional[float] = round(ist, 2)
        else:
            ist_wert = None
        punkte.append(Verlaufspunkt(montag, round(soll, 2), ist_wert, unterricht))
        montag += timedelta(days=7)
    return punkte
