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
