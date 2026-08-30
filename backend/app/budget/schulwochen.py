"""Unterrichtswochen eines Schuljahres — der Takt der Budget-Zuteilung.

Das Budget wird nicht monatlich zurückgesetzt, sondern wächst je Unterrichtswoche
(``Budget-Wochenmodell-Plan.md``). Dieses Modul beantwortet, **welche Wochen
Unterrichtswochen sind, wie viele es gibt und in welcher wir gerade stehen**.

Grundlage ist ``config/school_year.yaml`` über ``app.planning.calendar``. Ferien,
Feiertage und unterrichtsfreie Tage stehen dort gepflegt — teils von Hand, teils aus dem
Ferienimport (UP-8). Die Wochenzahl wird daraus **abgeleitet, nicht geschätzt**.

── Eine Woche, ein Betrag ───────────────────────────────────────────────────────────

Jede Unterrichtswoche bekommt denselben Betrag: den, der in der Admin-Oberfläche je
Jahrgang eingetragen ist. Die Jahressumme ist damit schlicht ``Wochenbetrag × Anzahl
Unterrichtswochen`` — und genau das kann die Oberfläche beim Eintragen anzeigen.

Angebrochene Randwochen bekommen denselben Betrag wie volle. Das ist Absicht: Die harte
Zusage ist die **Jahressumme**, und die stimmt exakt. Eine Woche anteilig nach ihren
Schultagen zu bezahlen würde eine zweite Einheit einführen — den Schultag —, die niemand
konfiguriert und niemand sieht; in der ersten Schulwoche käme dann ein Betrag heraus, den
die Administration nie eingetragen hat.

Für die Pflege der Konfiguration folgt daraus eine angenehme Robustheit: Ein vergessener
Feiertag mitten in einer vollen Woche ändert am Budget **nichts**. Erst wenn eine ganze
Woche die Seite wechselt — ein fehlender Ferienzeitraum, oder der einzige Schultag einer
Woche ist ein nicht eingetragener Feiertag —, verschiebt sich die Jahressumme. Das ist der
Prüfpunkt beim Schuljahreswechsel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from app.planning.calendar import SchoolYearConfig, is_schoolday, load_school_year


@dataclass(frozen=True)
class Unterrichtswoche:
    """Eine Kalenderwoche, in der mindestens ein Unterrichtstag liegt."""

    index: int      # 1-basiert, laufend im Schuljahr — der Zähler des Zuteilungslaufs
    montag: date    # Wochenbeginn (ISO), auch wenn er selbst kein Schultag ist
    tage: int       # Unterrichtstage in dieser Woche, 1–5.
                    # Nur zur Anzeige und Fehlersuche (erkennt angebrochene Wochen) —
                    # der zugeteilte Betrag hängt NICHT daran, siehe Modul-Docstring.

    @property
    def iso(self) -> tuple[int, int]:
        """(ISO-Jahr, Kalenderwoche) — für Anzeige und Protokoll."""
        jahr, kw, _ = self.montag.isocalendar()
        return jahr, kw


def _cfg(cfg: Optional[SchoolYearConfig]) -> SchoolYearConfig:
    return cfg or load_school_year()


def unterrichtswochen(cfg: Optional[SchoolYearConfig] = None) -> list[Unterrichtswoche]:
    """Alle Unterrichtswochen des Schuljahres, in zeitlicher Reihenfolge.

    Wochen ganz ohne Unterricht (Ferien) kommen nicht vor — sie bekommen dadurch weder
    einen Index noch eine Zuteilung. Das ist der Grund, warum die Ferienfrage im
    Wochenmodell gar nicht erst gestellt werden muss.
    """
    c = _cfg(cfg)
    tage_je_montag: dict[date, int] = {}

    tag = c.beginn
    while tag <= c.ende:
        if is_schoolday(tag, c):
            montag = tag - timedelta(days=tag.weekday())
            tage_je_montag[montag] = tage_je_montag.get(montag, 0) + 1
        tag += timedelta(days=1)

    return [
        Unterrichtswoche(index=i, montag=montag, tage=tage_je_montag[montag])
        for i, montag in enumerate(sorted(tage_je_montag), start=1)
    ]


def anzahl_unterrichtswochen(cfg: Optional[SchoolYearConfig] = None) -> int:
    """Wie oft im Schuljahr zugeteilt wird — der Faktor der Jahressumme.

    ``Wochenbetrag × diese Zahl`` ist die Summe, auf die sich die Schule festlegt.
    """
    return len(unterrichtswochen(cfg))


def woche_am(d: date, cfg: Optional[SchoolYearConfig] = None) -> Optional[Unterrichtswoche]:
    """Die Unterrichtswoche, in der ``d`` liegt — oder None in Ferien und außerhalb.

    ``d`` selbst muss kein Schultag sein: Ein Samstag gehört zur Woche davor, solange in
    ihr unterrichtet wurde. Sonst bekäme ein Lauf, der am Wochenende ausgeführt wird,
    keine Woche zugeordnet.
    """
    montag = d - timedelta(days=d.weekday())
    for w in unterrichtswochen(cfg):
        if w.montag == montag:
            return w
    return None


def naechste_woche_nach(
    d: date, cfg: Optional[SchoolYearConfig] = None
) -> Optional[Unterrichtswoche]:
    """Die nächste Unterrichtswoche, die **nach** der Woche von ``d`` beginnt.

    Beantwortet die Frage, die Nutzer:innen tatsächlich stellen: *Wann kommt wieder etwas
    dazu?* In Ferien ist das die erste Woche danach, am Schuljahresende ``None``.

    Bewusst allein aus dem Kalender, ohne den Buchungsstand: Die Aussage ist „an diesem Tag
    stockt die Plattform auf", nicht „für dich persönlich". Wäre ein Lauf ausgefallen, käme
    das Guthaben früher — eine zu späte Angabe enttäuscht niemanden, eine zu frühe schon.
    """
    montag = d - timedelta(days=d.weekday())
    for w in unterrichtswochen(cfg):
        if w.montag > montag:
            return w
    return None


def wochen_bis(d: date, cfg: Optional[SchoolYearConfig] = None) -> list[Unterrichtswoche]:
    """Alle Unterrichtswochen, die am Stichtag begonnen haben (einschließlich seiner).

    Das ist die Liste, gegen die der Zuteilungslauf abgleicht: Alles hier, was noch nicht
    gebucht ist, wird nachgeholt — auch wenn ein Lauf ausgefallen ist.
    """
    montag = d - timedelta(days=d.weekday())
    return [w for w in unterrichtswochen(cfg) if w.montag <= montag]
