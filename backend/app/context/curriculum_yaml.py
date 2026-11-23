"""Curriculum-YAML einlesen und bereinigen (0.56, Päckchen BA Schritt 1).

Der Riegel zwischen einer Datei, die irgendwer geschrieben hat — eine Lehrkraft, ein
KI-Programm, eine andere Plattform —, und `import_curriculum_from_draft`. Er liefert ein
geprüftes `CurriculumDraftConfirmed` oder Fehler, dazu Warnungen; **jede Meldung mit der
Stelle** („Kapitel 3, Lernsequenz 2, Eintrag 1: …“), damit man sie in der Datei findet.

**Fehler** (nichts wird angelegt): kein YAML, Anker/Aliase, zu groß, falsche Typen, fehlende
Pflichtfelder, keine Kapitel. **Warnungen** (Import möglich): unbekannte Felder (übergangen),
unbekannte Verweisarten (nur der Text bleibt), entfernte Steuerzeichen.

Die Prüfungen, die die Datenbank brauchen, stehen in :func:`verweise_pruefen`; die Auflösung
von Fach, Fachplan und Kompetenzen bleibt im Import selbst (die Vorschau führt ihn aus und
rollt zurück, F4).

⚠️ **Anker und Aliase werden abgelehnt.** Auch `yaml.safe_load` expandiert sie — zehn Zeilen
mit verschachtelten Aliasen ergeben Milliarden Einträge („Billion Laughs“). Der Export erzeugt
keine, eine echte Datei braucht sie also nicht.

Das Admin-Skript `backend/scripts/import_curriculum.py` nutzt dieselbe Schicht, ohne Grenzen
(`grenzen=None`): Die Administration überträgt auch große Bestände (F10).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml
from yaml.events import AliasEvent, CollectionStartEvent, ScalarEvent

from app.context.schemas import (
    CurriculumDraftConfirmed,
    CurriculumDraftEntry,
    CurriculumDraftKapitel,
    CurriculumDraftLernsequenz,
)


@dataclass(frozen=True)
class Grenzen:
    """Obergrenzen einer Datei aus der Oberfläche oder von einem KI-Programm.

    Gemessen am größten Curriculum auf Dev (23.11.2026: 20 KB, 7 Kapitel, 24 Lernsequenzen,
    29 Einträge, längster Text 683 Zeichen). Curricula über zwei Schuljahre sind etwa doppelt
    so groß; die Grenzen lassen darüber noch gut das Vierfache Luft.
    """
    bytes: int = 200_000
    kapitel: int = 30
    lernsequenzen: int = 150
    eintraege: int = 300
    zeichen: int = 5_000      # je Textfeld
    liste: int = 50           # je Liste in einem Eintrag (ik, pk, lp, begriffe …)
    tiefe: int = 12           # Verschachtelung; das Format braucht 6


GRENZEN = Grenzen()

PFLICHT = ("schule", "fach_code", "schulart", "jahrgangsstufe", "bp_version")
FELDER_OBEN = frozenset(PFLICHT + ("fach", "fachplan_id", "bp_id", "vorwort", "rahmen", "kapitel"))
FELDER_KAPITEL = frozenset(("titel", "reihenfolge", "std", "hinweis", "konkretisierung", "lernsequenzen"))
FELDER_LS = frozenset(("bp_titel", "bp_leitidee", "reihenfolge", "std", "eintraege"))
FELDER_EINTRAG = frozenset(("ik", "ik_partiell", "pk", "konkretisierung", "hinweise", "lp", "material",
                            "begriffe", "fachmethoden"))

#: Verweise im Text: `@[Text](art:ziel)` oder `#[Text](ik:…)`. Die Kompetenznummer darf eine
#: Ebene Klammern enthalten (`3.4.3(2)`), wie im Import (`service._IK_CODE_TOKEN`).
VERWEIS = re.compile(r'([@#])\[([^\]]*)\]\(([A-Za-z_]+):((?:[^()]|\([^()]*\))*)\)')
VERWEISARTEN = frozenset(("lp", "lpa", "lb", "lba", "ik", "node"))
#: Steuerzeichen außer Tabulator und Zeilenumbruch.
_STEUER = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class _OhneAliase(yaml.SafeLoader):
    """`SafeLoader` ohne Anker und Aliase und mit begrenzter Tiefe."""

    max_tiefe = GRENZEN.tiefe

    def __init__(self, stream):
        super().__init__(stream)
        self._tiefe = 0

    def compose_node(self, parent, index):
        ereignis = self.peek_event()
        if isinstance(ereignis, AliasEvent) or (
                isinstance(ereignis, (ScalarEvent, CollectionStartEvent)) and ereignis.anchor):
            raise yaml.YAMLError("Anker und Aliase (&, *) sind nicht erlaubt.")
        if isinstance(ereignis, CollectionStartEvent):
            self._tiefe += 1
            if self._tiefe > self.max_tiefe:
                raise yaml.YAMLError("Die Datei ist zu tief verschachtelt.")
            try:
                return super().compose_node(parent, index)
            finally:
                self._tiefe -= 1
        return super().compose_node(parent, index)


@dataclass
class Pruefung:
    """Ergebnis von :func:`einlesen` und :func:`zu_entwurf`."""
    entwurf: CurriculumDraftConfirmed | None = None
    fehler: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.entwurf is not None and not self.fehler


def einlesen(roh: bytes | str, *, grenzen: Grenzen | None = GRENZEN) -> Pruefung:
    """Text einer Datei → :class:`Pruefung`. Prüft Größe, YAML, Anker, Tiefe, dann
    :func:`zu_entwurf`."""
    if isinstance(roh, str):
        roh = roh.encode("utf-8")
    if grenzen and len(roh) > grenzen.bytes:
        return Pruefung(fehler=[f"Die Datei ist zu groß ({len(roh) // 1000} KB, höchstens "
                                f"{grenzen.bytes // 1000} KB)."])
    try:
        text = roh.decode("utf-8-sig")
    except UnicodeDecodeError:
        return Pruefung(fehler=["Die Datei ist kein UTF-8-Text."])

    lader = type("_Lader", (_OhneAliase,), {"max_tiefe": grenzen.tiefe if grenzen else 100})
    try:
        daten = yaml.load(text, Loader=lader)  # noqa: S506 — SafeLoader ohne Aliase
    except yaml.YAMLError as e:
        ort = getattr(e, "problem_mark", None)
        zeile = f" (Zeile {ort.line + 1})" if ort is not None else ""
        grund = getattr(e, "problem", None) or str(e)
        return Pruefung(fehler=[f"Kein gültiges YAML{zeile}: {grund}"])
    except RecursionError:
        return Pruefung(fehler=["Die Datei ist zu tief verschachtelt."])
    if not isinstance(daten, dict):
        return Pruefung(fehler=["Die Datei muss ein Curriculum beschreiben (Felder wie `fach_code`, `kapitel`)."])
    return zu_entwurf(daten, grenzen=grenzen)


def zu_entwurf(daten: dict, bp_version_override: str | None = None, *,
               grenzen: Grenzen | None = GRENZEN) -> Pruefung:
    """Geladene Daten → :class:`Pruefung`: Struktur, Typen, Grenzen, Texte, Verweisarten.

    `bp_version_override` nur für das Admin-Skript (`--bp-version`, F9): Die `bp_id` geht dann
    nicht mit — sie zeigte auf den Fachplan der ursprünglichen Edition.
    """
    p = Pruefung()
    zaehler = {"ls": 0, "eintraege": 0}

    def text(wert: Any, wo: str, *, pflicht: bool = False) -> str | None:
        if wert is None or wert == "":
            if pflicht:
                p.fehler.append(f"{wo}: fehlt.")
            return None if wert is None else ""
        if isinstance(wert, bool) or not isinstance(wert, (str, int, float)):
            p.fehler.append(f"{wo}: muss Text sein.")
            return None
        s = str(wert)
        if grenzen and len(s) > grenzen.zeichen:
            p.fehler.append(f"{wo}: zu lang ({len(s)} Zeichen, höchstens {grenzen.zeichen}).")
            return None
        sauber = _STEUER.sub("", s.replace("\r\n", "\n").replace("\r", "\n"))
        if sauber != s.replace("\r\n", "\n").replace("\r", "\n"):
            p.warnungen.append(f"{wo}: Steuerzeichen entfernt.")
        return _verweisarten(sauber, wo, p)

    def zahl(wert: Any, wo: str) -> int | None:
        if wert is None:
            return None
        if isinstance(wert, bool) or not isinstance(wert, int):
            if isinstance(wert, str) and wert.strip().isdigit():
                return int(wert.strip())
            p.fehler.append(f"{wo}: muss eine ganze Zahl sein.")
            return None
        return wert

    def stunden(wert: Any, wo: str) -> str | None:
        if wert is None or wert == "":
            return None
        if isinstance(wert, bool) or not isinstance(wert, (int, float, str)):
            p.fehler.append(f"{wo}: Stunden als Zahl oder Text.")
            return None
        return text(wert, wo)

    def liste(wert: Any, wo: str) -> list:
        if wert is None:
            return []
        if not isinstance(wert, list):
            p.fehler.append(f"{wo}: muss eine Liste sein.")
            return []
        if grenzen and len(wert) > grenzen.liste:
            p.fehler.append(f"{wo}: zu viele Einträge ({len(wert)}, höchstens {grenzen.liste}).")
            return []
        return wert

    def objekt(wert: Any, wo: str, bekannt: frozenset) -> dict | None:
        if not isinstance(wert, dict):
            p.fehler.append(f"{wo}: muss ein Objekt mit Feldern sein.")
            return None
        if fremd := sorted(str(k) for k in wert if k not in bekannt):
            p.warnungen.append(f"{wo}: unbekannte Felder übergangen: {', '.join(fremd)}.")
        return wert

    def verweise(wert: Any, wo: str, *, mit_objekt: tuple[str, ...] = ()) -> list:
        """Listen wie `ik`, `pk`, `lp`, `begriffe`: Text oder (bei `mit_objekt`) Objekte mit
        diesen Feldern, die selbst Text, Zahl oder Wahrheitswert sind."""
        aus = []
        for i, el in enumerate(liste(wert, wo), 1):
            if isinstance(el, (str, int, float)) and not isinstance(el, bool):
                if (t := text(el, f"{wo} {i}")) is not None:
                    aus.append(t)
            elif isinstance(el, dict) and mit_objekt:
                el = objekt(el, f"{wo} {i}", frozenset(mit_objekt))
                if el is None:
                    continue
                sauber = {}
                for k in mit_objekt:
                    if k not in el or el[k] is None:
                        continue
                    if isinstance(el[k], bool):
                        sauber[k] = el[k]
                    elif (t := text(el[k], f"{wo} {i}, {k}")) is not None:
                        sauber[k] = t
                aus.append(sauber)
            else:
                p.fehler.append(f"{wo} {i}: unerwarteter Wert.")
        return aus

    oben = objekt(daten, "Datei", FELDER_OBEN)
    if oben is None:
        return p
    # Alle Pflichtfelder müssen dastehen; leer sein dürfen `schule` und `schulart` — der Export
    # schreibt `schule: ""`, wenn die Instanz keinen Schulnamen kennt.
    werte = {}
    for k in PFLICHT:
        if k not in oben:
            p.fehler.append(f"{k}: fehlt.")
            werte[k] = ""
        else:
            werte[k] = text(oben[k], k, pflicht=k not in ("schule", "schulart")) or ""
    kopf = {k: text(oben.get(k), k) for k in ("fach", "fachplan_id", "bp_id", "vorwort")}

    from app.context.curriculum_rahmen import rahmen_normalisieren
    rahmen = oben.get("rahmen")
    if rahmen is not None:
        try:
            rahmen_normalisieren(rahmen)
            rahmen = {k: (text(v, f"rahmen, {k}") if isinstance(v, str) else v) for k, v in rahmen.items()}
        except ValueError as e:
            p.fehler.append(f"rahmen: {e}")
            rahmen = None

    kapitel_roh = oben.get("kapitel")
    if kapitel_roh is not None and not isinstance(kapitel_roh, list):
        p.fehler.append("kapitel: muss eine Liste sein.")
        return p
    if grenzen and kapitel_roh and len(kapitel_roh) > grenzen.kapitel:
        p.fehler.append(f"kapitel: zu viele ({len(kapitel_roh)}, höchstens {grenzen.kapitel}).")
        return p
    if not kapitel_roh:
        p.fehler.append("kapitel: Das Curriculum hat keine Kapitel.")
        return p

    kapitel = []
    for ki, kap in enumerate(kapitel_roh, 1):
        kwo = f"Kapitel {ki}"
        kap = objekt(kap, kwo, FELDER_KAPITEL)
        if kap is None:
            continue
        lernsequenzen = []
        ls_roh = kap.get("lernsequenzen") or []
        if not isinstance(ls_roh, list):
            p.fehler.append(f"{kwo}, lernsequenzen: muss eine Liste sein.")
            ls_roh = []
        for li, ls in enumerate(ls_roh, 1):
            lwo = f"{kwo}, Lernsequenz {li}"
            zaehler["ls"] += 1
            ls = objekt(ls, lwo, FELDER_LS)
            if ls is None:
                continue
            eintraege = []
            e_roh = ls.get("eintraege") or []
            if not isinstance(e_roh, list):
                p.fehler.append(f"{lwo}, eintraege: muss eine Liste sein.")
                e_roh = []
            for ei, e in enumerate(e_roh, 1):
                ewo = f"{lwo}, Eintrag {ei}"
                zaehler["eintraege"] += 1
                e = objekt(e, ewo, FELDER_EINTRAG)
                if e is None:
                    continue
                ik = e.get("ik")
                ik = (text(ik, f"{ewo}, ik") if isinstance(ik, (str, int, float)) and not isinstance(ik, bool)
                      else verweise(ik, f"{ewo}, ik", mit_objekt=("nr", "partiell")))
                partiell = e.get("ik_partiell", False)
                if not isinstance(partiell, bool):
                    p.fehler.append(f"{ewo}, ik_partiell: muss true oder false sein.")
                    partiell = False
                eintraege.append(CurriculumDraftEntry(
                    ik=ik, ik_partiell=partiell,
                    pk=verweise(e.get("pk"), f"{ewo}, pk", mit_objekt=("id",)),
                    konkretisierung=text(e.get("konkretisierung"), f"{ewo}, konkretisierung"),
                    hinweise=text(e.get("hinweise"), f"{ewo}, hinweise"),
                    lp=verweise(e.get("lp"), f"{ewo}, lp"),
                    material=text(e.get("material"), f"{ewo}, material"),
                    begriffe=verweise(e.get("begriffe"), f"{ewo}, begriffe", mit_objekt=("name", "fassung")),
                    fachmethoden=verweise(e.get("fachmethoden"), f"{ewo}, fachmethoden", mit_objekt=("name",)),
                ))
            lernsequenzen.append(CurriculumDraftLernsequenz(
                bp_titel=(text(ls.get("bp_titel"), f"{lwo}, bp_titel") or "").strip() or None,
                bp_leitidee=text(ls.get("bp_leitidee"), f"{lwo}, bp_leitidee"),
                reihenfolge=li if (r := zahl(ls.get("reihenfolge"), f"{lwo}, reihenfolge")) is None else r,
                std=stunden(ls.get("std"), f"{lwo}, std"),
                eintraege=eintraege,
            ))
        reihenfolge = zahl(kap.get("reihenfolge"), f"{kwo}, reihenfolge")
        konkretisierung = [t for i, k in enumerate(liste(kap.get("konkretisierung"), f"{kwo}, konkretisierung"), 1)
                           if (t := text(k, f"{kwo}, konkretisierung {i}"))]
        roh_titel = kap.get("titel")
        titel = (text(roh_titel, f"{kwo}, titel", pflicht=True) or "").strip()
        if not titel and isinstance(roh_titel, str) and roh_titel:
            p.fehler.append(f"{kwo}, titel: fehlt.")
        kapitel.append(CurriculumDraftKapitel(
            titel=titel, reihenfolge=reihenfolge if reihenfolge is not None else ki,
            std=stunden(kap.get("std"), f"{kwo}, std"), hinweis=text(kap.get("hinweis"), f"{kwo}, hinweis"),
            konkretisierung=konkretisierung, lernsequenzen=lernsequenzen,
        ))

    # Die Reihenfolge ist Teil des Schlüssels jedes Kapitels und jeder Lernsequenz: Zwei gleiche
    # Nummern legte der Import zu **einem** Knoten zusammen. Dann zählt die Position.
    if len({k.reihenfolge for k in kapitel}) < len(kapitel):
        p.warnungen.append("Kapitel: Reihenfolge doppelt — nach Position neu nummeriert.")
        for i, k in enumerate(kapitel, 1):
            k.reihenfolge = i
    for k in kapitel:
        if len({ls.reihenfolge for ls in k.lernsequenzen}) < len(k.lernsequenzen):
            p.warnungen.append(f"Kapitel „{k.titel}“: Reihenfolge der Lernsequenzen doppelt — nach Position "
                               f"neu nummeriert.")
            for i, ls in enumerate(k.lernsequenzen, 1):
                ls.reihenfolge = i

    if grenzen and zaehler["ls"] > grenzen.lernsequenzen:
        p.fehler.append(f"Zu viele Lernsequenzen ({zaehler['ls']}, höchstens {grenzen.lernsequenzen}).")
    if grenzen and zaehler["eintraege"] > grenzen.eintraege:
        p.fehler.append(f"Zu viele Einträge ({zaehler['eintraege']}, höchstens {grenzen.eintraege}).")
    if p.fehler:
        return p

    p.entwurf = CurriculumDraftConfirmed(
        schule=werte["schule"], fach_code=werte["fach_code"], fach=kopf["fach"] or None,
        schulart=werte["schulart"], jahrgangsstufe=werte["jahrgangsstufe"],
        fachplan_id=kopf["fachplan_id"] or None,
        bp_id=None if bp_version_override else (kopf["bp_id"] or None),
        bp_version=bp_version_override or werte["bp_version"],
        vorwort=kopf["vorwort"], rahmen=rahmen, kapitel=kapitel,
    )
    return p


def _verweisarten(s: str, wo: str, p: Pruefung) -> str:
    """Verweise unbekannter Art → nur ihr Text, mit Warnung. Bekannte bleiben stehen; ob ihr
    Ziel existiert und lesbar ist, prüfen :func:`verweise_pruefen` und der Import."""
    def ersetzen(m: re.Match) -> str:
        if m.group(3) in VERWEISARTEN:
            return m.group(0)
        p.warnungen.append(f"{wo}: Verweis „{m.group(2)}“ unbekannter Art ({m.group(3)}) — nur der Text bleibt.")
        return m.group(2)
    return VERWEIS.sub(ersetzen, s) if "](" in s else s


# ── Prüfungen mit Datenbank ──────────────────────────────────────────────────

#: Verweise mit einer Kennung (UUID) statt eines Codes. Ein Export schreibt sie, wenn das Ziel
#: keinen Code hat (Material immer: `node:`). Welche Art auf welchen Typ zeigen darf:
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_UUID_VERWEIS = re.compile(r'([@#])\[([^\]]*)\]\((lp|lpa|lb|lba|ik|node):(' + _UUID + r')\)')


async def verweise_pruefen(db, entwurf: CurriculumDraftConfirmed, user) -> list[str]:
    """Verweise mit Kennung nur auf Bausteine, die die Person lesen darf (F5).

    Sonst bleibt nur der Text des Verweises, ohne Link, mit Warnung. So hängt niemand über
    eine Datei einen fremden privaten Baustein in ein Curriculum — der Import legte zu jeder
    vorhandenen Kennung eine Kante an, ohne nach dem Leserecht zu fragen. Ändert `entwurf`.
    """
    import sqlalchemy as sa
    from uuid import UUID

    from app.context.visibility import read_scope_clause
    from app.db.models import ContextNode

    felder = []
    for ki, kap in enumerate(entwurf.kapitel, 1):
        for li, ls in enumerate(kap.lernsequenzen, 1):
            for ei, e in enumerate(ls.eintraege, 1):
                for name in ("hinweise", "material"):
                    if getattr(e, name):
                        felder.append((e, name, f"Kapitel {ki}, Lernsequenz {li}, Eintrag {ei}, {name}"))
    kennungen = {UUID(m.group(4)) for e, name, _ in felder for m in _UUID_VERWEIS.finditer(getattr(e, name))}
    if not kennungen:
        return []
    lesbar = set((await db.execute(sa.select(ContextNode.id).where(
        ContextNode.id.in_(kennungen), ContextNode.status != "deleted",
        read_scope_clause(user.sub, user.roles)))).scalars())

    warnungen: list[str] = []

    def ersetzen(m: re.Match, wo: str) -> str:
        if UUID(m.group(4)) in lesbar:
            return m.group(0)
        warnungen.append(f"{wo}: Verweis „{m.group(2)}“ zeigt auf einen Baustein, den es nicht gibt "
                         f"oder den du nicht lesen darfst — nur der Text bleibt.")
        return m.group(2)

    for e, name, wo in felder:
        setattr(e, name, _UUID_VERWEIS.sub(lambda m, wo=wo: ersetzen(m, wo), getattr(e, name)))
    return warnungen
