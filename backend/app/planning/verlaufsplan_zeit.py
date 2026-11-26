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
  Übersicht der Vorlage;
- für die Ablaufleiste (zweiter Durchgang): den Montag jeder Unterrichtswoche (Monatsachse,
  „heute“), die Ferien als Lücken und die Woche, mit der das 2. Halbjahr beginnt.

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
    stunden: Optional[float] = None

    @property
    def lang(self) -> bool:
        return self.wochen > RICHTGROESSE_WOCHEN


@dataclass
class Sequenzbilanz:
    sequenz_id: str
    titel: Optional[str]
    soll: Optional[int]
    geplant: Optional[float]
    wochen: float


@dataclass
class Kapitelbilanz:
    kapitel_id: str
    titel: Optional[str]
    soll: Optional[int]
    # Geplante Stunden; ein Abschnitt mit mehreren Kapiteln teilt seine Stunden gleich auf.
    geplant: Optional[float]
    wochen: float
    # Bei sequenzgenauer Planung (BD Schritt 7): die Sequenzen des Kapitels, aufklappbar
    sequenzen: list[Sequenzbilanz] = field(default_factory=list)


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
    # Bei sequenzgenauer Planung: Sequenzen, die kein Abschnitt nennt
    sequenzen_ohne_abschnitt: list[str] = field(default_factory=list)
    # Für die Ablaufleiste: die Unterrichtswochen, die Ferien zwischen ihnen und die erste Woche
    # des 2. Halbjahrs (None, wenn es keine gibt)
    wochen: list[Unterrichtswoche] = field(default_factory=list)
    ferien: list[Ferienmarke] = field(default_factory=list)
    halbjahr_ab_woche: Optional[int] = None

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


def halbjahr_ab_woche(cfg: SchoolYearConfig, wochen: Optional[list[Unterrichtswoche]] = None) -> Optional[int]:
    """Die Unterrichtswoche, in der das 2. Halbjahr beginnt — die erste, deren Freitag nicht vor
    dem Wechsel liegt. Fällt der Wechsel in Ferien, die nächste Woche danach."""
    wochen = wochen if wochen is not None else unterrichtswochen(cfg)
    return next((w.index for w in wochen if w.montag + timedelta(days=4) >= cfg.halbjahreswechsel), None)


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
    wochenstunden: Optional[float] = None,
    kapitel: Iterable[dict] = (),
    planungsart: str = "kapitel",
) -> Planlage:
    """Legt die Abschnitte auf den Kalender des Schuljahrs.

    `abschnitte`: in Planreihenfolge, je `{id, titel, wochen, kapitel_ids, sequenz_ids, notiz}`;
    gelesen werden `id`, `wochen` und das Bezugsfeld der Planungsart.
    `kapitel`: die Kapitel des Curriculums der Stufe, je `{id, titel, std, sequenzen}` — für die
    Bilanz und den Hinweis auf Kapitel (und Sequenzen) ohne Abschnitt.
    `planungsart`: `kapitel` oder `sequenz` (BD Schritt 7).
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
        wochen=wochen,
        # Ferien nach der letzten Woche (Sommer) sind keine Lücke im Plan
        ferien=[m for m in marken if m.nach_woche < n],
        halbjahr_ab_woche=halbjahr_ab_woche(cfg, wochen),
        **(_sequenzbilanz(abschnitte, lagen, list(kapitel), wochenstunden) if planungsart == "sequenz"
           else _bilanz(abschnitte, lagen, list(kapitel), wochenstunden)),
    )


def _bilanz(abschnitte: list[dict], lagen: list[AbschnittLage], kapitel: list[dict],
            wochenstunden: Optional[float]) -> dict:
    """Stunden und Wochen je Kapitel; ein Abschnitt teilt sich gleich auf seine Kapitel auf."""
    wochen_je = _anteile(abschnitte, lagen, "kapitel_ids")

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


def _anteile(abschnitte: list[dict], lagen: list[AbschnittLage], feld: str) -> dict[str, float]:
    """Wochen je genannter Einheit; ein Abschnitt teilt sich gleich auf seine Einheiten auf."""
    wochen_je: dict[str, float] = {}
    for a, l in zip(abschnitte, lagen):
        ids = list(dict.fromkeys(str(k) for k in (a.get(feld) or [])))
        for k in ids:
            wochen_je[k] = wochen_je.get(k, 0) + l.wochen / len(ids)
    return wochen_je


def _sequenzbilanz(abschnitte: list[dict], lagen: list[AbschnittLage], kapitel: list[dict],
                   wochenstunden: Optional[float]) -> dict:
    """Bilanz bei sequenzgenauer Planung: je Sequenz, zusammengefasst je Kapitel.

    Soll eines Kapitels ist die Summe der Sequenz-Stunden, wo Sequenzen welche tragen; sonst die
    Stunden des Kapitels. Sequenzen, die nicht (mehr) im Curriculum stehen, erscheinen einzeln
    am Ende, ohne Titel — wie fremde Kapitel bei kapitelgenauer Planung.
    """
    wochen_je = _anteile(abschnitte, lagen, "sequenz_ids")
    stunden = (lambda w: round(w * wochenstunden, 1) if wochenstunden else None)
    bilanz, bekannt, ohne_kapitel = [], set(), []
    for k in kapitel:
        seqs = []
        for sq in k.get("sequenzen") or []:
            sid = str(sq["id"])
            bekannt.add(sid)
            w = wochen_je.get(sid, 0)
            seqs.append(Sequenzbilanz(sequenz_id=sid, titel=sq.get("titel"), soll=sq.get("std"),
                                      geplant=stunden(w), wochen=round(w, 2)))
        std_seq = [x.soll for x in seqs if x.soll is not None]
        w_kap = sum(wochen_je.get(x.sequenz_id, 0) for x in seqs)
        if w_kap == 0:
            ohne_kapitel.append(str(k["id"]))
        bilanz.append(Kapitelbilanz(
            kapitel_id=str(k["id"]), titel=k.get("titel"),
            soll=sum(std_seq) if std_seq else k.get("std"),
            geplant=stunden(w_kap), wochen=round(w_kap, 2), sequenzen=seqs,
        ))
    for sid, w in wochen_je.items():
        if sid not in bekannt:
            bilanz.append(Kapitelbilanz(kapitel_id=sid, titel=None, soll=None, geplant=stunden(w),
                                        wochen=round(w, 2)))
    return {
        "kapitel": bilanz,
        "kapitel_ohne_abschnitt": ohne_kapitel,
        "sequenzen_ohne_abschnitt": [x.sequenz_id for b in bilanz for x in b.sequenzen if x.wochen == 0],
    }

