"""Einheiten aus dem Jahresverlaufsplan vorbelegen — die Vorschau (BD Teil B, Schritt 3).

Rein, ohne Datenbank: Aus den Abschnitten des Plans, seiner Lage im Kalender, den Terminen der
Gruppe und ihren vorhandenen Einheiten entsteht je Abschnitt ein Vorschlag. Angelegt wird in
Schritt 4 genau das, was diese Funktion vorschlägt.

Regeln (Jan, 26.11.2026):

- **FB3:** je Abschnitt eine Einheit. Titel = Thema des Abschnitts (ohne Thema: der Titel des
  Kapitels, sonst „Abschnitt n“). Kapitel = das erste Kapitel des Abschnitts, bei sequenzgenauer
  Planung das Kapitel der ersten Sequenz. Die Sequenzen, weitere Kapitel und die Notiz stehen in
  der Beschreibung. **Puffer** bekommen keine Einheit.
- **FB4:** belegt werden die **freien Unterrichtstermine** in den Wochen des Abschnitts — Kategorie
  Unterricht, ohne Einheit, ohne Stunde, nicht angepinnt. Prüfungen, Ausfall und schon belegte
  Termine bleiben, wie sie sind. Ein freier Text (`thema`) am Termin bleibt stehen und hindert nicht.
- **FB5:** nichts wird überschrieben. Ein Abschnitt wird übersprungen, wenn sein Kapitel in diesem
  Schuljahr schon eine Einheit der Gruppe hat — oder wenn aus genau diesem Abschnitt schon eine
  Einheit angelegt wurde (`metadata.aus_verlaufsplan.abschnitt_id`; so legt ein zweiter Lauf nichts
  doppelt an, auch nicht bei Abschnitten ohne Kapitel). Einheiten **aus demselben Plan** zählen für
  die Kapitelprüfung nicht (das regelt `abschnitt_id`): Nennen zwei Abschnitte dasselbe Kapitel,
  bekommt jeder seine Einheit (FB3) — gleich, ob in einem Lauf oder nacheinander.

Eigene Festlegungen dieses Schritts (für Jan vermerkt):

- Termine vor ``heute`` werden nicht belegt — ein vergangener freier Termin ist kein Platz für
  neuen Unterricht. Liegt ein Abschnitt **ganz** in der Vergangenheit, wird er übersprungen
  (`vorbei`); ebenso ein Abschnitt ganz hinter dem Schuljahresende (`nach_schuljahresende`).
- Ein Kapitel, das nicht mehr veröffentlicht ist (ersetztes Curriculum), wird durch seinen
  **Nachfolger** ersetzt (`kopie_von` am Kapitel der neuen Fassung) — dorthin sind beim Veröffentlichen
  auch die Einheiten umgezogen. Ohne Nachfolger entsteht die Einheit ohne Kapitel (`kapitel_fehlt`).
  Die Kapitelprüfung (FB5) vergleicht altes und neues Kapitel.
- Sind alle künftigen Unterrichtstermine seiner Wochen schon belegt, wird er übersprungen (`belegt`).
- Hat ein Abschnitt **schon begonnen** und keinen Termin mehr ab heute, ist er vorbei — auch wenn
  er gar keine Termine hat (die Gruppe hat ihre Termine erst ab jetzt; gefunden mit der Messung
  zu 0.61). Liegt er ganz in der Zukunft und hat keine Termine (etwa weil das 2. Halbjahr noch
  nicht erzeugt ist), entsteht die Einheit trotzdem, mit dem Hinweis `ohne_termine`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

#: Gründe, aus denen ein Abschnitt keine Einheit bekommt.
PUFFER, KAPITEL_VORHANDEN, SCHON_ANGELEGT = "puffer", "kapitel_vorhanden", "schon_angelegt"
VORBEI, NACH_SCHULJAHRESENDE = "vorbei", "nach_schuljahresende"
#: Alle künftigen Unterrichtstermine der Wochen sind schon belegt — etwa von Hand, aus einem früheren
#: Plan oder von einer anderen Einheit. Dann gibt es nichts zu belegen, und eine Einheit wäre doppelt.
BELEGT = "belegt"

FREI_KATEGORIE = "unterricht"


@dataclass
class Vorschlag:
    index: int
    nr: int
    abschnitt_id: Optional[str]
    titel: str
    wochen: str
    anlegen: bool
    grund: Optional[str] = None
    kapitel_id: Optional[str] = None
    kapitel_titel: Optional[str] = None
    #: Das Kapitel des Abschnitts ist nicht mehr veröffentlicht — die Einheit bleibt ohne Kapitel.
    kapitel_fehlt: bool = False
    beschreibung: str = ""
    slot_ids: list = field(default_factory=list)
    #: Unterrichtstermine in den Wochen des Abschnitts, die schon belegt sind (zur Auskunft).
    belegt: int = 0
    #: Die Wochen haben (noch) keine Termine der Gruppe — die Einheit entsteht ohne Stunden.
    ohne_termine: bool = False

    @property
    def stunden(self) -> int:
        return len(self.slot_ids)


def _montag(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _datum(wert) -> date:
    return wert if isinstance(wert, date) else date.fromisoformat(str(wert))


def ist_frei(slot) -> bool:
    return (slot.kategorie == FREI_KATEGORIE and slot.ue_node_id is None
            and slot.stunde_node_id is None and not slot.pinned)


def _wochentext(von: int, bis: int) -> str:
    return f"Woche {von}" if von == bis else f"Woche {von}–{bis}"


def vorschau(
    abschnitte: list[dict],
    lage: dict,
    *,
    planungsart: str,
    kapitel_von: dict[str, str],
    titel: dict[str, str],
    kapitel_aktiv: set[str],
    slots: Iterable,
    kapitel_mit_einheit: set[str],
    angelegte_abschnitte: set[str],
    heute: date,
    nachfolger: dict[str, str] | None = None,
) -> list[Vorschlag]:
    """Je Abschnitt ein :class:`Vorschlag`, in der Reihenfolge des Plans.

    - `lage`: die Lage wie in `vp._lage_dict` (`abschnitte` mit `von_woche`/`bis_woche`, `wochen` mit
      Montag) — so rechnet die Vorschau mit denselben Wochen wie Ablaufleiste und Planer.
    - `kapitel_von`: Sequenz → Kapitel; `titel`: Titel je Kapitel- und Sequenz-ID.
    - `kapitel_aktiv`: die Kapitel, die heute veröffentlicht sind.
    - `slots`: die Termine der Gruppe (Attribute wie `LessonSlot`).
    - `kapitel_mit_einheit`: Kapitel, die in diesem Schuljahr schon eine Einheit der Gruppe haben —
      ohne die Einheiten, die aus diesem Plan entstanden sind.
    - `nachfolger`: archiviertes Kapitel → sein veröffentlichter Nachfolger.
    - `angelegte_abschnitte`: Abschnitt-IDs, aus denen schon eine Einheit entstanden ist.
    """
    montag_von = {w["nr"]: _datum(w["montag"]) for w in lage.get("wochen", [])}
    je_montag: dict[date, list] = {}
    for s in sorted(slots, key=lambda s: (s.date, s.start_period or 0)):
        je_montag.setdefault(_montag(s.date), []).append(s)

    nachfolger = nachfolger or {}
    sequenzgenau = planungsart == "sequenz"
    ergebnis: list[Vorschlag] = []
    for i, a in enumerate(abschnitte):
        lg = lage["abschnitte"][i]
        von, bis = lg["von_woche"], lg["bis_woche"]
        v = Vorschlag(index=i, nr=i + 1, abschnitt_id=a.get("id"), titel=(a.get("titel") or "").strip(),
                      wochen=_wochentext(von, bis), anlegen=False)
        ergebnis.append(v)
        if a.get("puffer"):
            v.titel = v.titel or "Puffer"
            v.grund = PUFFER
            continue

        # Kapitel und Beschreibung
        sequenzen = [str(x) for x in a.get("sequenz_ids") or []] if sequenzgenau else []
        if sequenzgenau:
            kapitel = list(dict.fromkeys(kapitel_von[x] for x in sequenzen if x in kapitel_von))
        else:
            kapitel = [str(x) for x in a.get("kapitel_ids") or []]
        erstes = kapitel[0] if kapitel else None
        gilt = erstes if erstes in kapitel_aktiv else nachfolger.get(erstes) if erstes else None
        if gilt:
            v.kapitel_id, v.kapitel_titel = gilt, titel.get(gilt)
        elif erstes:
            v.kapitel_fehlt = True
        v.titel = v.titel or v.kapitel_titel or f"Abschnitt {v.nr}"
        zeilen = [f"Aus dem Jahresverlaufsplan der Fachschaft: Abschnitt {v.nr}, {v.wochen}."]
        if sequenzen:
            zeilen.append("Lernsequenzen: " + ", ".join(titel.get(x, "nicht mehr im Curriculum") for x in sequenzen))
        weitere = [k for k in kapitel if k not in (erstes if v.kapitel_id else None, v.kapitel_id)]
        if weitere:
            zeilen.append(("Kapitel: " if not v.kapitel_id else "Weitere Kapitel: ")
                          + ", ".join(titel.get(k, "nicht mehr im Curriculum") for k in weitere))
        if (a.get("notiz") or "").strip():
            zeilen.append("Notiz: " + a["notiz"].strip())
        v.beschreibung = "\n".join(zeilen)

        # Termine der Wochen
        montage = [montag_von[n] for n in range(von, bis + 1) if n in montag_von]
        termine = [s for m in montage for s in je_montag.get(m, []) if s.kategorie == FREI_KATEGORIE]
        v.slot_ids = [s.id for s in termine if ist_frei(s) and s.date >= heute]
        v.belegt = sum(1 for s in termine if not ist_frei(s))
        v.ohne_termine = bool(montage) and not termine

        if v.abschnitt_id and v.abschnitt_id in angelegte_abschnitte:
            v.grund = SCHON_ANGELEGT
        elif {erstes, v.kapitel_id} & kapitel_mit_einheit - {None}:
            v.grund = KAPITEL_VORHANDEN
        elif not montage:
            v.grund = NACH_SCHULJAHRESENDE
        elif ((montage[0] <= heute and not any(s.date >= heute for s in termine))
              or montage[-1] + timedelta(days=4) < heute):
            v.grund = VORBEI
        elif not v.slot_ids and any(s.date >= heute for s in termine):
            v.grund = BELEGT
        else:
            v.anlegen = True
        if not v.anlegen:
            v.slot_ids = []
    return ergebnis
