"""Zeitrechnung des Jahresverlaufsplans (Päckchen BD, Schritt 3) — ohne Datenbank.

Ein Verlaufsplan speichert nur **Reihenfolge und Dauer** seiner Abschnitte (BD F1). Wann ein
Abschnitt liegt, ergibt sich aus dem Kalender des Schuljahrs: Abschnitt 1 beginnt in der ersten
Unterrichtswoche, jeder weitere in der Woche nach dem vorigen. Ferienwochen zählen nicht
(:func:`app.budget.schulwochen.unterrichtswochen`), also überspringt der Plan sie von selbst.
Ändert sich ein Ferientermin, stimmt der Plan damit ohne Zutun.

Diese Datei rechnet daraus, was die Oberfläche und später der Assistent zeigen:

- je Abschnitt die Unterrichtswochen von–bis, den ersten und letzten Schultag, die Ferien, über
  die er reicht, die Ferien direkt danach, ob der Halbjahreswechsel in ihm liegt, seine Stunden;
- für den Plan freie Wochen am Ende oder den Überhang über das Schuljahr hinaus;
- die Stundenbilanz je Kapitel (Soll aus `std`, geplant aus Wochen × Wochenstunden);
- die Abschnitte zwischen den Ferien — für den Knopf „bis zu den Ferien“ (BD F3) und die
  Übersicht der Vorlage.

**Ganze Wochen.** Eine Woche mit zwei Unterrichtstagen zählt wie eine volle, auch in der
Stundenbilanz (Wochen × Wochenstunden). Genauer ginge es nur mit dem Stundenplan der Gruppe —
den hat ein Plan der Fachschaft nicht. Dieselbe Regel gilt im Budget (`schulwochen.py`).

**6 Wochen sind die Richtgröße, keine Grenze** (BD F2): Ein längerer Abschnitt wird gerechnet
wie jeder andere und nur als `lang` gekennzeichnet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from app.budget.schulwochen import Unterrichtswoche, unterrichtswochen
from app.planning.calendar import SchoolYearConfig, is_schoolday

#: Ab dieser Dauer heißt ein Abschnitt „lang“ — ein Hinweis, keine Ablehnung (BD F2).
RICHTGROESSE_WOCHEN = 6
SCHULJAHRESENDE = "Schuljahresende"


@dataclass(frozen=True)
class Ferienmarke:
    """Ferien zwischen zwei Unterrichtswochen: Sie beginnen nach Woche `nach_woche`."""

    name: str
    von: date
    bis: date
    nach_woche: int


@dataclass(frozen=True)
class Ferienabschnitt:
    """Unterrichtswochen zwischen zwei Ferien (oder Schuljahresbeginn/-ende)."""

    von_woche: int
    bis_woche: int
    endet_mit: str          # Name der folgenden Ferien oder „Schuljahresende“

    @property
    def wochen(self) -> int:
        return self.bis_woche - self.von_woche + 1


@dataclass
class AbschnittLage:
    id: Optional[str]
    nr: int
    wochen: int
    von_woche: int
    bis_woche: int
    # Erster und letzter Schultag; None, wenn der Abschnitt ganz hinter dem Schuljahr liegt.
    beginn: Optional[date]
    ende: Optional[date]
    ueber_ferien: list[str] = field(default_factory=list)
    vor_ferien: Optional[str] = None
    halbjahreswechsel: bool = False
    # Wochen, die über das Schuljahr hinausreichen
    ausserhalb: int = 0
    stunden: Optional[int] = None

    @property
    def lang(self) -> bool:
        return self.wochen > RICHTGROESSE_WOCHEN


@dataclass
class Kapitelbilanz:
    kapitel_id: str
    titel: Optional[str]
    soll: Optional[int]
    # Geplante Stunden; ein Abschnitt mit mehreren Kapiteln teilt seine Stunden gleich auf.
    geplant: Optional[float]
    wochen: float


@dataclass
class Planlage:
    schuljahr: str
    unterrichtswochen: int
    belegt: int
    abschnitte: list[AbschnittLage]
    ferienabschnitte: list[Ferienabschnitt]
    kapitel: list[Kapitelbilanz]
    # Kapitel des Curriculums, die kein Abschnitt nennt (BD F5)
    kapitel_ohne_abschnitt: list[str]

    @property
    def frei(self) -> int:
        return max(0, self.unterrichtswochen - self.belegt)

    @property
    def ueberhang(self) -> int:
        return max(0, self.belegt - self.unterrichtswochen)


# ── Kalender ──────────────────────────────────────────────────────────────────


def _schultage(w: Unterrichtswoche, cfg: SchoolYearConfig) -> list[date]:
    return [d for d in (w.montag + timedelta(days=i) for i in range(5)) if is_schoolday(d, cfg)]


def ferienmarken(cfg: SchoolYearConfig, wochen: Optional[list[Unterrichtswoche]] = None) -> list[Ferienmarke]:
    """Die Ferien des Schuljahrs, je mit der Unterrichtswoche, nach der sie beginnen.

    Beginnen Ferien mitten in der Woche, zählt diese Woche davor — sie hat Unterricht. Ferien
    vor der ersten Unterrichtswoche fallen weg; sie liegen vor dem Plan.
    """
    wochen = wochen if wochen is not None else unterrichtswochen(cfg)
    marken = []
    for f in sorted(cfg.ferien, key=lambda f: f.von):
        vorher = [w.index for w in wochen if w.montag < f.von]
        if vorher:
            marken.append(Ferienmarke(name=f.name, von=f.von, bis=f.bis, nach_woche=vorher[-1]))
    return marken


def ferienabschnitte(cfg: SchoolYearConfig, wochen: Optional[list[Unterrichtswoche]] = None) -> list[Ferienabschnitt]:
    """Das Schuljahr in Abschnitte zwischen den Ferien geteilt."""
    wochen = wochen if wochen is not None else unterrichtswochen(cfg)
    if not wochen:
        return []
    aus, start = [], 1
    for m in ferienmarken(cfg, wochen):
        if m.nach_woche >= start:
            aus.append(Ferienabschnitt(von_woche=start, bis_woche=m.nach_woche, endet_mit=m.name))
            start = m.nach_woche + 1
    if start <= len(wochen):
        aus.append(Ferienabschnitt(von_woche=start, bis_woche=len(wochen), endet_mit=SCHULJAHRESENDE))
    return aus


def wochen_bis_zu_den_ferien(von_woche: int, cfg: SchoolYearConfig,
                             wochen: Optional[list[Unterrichtswoche]] = None) -> int:
    """Wie viele Wochen ein Abschnitt ab `von_woche` dauert, der an den nächsten Ferien endet
    (Knopf „bis zu den Ferien“, BD F3). Hinter dem Schuljahr: 1."""
    for a in ferienabschnitte(cfg, wochen):
        if a.von_woche <= von_woche <= a.bis_woche:
            return a.bis_woche - von_woche + 1
    return 1


# ── Plan ──────────────────────────────────────────────────────────────────────


def lage(
    abschnitte: Iterable[dict],
    cfg: SchoolYearConfig,
    *,
    wochenstunden: Optional[int] = None,
    kapitel: Iterable[dict] = (),
) -> Planlage:
    """Legt die Abschnitte auf den Kalender des Schuljahrs.

    `abschnitte`: in Planreihenfolge, je `{id, titel, wochen, kapitel_ids, notiz}`; gelesen
    werden `id`, `wochen` und `kapitel_ids`.
    `kapitel`: die Kapitel des Curriculums der Stufe, je `{id, titel, std}` — für die Bilanz und
    den Hinweis auf Kapitel ohne Abschnitt.
    """
    wochen = unterrichtswochen(cfg)
    n = len(wochen)
    marken = ferienmarken(cfg, wochen)

    abschnitte = list(abschnitte)
    lagen: list[AbschnittLage] = []
    pos = 1
    for nr, a in enumerate(abschnitte, start=1):
        dauer = int(a.get("wochen") or 0)
        if dauer < 1:
            raise ValueError(f"Abschnitt {nr}: Dauer muss mindestens eine Woche sein")
        von, bis = pos, pos + dauer - 1
        pos = bis + 1

        innen_von, innen_bis = min(von, n), min(bis, n)
        beginn = ende = None
        if von <= n:
            beginn = _schultage(wochen[innen_von - 1], cfg)[0]
            ende = _schultage(wochen[innen_bis - 1], cfg)[-1]

        l = AbschnittLage(
            id=a.get("id"), nr=nr, wochen=dauer, von_woche=von, bis_woche=bis,
            beginn=beginn, ende=ende, ausserhalb=max(0, bis - max(n, von - 1)),
            stunden=dauer * wochenstunden if wochenstunden else None,
        )
        if von <= n:
            l.ueber_ferien = [m.name for m in marken if von <= m.nach_woche < innen_bis]
            l.vor_ferien = next((m.name for m in marken if m.nach_woche == innen_bis), None)
            # Beginnt der Abschnitt mit dem neuen Halbjahr, liegt der Wechsel nicht *in* ihm.
            l.halbjahreswechsel = beginn < cfg.halbjahreswechsel <= ende
        lagen.append(l)

    return Planlage(
        schuljahr=cfg.schuljahr,
        unterrichtswochen=n,
        belegt=pos - 1,
        abschnitte=lagen,
        ferienabschnitte=ferienabschnitte(cfg, wochen),
        **_bilanz(abschnitte, lagen, list(kapitel), wochenstunden),
    )


def _bilanz(abschnitte: list[dict], lagen: list[AbschnittLage], kapitel: list[dict],
            wochenstunden: Optional[int]) -> dict:
    """Stunden und Wochen je Kapitel; ein Abschnitt teilt sich gleich auf seine Kapitel auf."""
    wochen_je: dict[str, float] = {}
    for a, l in zip(abschnitte, lagen):
        ids = list(dict.fromkeys(str(k) for k in (a.get("kapitel_ids") or [])))
        for k in ids:
            wochen_je[k] = wochen_je.get(k, 0) + l.wochen / len(ids)

    bekannt = {str(k["id"]): k for k in kapitel}
    reihenfolge = [str(k["id"]) for k in kapitel] + [k for k in wochen_je if k not in bekannt]
    bilanz = []
    for kid in reihenfolge:
        k = bekannt.get(kid, {})
        w = wochen_je.get(kid, 0)
        bilanz.append(Kapitelbilanz(
            kapitel_id=kid, titel=k.get("titel"), soll=k.get("std"),
            geplant=round(w * wochenstunden, 1) if wochenstunden else None,
            wochen=round(w, 2),
        ))
    return {
        "kapitel": bilanz,
        "kapitel_ohne_abschnitt": [kid for kid in bekannt if kid not in wochen_je],
    }
