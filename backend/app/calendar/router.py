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
