"""Kalender-Endpunkte (UP-8).

Bisher nur die Kürzel-Liste für die Profileinstellung (Schritt 3).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.config import SsoConfig
from app.auth.dependencies import get_current_user, get_sso_config, require_any_role
from app.calendar.base import CalendarSourceError
from app.calendar.sync import SlotRef
from app.calendar.groups import (
    kein_unterricht_codes,
    klassenkarte,
    lege_gruppe_aus_vorschlag_an,
    match_groups,
    quellklassen_aufloesen,
)
from app.calendar.patterns import derive_patterns
from app.calendar.service import (
    KUERZEL_PREFERENCE_KEY,
    get_adapter,
    is_configured,
    list_kuerzel,
)
from app.db.models import Group
from app.db.session import get_db
from app.groups.aktualitaet import (
    gruppen_mit_beleg,
    gruppen_mit_quellklasse,
    ist_aktuell,
)
from app.planning.calendar import ab_phasen, is_schoolday, load_school_year
from app.preferences.service import get_preferences

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/status")
async def calendar_status(
    _user=Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    """Ist eine Stundenplanquelle eingerichtet? — **ohne** sie zu kontaktieren.

    Getrennt von `/teachers`, weil die Antwort die Navigation steuert und damit bei jedem
    Seitenaufruf gebraucht wird. `/teachers` meldet dasselbe, kostet aber eine Anmeldung
    samt Elementabruf — das wäre für ein Menü der falsche Preis.
    """
    return {"configured": is_configured()}


@router.get("/school-year")
async def school_year(
    _user=Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    """Das laufende Schuljahr aus `config/school_year.yaml`.

    Damit die Oberfläche kein zweites Mal rechnet. Der Knopf „Schuljahresende" im
    Baustein-Formular leitete das Datum bis 04.09.2026 aus dem eingetippten Schuljahr ab
    und nahm dafür **fest den 31.07.** an — in der Config steht der 29.07.2026 bzw. der
    28.07.2027. Zwei Tage daneben fällt niemandem auf, und genau deshalb bleibt es
    stehen.

    Wichtiger als die zwei Tage ist der Gleichlauf: Dasselbe Datum trägt der Server ein,
    wenn beim Anlegen kein Ablaufdatum angegeben wird
    (`_ablaufdatum_vorbelegen` in `app/db/models.py`). Knopf und Automatik müssen
    dieselbe Antwort geben, sonst wirkt eines von beidem falsch.

    Bewusst schmal — nur die vier Eckdaten. Ferien und Feiertage liefert der
    Planer-Endpunkt, der sie auch braucht.
    """
    cfg = load_school_year()
    return {
        "schuljahr": cfg.schuljahr,
        "beginn": cfg.beginn.isoformat(),
        "ende": cfg.ende.isoformat(),
        "halbjahreswechsel": cfg.halbjahreswechsel.isoformat(),
    }


@router.get("/teachers")
async def list_teachers(
    _user=Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    """Auswählbare Lehrkraft-Kürzel der konfigurierten Stundenplanquelle.

    Grundlage der Auswahl im Profil: Ein Tippfehler in einem Freitextfeld führte zu einem
    stillen Nicht-Abruf, den niemand mehr zuordnen kann.

    **Kein Fehler, wenn nichts konfiguriert ist** — dann ist `configured` falsch und die
    Oberfläche blendet das Feld aus (Plan §0). Eine Schule ohne WebUntis soll hier keine
    Störungsmeldung sehen.

    Nur für Lehrkräfte: Die Kürzel-Liste ist kollegiumsöffentlich (Plan §2), für
    Schüler:innen aber ohne Zweck.
    """
    if not is_configured():
        return {"configured": False, "teachers": [], "error": None}
    try:
        return {"configured": True, "teachers": await list_kuerzel(), "error": None}
    except CalendarSourceError as exc:
        # Adapter-Meldungen sind bewusst frei von Zugangsdaten (siehe base.py).
        logger.warning("Kürzel-Liste nicht abrufbar: %s", exc)
        return {"configured": True, "teachers": [], "error": str(exc)}


def _ist_unterrichtswoche(montag: date, cfg) -> bool:
    return any(is_schoolday(montag + timedelta(days=n), cfg) for n in range(5))


def _suche_woche(montag: date, cfg, richtung: int) -> date | None:
    """Die erste Unterrichtswoche ab `montag` in dieser Richtung, `montag` eingeschlossen.

    Zwei Schuljahre als Notbremse — weiter zu suchen hieße, eine Config zu bedienen, die
    zum Datum gar nicht passt.
    """
    for _ in range(104):
        if _ist_unterrichtswoche(montag, cfg):
            return montag
        montag += timedelta(weeks=richtung)
    return None


def _verlaengere(von: date, cfg, richtung: int, hoechstens: int) -> list[date]:
    """Bis zu `hoechstens` **lückenlos** anschließende Unterrichtswochen neben `von`."""
    wochen: list[date] = []
    kandidat = von + timedelta(weeks=richtung)
    while len(wochen) < hoechstens and _ist_unterrichtswoche(kandidat, cfg):
        wochen.append(kandidat)
        kandidat += timedelta(weeks=richtung)
    return wochen


def _unterrichtswochen(referenz: date, anzahl: int) -> list[date]:
    """Bis zu `anzahl` **zusammenhängende** Unterrichtswochen ab `referenz`.

    Zwei Anforderungen, die einander widersprechen könnten:

    * **Ferienwochen dürfen nicht mitzählen.** Sonst wäre der Nenner falsch: „in 2 von 4
      Wochen gesehen" hieße bei zwei Ferienwochen in Wahrheit „in 2 von 2" — und jeder
      wöchentliche Termin sähe 14-tägig aus.
    * **Die Wochen müssen aneinandergrenzen.** Über eine Ferienlücke hinweg ist nicht
      bestimmbar, ob der A/B-Takt nach Kalenderwochen weiterläuft oder neu anfängt. Aus
      Wochen mit Lücke einen Rhythmus abzuleiten hieße raten.

    Deshalb wird nach einem **ununterbrochenen** Lauf gesucht, statt Ferienwochen einfach
    zu überspringen.

    **Nach vorn, nicht zurück** (14.09.2026). Der Stundenplan ist ein *Plan*: Für die
    Frage, wann eine Stunde regelmäßig liegt, ist die Veröffentlichung die bessere Quelle
    als die Vergangenheit, in der Ausfall und Vertretung das Bild schon verändert haben.
    Und am Schuljahresanfang — genau dann, wenn man das Raster anlegen will — gibt es
    keine Vergangenheit. Liegt `referenz` in den Ferien, zählt der Plan **danach**.

    Reicht die Zukunft nicht, wird aus der Vergangenheit aufgefüllt: am Schuljahresende,
    oder wenn die Ferien schon in zwei Wochen beginnen.
    """
    cfg = load_school_year()
    montag = referenz - timedelta(days=referenz.weekday())
    # Die laufende Woche, sonst die nächste mit Unterricht. Findet sich vorwärts keine
    # mehr (Schuljahresende, oder die Config beschreibt ein vergangenes Jahr), dient die
    # letzte vergangene als Anker — sonst bliebe die Antwort leer.
    start = _suche_woche(montag, cfg, +1) or _suche_woche(montag, cfg, -1)
    if start is None:
        return []
    fenster = [start] + _verlaengere(start, cfg, +1, anzahl - 1)
    if len(fenster) < anzahl:
        fenster += _verlaengere(fenster[0], cfg, -1, anzahl - len(fenster))
    return sorted(fenster)


def _abgleich_wochen(
    referenz: date, rueckblick: int = 1, vorausschau: int = 2
) -> list[date]:
    """Kalenderwochen für den **Abgleich** — anderes Fenster als für die Musterableitung.

    Beide Fenster blicken nach vorn (seit 14.09.2026 auch `_unterrichtswochen`). Der
    Unterschied ist die **Zusammenhangs-Regel**: Die Musterableitung braucht lückenlos
    aneinandergrenzende Wochen, sonst ist der A-/B-Takt nicht bestimmbar. Der Abgleich
    braucht das nicht — er braucht die **jüngsten** Wochen, und eine Verlegung über die
    Ferien hinweg soll er trotzdem finden.

    Er blickt außerdem eine Woche weiter zurück als die Musterableitung: Eine Verlegung
    zeigt zwar meist nach vorn, ihr Ursprung liegt aber in der Vergangenheit.

    Die laufende Woche ist immer dabei, sofern sie Unterricht enthält.
    """
    cfg = load_school_year()
    montag = referenz - timedelta(days=referenz.weekday())
    wochen: list[date] = []
    for versatz in range(-rueckblick + 1, vorausschau + 1):
        kandidat = montag + timedelta(weeks=versatz)
        if kandidat < cfg.beginn or kandidat > cfg.ende:
            continue
        if any(is_schoolday(kandidat + timedelta(days=n), cfg) for n in range(5)):
            wochen.append(kandidat)
    return wochen


@dataclass
class _Musterlage:
    """Was ein Stundenplan-Abruf über die Lerngruppen einer Lehrkraft hergibt."""

    result: object          # Ergebnis von `derive_patterns`
    abgleich: object        # `GroupMatchResult`
    halbjahr: int
    warnungen: list[str]


async def _musterlage(
    db: AsyncSession,
    pseudonym: str,
    kuerzel: str,
    wochen: int,
    stichtag: date | None,
) -> _Musterlage:
    """Stundenplan abrufen, Wochenmuster ableiten, gegen die eigenen Gruppen abgleichen.

    **Gemeinsame Grundlage von `GET /week-patterns` und `POST /teaching-groups`.** Beide
    müssen dasselbe sehen: Beim Anlegen ist das Vorkommen im eigenen Stundenplan die
    **Berechtigung**, und die darf nicht aus einer zweiten, womöglich abweichenden
    Rechnung stammen. Zwei Kopien dieser Kette liefen sonst irgendwann auseinander — und
    die Abweichung fiele ausgerechnet dort auf, wo sie ein Rechteproblem wäre.
    """
    kalenderwochen = _unterrichtswochen(stichtag or date.today(), wochen)
    if not kalenderwochen:
        raise HTTPException(
            status_code=409,
            detail="Im Schuljahr liegen um dieses Datum herum keine Unterrichtswochen.",
        )

    try:
        adapter = get_adapter()
        async with adapter:  # type: ignore[attr-defined]
            raster = await adapter.timegrid(kalenderwochen[-1])  # type: ignore[attr-defined]
            stunden = []
            warnungen: list[str] = []
            for woche in kalenderwochen:
                ergebnis = await adapter.fetch_week(kuerzel, woche)  # type: ignore[attr-defined]
                stunden.extend(ergebnis.lessons)
                warnungen.extend(ergebnis.warnings)
    except CalendarSourceError as exc:
        logger.warning("Stundenplan-Abruf für %s fehlgeschlagen: %s", kuerzel, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from None

    cfg = load_school_year()
    result = derive_patterns(
        stunden,
        wochen=kalenderwochen,
        timegrid=raster,
        # Welche Wochen A- und welche B-Wochen sind, entscheidet das Schuljahr, nicht das
        # Abruffenster. Ohne das Mapping hinge das Etikett am Klickzeitpunkt.
        phasen=ab_phasen(cfg),
        kein_unterricht=kein_unterricht_codes(),
    )
    # Aus welchem Halbjahr die Wochen stammen — der Editor schreibt je Halbjahr, und ein
    # Muster ins falsche zu übernehmen wäre schwer zu bemerken.
    halbjahr = 1 if kalenderwochen[-1] < cfg.halbjahreswechsel else 2
    # Die erkannten Lerngruppen gegen die Unterrichtsgruppen der Plattform abgleichen.
    # Erst damit wird aus einem Muster ein schreibbarer Vorschlag — und erst hier fällt
    # auf, wenn ein Fachkürzel keinem Fach zugeordnet ist.
    abgleich = await match_groups(db, [p.key for p in result.proposals], pseudonym=pseudonym)
    return _Musterlage(result=result, abgleich=abgleich, halbjahr=halbjahr,
                       warnungen=warnungen)


@router.get("/week-patterns")
async def week_patterns(
    wochen: int = Query(4, ge=1, le=12),
    stichtag: date | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_any_role(["teacher", "admin"])),
    _current=Depends(get_current_user),
) -> dict:
    """Wochenmuster-Vorschläge aus dem eigenen Stundenplan (UP-8, Schritt 6).

    **Vorschlag, keine Übernahme.** Das Schreiben nach `group_week_patterns` braucht die
    Zuordnung zu den Unterrichtsgruppen der Plattform — die kommt in Schritt 7.

    Vier Wochen als Vorgabe: Weniger als zwei erlaubt keine Aussage über 14-tägige
    Termine, mehr erhöht nur die Wahrscheinlichkeit, dass zwischendurch der Plan
    gewechselt hat.
    """
    if not is_configured():
        return {"configured": False, "kuerzel": None, "patterns": [], "hinweise": []}

    prefs = await get_preferences(db, _current.sub)
    kuerzel = (prefs.get(KUERZEL_PREFERENCE_KEY) or "").strip()
    if not kuerzel:
        return {
            "configured": True,
            "kuerzel": None,
            "patterns": [],
            "hinweise": [
                "Im Profil ist kein Kürzel eingetragen — ohne das lässt sich kein "
                "Stundenplan abrufen."
            ],
        }

    lage = await _musterlage(db, _current.sub, kuerzel, wochen, stichtag)
    result, abgleich, halbjahr, warnungen = (
        lage.result, lage.abgleich, lage.halbjahr, lage.warnungen
    )
    # Woher die Mitglieder einer noch fehlenden Gruppe kämen, weiß nur der Server — die
    # Oberfläche kennt die Klassengruppen der Plattform nicht. Sie hier mitzugeben ist
    # billiger als eine zweite Abfrage und verhindert, dass die Liste rät.
    karte = await klassenkarte(db) if abgleich.fehlend else {}
    aufloesungen = {
        s.key.label: quellklassen_aufloesen(karte, s.class_names) for s in abgleich.fehlend
    }
    verschwunden = await _nicht_mehr_im_stundenplan(db, abgleich.nicht_im_stundenplan)
    # Eine Gruppe kann mehrere Muster-Schlüssel bündeln (M + MD).
    zuordnung = {k: s for s in abgleich.fehlend for k in s.keys}
    vorhanden = set(abgleich.vorhanden)
    return {
        "configured": True,
        "kuerzel": kuerzel,
        "halbjahr": halbjahr,
        "wochen": [w.isoformat() for w in result.wochen],
        "patterns": [
            {
                "gruppe": p.key.label,
                "student_group": p.key.student_group,
                "fach": p.key.subject,
                "klassen": list(p.key.class_names),
                "weekday": p.weekday,
                "start_period": p.start_period,
                "periods": p.periods,
                "rhythmus": p.rhythmus,
                "gesehen": p.gesehen,
                "von_wochen": p.wochen,
                "sicher": p.sicher,
                # Ohne Fach-/Gruppenzuordnung lässt sich das Muster nicht speichern —
                # `group_week_patterns` braucht eine `group_id`.
                "subject_id": (zuordnung.get(p.key) or _leer).subject_id,
                "subject_slug": (zuordnung.get(p.key) or _leer).subject_slug,
                "gruppe_vorhanden": p.key in vorhanden,
                "gruppe_vorschlag": (zuordnung.get(p.key) or _leer).vorschlag_name,
                # `group_id` nur bei vorhandener Gruppe — nur dorthin lässt sich schreiben.
                "group_id": abgleich.zuordnung.get(p.key),
            }
            for p in result.proposals
        ],
        "fehlende_gruppen": [
            {
                "name": s.vorschlag_name,
                "subject_id": s.subject_id,
                "subject_slug": s.subject_slug,
                "klassen": list(s.class_names),
                "gruppe": s.key.label,
                "kursart": s.kursart,
                # Mehrere Kürzel = eine Gruppe (Differenzierungsstunde).
                "kuerzel": list(s.codes),
                # Woher die Mitglieder kämen, wenn die Gruppe jetzt angelegt würde.
                # `erbt_aus` ist leer, sobald die Gruppe über mehreren Klassen liegt —
                # dann ist sie eine Auswahl daraus und füllt sich über den Code.
                "erbt_aus": (
                    list(aufloesungen[s.key.label].treffer)
                    if aufloesungen[s.key.label].erbt else []
                ),
                "stammt_aus": list(aufloesungen[s.key.label].treffer),
                "klassen_ohne_treffer": list(aufloesungen[s.key.label].ohne_treffer),
                "kursstufe": aufloesungen[s.key.label].kursstufe,
                "mehrklassig": aufloesungen[s.key.label].mehrklassig,
                # Ob die Frage „ganze Klasse oder Teilgruppe?" überhaupt sinnvoll ist —
                # ohne gefundene Klasse gibt es nichts zu erben.
                "kann_erben": bool(aufloesungen[s.key.label].treffer),
                "erbt_vorbelegt": aufloesungen[s.key.label].erbt,
            }
            for s in abgleich.fehlend
        ],
        "unbekannte_faecher": [
            {"code": u.code, "stunden": u.stunden, "klassen": list(u.klassen)}
            for u in abgleich.unbekannte_faecher
        ],
        # Doppelte Warnungen aus mehreren Wochen zusammenfassen — sonst steht dieselbe
        # Meldung viermal untereinander.
        "hinweise": [
            *result.hinweise,
            *sorted(set(warnungen)),
            *(
                [
                    f"{len(abgleich.ohne_klasse)} Lerngruppen ohne Fach oder Klasse — "
                    f"daraus lässt sich keine Unterrichtsgruppe ableiten."
                ]
                if abgleich.ohne_klasse
                else []
            ),
            *abgleich.mehrdeutig,
            *verschwunden,
        ],
    }


class TeachingGroupAusStundenplan(BaseModel):
    """Welche Lerngruppe des eigenen Stundenplans angelegt werden soll."""

    gruppe: str            # `GroupKey.label`, wie in `fehlende_gruppen.gruppe`
    subject_id: int        # zur Absicherung: muss zum serverseitigen Vorschlag passen
    # Ob die Gruppe den ganzen Klassenverband unterrichtet (`true`) oder eine Auswahl
    # daraus (`false`). `None` übernimmt die Vorbelegung des Servers.
    erbt: bool | None = None
    wochen: int = 4
    stichtag: date | None = None


@router.post("/teaching-groups", status_code=201)
async def gruppe_aus_stundenplan_anlegen(
    body: TeachingGroupAusStundenplan,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_any_role(["teacher", "admin"])),
    sso_config: SsoConfig = Depends(get_sso_config),
    _current=Depends(get_current_user),
) -> dict:
    """Eine im Stundenplan gefundene, auf der Plattform fehlende Gruppe anlegen.

    ⚠️ **Die Berechtigung ist das Vorkommen im eigenen Stundenplan** — deshalb rechnet
    der Endpunkt den Abgleich neu und sucht die angeforderte Lerngruppe in
    `fehlend`. Name, Fach und Klassen stammen **ausschließlich** aus diesem Ergebnis;
    aus der Anfrage kommt nur, *welche* Gruppe gemeint ist. Dasselbe Muster wie bei den
    Plan-Operationen: Ein vom Client übergebener Vorschlag wäre eine Einladung, beliebige
    Gruppen anzulegen und sich zur Lehrkraft darin zu machen.

    `subject_id` wird mitgeschickt und **geprüft**, nicht übernommen: Stimmt sie nicht
    mit dem serverseitigen Vorschlag überein, hat sich die Lage seit dem Laden der Liste
    geändert (anderes Fachkürzel-Mapping, andere Woche) — dann ist Abbrechen richtiger
    als Anlegen.
    """
    if not is_configured():
        raise HTTPException(409, "Für diese Installation ist kein Stundenplan angebunden.")
    # ⚠️ **Derselbe Schalter wie beim manuellen Weg.** `allow_manual_teaching_groups=false`
    # heißt „der SSO liefert alle Unterrichtsgruppen, Lehrkräfte legen keine eigenen an".
    # Dieser Weg hier ist besser belegt als „Klasse × Fach", aber er erzeugt dieselbe
    # Art Gruppe — und in einer Installation, die auf den SSO setzt, dieselben
    # Dubletten. Ohne die Prüfung wäre der Schalter über die Hintertür wirkungslos.
    if not sso_config.allow_manual_teaching_groups:
        raise HTTPException(
            403, "Unterrichtsgruppen werden in dieser Installation vom Schulkonto geführt."
        )

    prefs = await get_preferences(db, _current.sub)
    kuerzel = (prefs.get(KUERZEL_PREFERENCE_KEY) or "").strip()
    if not kuerzel:
        raise HTTPException(
            409, "Im Profil ist kein Kürzel eingetragen — ohne das gibt es keinen Stundenplan."
        )

    lage = await _musterlage(db, _current.sub, kuerzel, body.wochen, body.stichtag)

    vorschlag = next(
        (s for s in lage.abgleich.fehlend if s.key.label == body.gruppe), None
    )
    if vorschlag is None:
        # Bewusst 403 und nicht 404: Die Gruppe mag es geben — nur nicht im Stundenplan
        # dieser Lehrkraft. Der Unterschied ist eine Rechte-, keine Existenzfrage.
        raise HTTPException(
            403,
            "Diese Lerngruppe steht nicht als fehlend in Ihrem Stundenplan. "
            "Vielleicht ist die Gruppe inzwischen angelegt — bitte Liste neu laden.",
        )
    if vorschlag.subject_id != body.subject_id:
        raise HTTPException(
            409,
            "Das Fach dieser Lerngruppe hat sich seit dem Laden der Liste geändert. "
            "Bitte Liste neu laden.",
        )

    ergebnis = await lege_gruppe_aus_vorschlag_an(db, vorschlag, _current.sub, body.erbt)
    await db.commit()
    logger.info(
        "gruppe_aus_stundenplan pseudonym=%s gruppe=%s id=%s quellklassen=%d kursstufe=%s",
        _current.sub, body.gruppe, ergebnis.group_id,
        len(ergebnis.quellklassen), ergebnis.kursstufe,
    )
    return {
        "group_id": ergebnis.group_id,
        "name": ergebnis.name,
        "subject_id": ergebnis.subject_id,
        "quellklassen": list(ergebnis.quellklassen),
        "ohne_treffer": list(ergebnis.ohne_treffer),
        "kursstufe": ergebnis.kursstufe,
        "erbt": ergebnis.erbt,
    }


async def _nicht_mehr_im_stundenplan(db: AsyncSession, kandidaten) -> list[str]:
    """Hinweise zu eigenen Gruppen, die der Stundenplan nicht mehr nennt.

    **Ein Hinweis, keine Handlung.** Nichts wird archiviert, gelöscht oder umbenannt: An
    einer Unterrichtsgruppe hängen Jahresplan, Stundenentwürfe, Konversationen und
    Kontextfreigaben. Ob eine Gruppe wirklich ausgelaufen ist oder nur gerade nicht im
    Abrufzeitraum liegt, weiß die Lehrkraft — die Plattform sieht vier Wochen.

    ⚠️ **Gefiltert auf das laufende Schuljahr.** Ohne `ist_aktuell` meldete der Hinweis
    jede Gruppe aus jedem Vorjahr und aus dem anderen Halbjahr — Lärm, in dem der eine
    echte Fall untergeht. Die Regel dafür teilt sich diese Stelle mit der Gruppenliste
    (`app/groups/aktualitaet.py`); zwei Fassungen liefen auseinander.
    """
    if not kandidaten:
        return []
    ids = [k.id for k in kandidaten]
    gruppen = list((await db.execute(select(Group).where(Group.id.in_(ids)))).scalars())
    cfg = load_school_year()
    beleg = await gruppen_mit_beleg(db, ids, cfg)
    quellklassen = await gruppen_mit_quellklasse(db, ids)
    betroffen = [g for g in gruppen if ist_aktuell(g, beleg, cfg, quellklassen)]
    if not betroffen:
        return []
    namen = ", ".join(f"„{g.anzeigename}“" for g in sorted(betroffen, key=lambda g: g.anzeigename))
    return [
        f"{namen}: im Stundenplan nicht gefunden. Das kann am Abrufzeitraum liegen — "
        "oder die Gruppe läuft nicht mehr. Geändert wurde nichts; Planung und Chats "
        "bleiben erhalten."
    ]


class _Leer:
    """Platzhalter für Muster ohne Gruppenzuordnung — spart Fallunterscheidungen oben."""

    subject_id = None
    subject_slug = None
    vorschlag_name = None


_leer = _Leer()


async def _stundenplan_abgleich(
    db: AsyncSession, pseudonym: str, wochen_anzahl: int, bis: date | None
):
    """Gemeinsame Vorarbeit von Vorschau und Ausführung (Schritt 8).

    Beide brauchen dasselbe: Stunden abrufen, Lerngruppen zuordnen, Slots laden, Plan
    rechnen. Getrennt implementiert liefe die Vorschau irgendwann etwas anderes vor als
    die Ausführung tut — und genau darauf verlässt man sich.
    """
    from sqlalchemy import text

    from app.calendar.groups import (
    kein_unterricht_codes,
    klassenkarte,
    lege_gruppe_aus_vorschlag_an,
    match_groups,
    quellklassen_aufloesen,
)
    from app.calendar.sync import SlotRef, plan_sync

    prefs = await get_preferences(db, pseudonym)
    kuerzel = (prefs.get(KUERZEL_PREFERENCE_KEY) or "").strip()
    if not kuerzel:
        return None, None, "Im Profil ist kein Kürzel eingetragen."

    # Abgleichfenster, nicht Musterfenster: jüngste Wochen inklusive der laufenden, plus
    # zwei nach vorn für Verlegungsziele.
    kalenderwochen = _abgleich_wochen(bis or date.today(), wochen_anzahl)
    if not kalenderwochen:
        return None, None, "Im Schuljahr liegen um dieses Datum keine Unterrichtswochen."

    adapter = get_adapter()
    async with adapter:  # type: ignore[attr-defined]
        raster = await adapter.timegrid(kalenderwochen[-1])  # type: ignore[attr-defined]
        stunden: list = []
        for woche in kalenderwochen:
            stunden.extend((await adapter.fetch_week(kuerzel, woche)).lessons)  # type: ignore[attr-defined]

    # Ohne `phasen`, anders als bei den Wochenmustern: Gebraucht werden hier allein die
    # Lerngruppen-Schlüssel. Der Rhythmus wird verworfen — aus einem Fenster mit Lücken
    # wäre er ohnehin nicht bestimmbar.
    muster = derive_patterns(
        stunden,
        wochen=kalenderwochen,
        timegrid=raster,
        kein_unterricht=kein_unterricht_codes(),
    )
    abgleich = await match_groups(db, [p.key for p in muster.proposals], pseudonym=pseudonym)

    # Nur Stunden, deren Lerngruppe einer vorhandenen Unterrichtsgruppe entspricht —
    # ohne `group_id` gibt es keinen Slot, den man ändern könnte.
    from app.calendar.patterns import GroupKey

    def schluessel(lesson) -> GroupKey:
        return GroupKey(
            student_group=lesson.student_group,
            subject=lesson.subject,
            class_names=lesson.class_names,
        )

    zugeordnet = [
        (abgleich.zuordnung[schluessel(l)], l)
        for l in stunden
        if schluessel(l) in abgleich.zuordnung
    ]

    zeitraum = (kalenderwochen[0], kalenderwochen[-1] + timedelta(days=6))
    gruppen = sorted({gid for gid, _ in zugeordnet})
    slots: list[SlotRef] = []
    if gruppen:
        rows = await db.execute(
            text(
                f"SELECT {', '.join(SLOT_SPALTEN)} "
                "FROM lesson_slots WHERE group_id = ANY(:gruppen) "
                "AND date BETWEEN :von AND :bis"
            ),
            {"gruppen": gruppen, "von": zeitraum[0], "bis": zeitraum[1]},
        )
        slots = als_slot_refs(rows.mappings().all())

    plan = plan_sync(zugeordnet, slots, zeitraum=zeitraum)
    return plan, {"kuerzel": kuerzel, "wochen": kalenderwochen, "gruppen": gruppen}, None


# Die Spalten, die der Abgleich von einem Slot braucht. Als Liste, damit Abfrage und
# Abbildung nicht auseinanderlaufen können.
SLOT_SPALTEN = (
    "id", "group_id", "date", "start_period", "kategorie", "pinned", "source", "note",
    "periods", "ausfall_herkunft",
)


def als_slot_refs(zeilen) -> list[SlotRef]:
    """Datenbankzeilen → `SlotRef`. Über **Namen**, nicht über Positionen.

    ⚠️ **Warum das eine eigene Funktion ist.** Vorher stand die Abbildung inline und griff
    mit `r[0]`…`r[8]` zu. Eine neue Spalte an der falschen Stelle hätte alles verschoben,
    ohne dass etwas auffiele — und `periods` ist die Angabe, an der die Phantom-Termine
    hängen: Fehlt sie, hält der Abgleich die zweite Hälfte jeder Doppelstunde für
    ungedeckt und legt dort einen Termin an. Mit Namen kann das nicht mehr passieren, und
    die Abbildung ist ohne Datenbank prüfbar.
    """
    return [
        SlotRef(
            id=z["id"],
            group_id=z["group_id"],
            datum=z["date"],
            start_period=z["start_period"] or 0,
            kategorie=z["kategorie"],
            pinned=z["pinned"],
            source=z["source"],
            note=z["note"],
            periods=z["periods"] or 1,
            ausfall_herkunft=z["ausfall_herkunft"],
        )
        for z in zeilen
    ]


def _plan_als_json(plan, kontext) -> dict:
    return {
        "kuerzel": kontext["kuerzel"],
        "wochen": [w.isoformat() for w in kontext["wochen"]],
        "gruppen": len(kontext["gruppen"]),
        "aenderungen": [
            {
                "datum": c.datum.isoformat(),
                "stunde": c.start_period,
                "von": c.von_kategorie,
                "nach": c.nach_kategorie,
                "anpassung_noetig": c.anpassung_noetig,
                "notiz": c.notiz,
            }
            for c in plan.wirksame_changes
        ],
        # Für den Verschiebe-Dialog aus UP-6: `slot_id` als `slot_ids`, Trigger `ausfall`.
        "verlegungen": [
            {
                "group_id": v.group_id,
                "slot_id": str(v.slot_id) if v.slot_id else None,
                "von_datum": v.von_datum.isoformat(),
                "von_stunde": v.von_stunde,
                "nach_datum": v.nach_datum.isoformat(),
                "nach_stunde": v.nach_stunde,
                "periods": v.periods,
                "vorgezogen": v.rueckwaerts,
            }
            for v in plan.verlegungen
        ],
        "konflikte": [
            {
                "datum": k.datum.isoformat(),
                "stunde": k.start_period,
                "grund": k.grund,
                "beschreibung": k.beschreibung,
            }
            for k in plan.conflicts
        ],
        # Neu seit 22.09.2026: Termine, die der Abgleich anlegt, weil der Stundenplan
        # dort Unterricht kennt und die Planung keinen hatte. Getrennt von `konflikte` —
        # ein Hinweis ist etwas, das **nicht** geschah.
        "angelegte": [
            {
                "group_id": n.group_id,
                "datum": n.datum.isoformat(),
                "stunde": n.start_period,
                "kategorie": n.kategorie,
            }
            for n in plan.anzulegende
        ],
        "meldungen": plan.meldungen,
    }


@router.get("/sync/status")
async def sync_status(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_any_role(["teacher", "admin"])),
    _current=Depends(get_current_user),
) -> dict:
    """Wann zuletzt abgeglichen wurde und mit welchem Ergebnis.

    Billig — nur ein Datenbankzugriff, **keine** Verbindung zur Stundenplanquelle. Die
    Anzeige begleitet den Jahresplan und darf nicht von einem fremden Server abhängen.
    """
    from app.crons.calendar_sync_service import letzter_status

    if not is_configured():
        return {"configured": False, "status": None}

    prefs = await get_preferences(db, _current.sub)
    kuerzel = (prefs.get(KUERZEL_PREFERENCE_KEY) or "").strip()
    return {
        "configured": True,
        "kuerzel": kuerzel or None,
        "letzter_lauf": await letzter_status(db, _current.sub),
    }


@router.get("/sync/preview")
async def sync_preview(
    wochen: int = Query(1, ge=1, le=12),
    bis: date | None = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_any_role(["teacher", "admin"])),
    _current=Depends(get_current_user),
) -> dict:
    """Was der Abgleich ändern würde — **ohne** zu schreiben."""
    if not is_configured():
        return {"configured": False}
    try:
        plan, kontext, fehler = await _stundenplan_abgleich(db, _current.sub, wochen, bis)
    except CalendarSourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    if fehler:
        return {"configured": True, "hinweis": fehler, "aenderungen": []}
    return {"configured": True, **_plan_als_json(plan, kontext)}


@router.post("/sync")
async def sync_ausfuehren(
    wochen: int = Query(1, ge=1, le=12),
    bis: date | None = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_any_role(["teacher", "admin"])),
    _current=Depends(get_current_user),
) -> dict:
    """Entfall und Vertretung übernehmen. Rechnet den Plan neu, statt ihn mitzuschicken.

    Ein vom Client übergebener Plan wäre eine Einladung, fremde Slots zu ändern — und
    zwischen Vorschau und Klick kann sich der Stundenplan ohnehin geändert haben.
    """
    from app.calendar.sync import apply_sync

    if not is_configured():
        raise HTTPException(status_code=409, detail="Keine Stundenplanquelle eingerichtet.")
    try:
        plan, kontext, fehler = await _stundenplan_abgleich(db, _current.sub, wochen, bis)
    except CalendarSourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    if fehler:
        raise HTTPException(status_code=409, detail=fehler)

    geaendert = await apply_sync(db, plan)
    # Auch der Handabgleich zählt: Sonst zeigte die Statusanzeige den Stand des letzten
    # Cron-Laufs, obwohl gerade eben abgeglichen wurde.
    from app.crons.calendar_sync_service import _status_schreiben

    await _status_schreiben(
        db,
        _current.sub,
        "ok",
        changed=geaendert,
        conflicts=len(plan.conflicts),
        shifts=len(plan.verlegungen),
    )
    logger.info("Stundenplan-Abgleich für %s: %s Slots geändert", kontext["kuerzel"], geaendert)
    return {"geaendert": geaendert, **_plan_als_json(plan, kontext)}
