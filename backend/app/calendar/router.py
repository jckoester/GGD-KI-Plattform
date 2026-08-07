"""Kalender-Endpunkte (UP-8).

Bisher nur die Kürzel-Liste für die Profileinstellung (Schritt 3).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_any_role
from app.calendar.base import CalendarSourceError
from app.calendar.groups import kein_unterricht_codes, match_groups
from app.calendar.patterns import derive_patterns
from app.calendar.service import (
    KUERZEL_PREFERENCE_KEY,
    get_adapter,
    is_configured,
    list_kuerzel,
)
from app.db.session import get_db
from app.planning.calendar import is_schoolday, load_school_year
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


def _unterrichtswochen(referenz: date, anzahl: int) -> list[date]:
    """Die jüngsten `anzahl` **zusammenhängenden** Unterrichtswochen vor `referenz`.

    Zwei Anforderungen, die einander widersprechen könnten:

    * **Ferienwochen dürfen nicht mitzählen.** Sonst wäre der Nenner falsch: „in 2 von 4
      Wochen gesehen" hieße bei zwei Ferienwochen in Wahrheit „in 2 von 2" — und jeder
      wöchentliche Termin sähe 14-tägig aus.
    * **Die Wochen müssen aneinandergrenzen.** Über eine Ferienlücke hinweg ist nicht
      bestimmbar, ob der A/B-Takt nach Kalenderwochen weiterläuft oder neu anfängt. Aus
      Wochen mit Lücke einen Rhythmus abzuleiten hieße raten.

    Deshalb wird rückwärts nach dem jüngsten **ununterbrochenen** Lauf gesucht, statt
    Ferienwochen einfach zu überspringen. Rückwärts, weil vergangene Wochen belegt sind;
    kommende sind Planung.
    """
    cfg = load_school_year()
    montag = referenz - timedelta(days=referenz.weekday())
    lauf: list[date] = []
    bester: list[date] = []
    # Zwei Schuljahre Rückblick als Notbremse — älteres wäre ohnehin nicht aussagekräftig.
    for _ in range(104):
        if montag < cfg.beginn:
            break
        if any(is_schoolday(montag + timedelta(days=n), cfg) for n in range(5)):
            lauf.append(montag)
            if len(lauf) >= anzahl:
                return sorted(lauf)
        else:
            if len(lauf) > len(bester):
                bester = lauf
            lauf = []
        montag -= timedelta(weeks=1)
    return sorted(lauf if len(lauf) > len(bester) else bester)


def _abgleich_wochen(
    referenz: date, rueckblick: int = 1, vorausschau: int = 2
) -> list[date]:
    """Kalenderwochen für den **Abgleich** — anderes Fenster als für die Musterableitung.

    Zwei Unterschiede zu `_unterrichtswochen`, beide wesentlich:

    * **Nach vorn.** Eine Verlegung zeigt fast immer in die Zukunft; ihr Ziel liegt in
      einer kommenden Woche. Ein reiner Rückblick fände den Ursprung und nie das Ziel.
    * **Lücken sind erlaubt.** Die Musterableitung braucht zusammenhängende Wochen, sonst
      ist der A-/B-Takt nicht bestimmbar. Der Abgleich braucht das nicht — er braucht die
      **jüngsten** Wochen. Mit der Zusammenhangs-Regel landete er nach jeden Ferien
      wochenlang in der Vergangenheit statt in der Gegenwart.

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


@router.get("/week-patterns")
async def week_patterns(
    wochen: int = Query(4, ge=1, le=12),
    bis: date | None = None,
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

    kalenderwochen = _unterrichtswochen(bis or date.today(), wochen)
    if not kalenderwochen:
        raise HTTPException(
            status_code=409,
            detail="Im Schuljahr liegen vor diesem Datum keine Unterrichtswochen.",
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

    result = derive_patterns(
        stunden,
        wochen=kalenderwochen,
        timegrid=raster,
        kein_unterricht=kein_unterricht_codes(),
    )
    # Aus welchem Halbjahr die Wochen stammen — der Editor schreibt je Halbjahr, und ein
    # Muster ins falsche zu übernehmen wäre schwer zu bemerken.
    cfg = load_school_year()
    halbjahr = 1 if kalenderwochen[-1] < cfg.halbjahreswechsel else 2
    # Schritt 7: Die erkannten Lerngruppen gegen die Unterrichtsgruppen der Plattform
    # abgleichen. Erst damit wird aus einem Muster ein schreibbarer Vorschlag — und erst
    # hier fällt auf, wenn ein Fachkürzel keinem Fach zugeordnet ist.
    abgleich = await match_groups(db, [p.key for p in result.proposals])
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
        ],
    }


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

    from app.calendar.groups import kein_unterricht_codes, match_groups
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

    muster = derive_patterns(
        stunden,
        wochen=kalenderwochen,
        timegrid=raster,
        kein_unterricht=kein_unterricht_codes(),
    )
    abgleich = await match_groups(db, [p.key for p in muster.proposals])

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
                "SELECT id, group_id, date, start_period, kategorie, pinned, source, note "
                "FROM lesson_slots WHERE group_id = ANY(:gruppen) "
                "AND date BETWEEN :von AND :bis"
            ),
            {"gruppen": gruppen, "von": zeitraum[0], "bis": zeitraum[1]},
        )
        slots = [
            SlotRef(
                id=r[0], group_id=r[1], datum=r[2], start_period=r[3] or 0,
                kategorie=r[4], pinned=r[5], source=r[6], note=r[7],
            )
            for r in rows.fetchall()
        ]

    plan = plan_sync(zugeordnet, slots, zeitraum=zeitraum)
    return plan, {"kuerzel": kuerzel, "wochen": kalenderwochen, "gruppen": gruppen}, None


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
