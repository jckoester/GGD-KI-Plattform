"""UP-8 Schritt 2 — WebUntis-Adapter.

Die Fixtures sind **echte, anonymisierte Antworten** von `ggd.webuntis.com`, aufgezeichnet
am 06.08.2026 mit `scripts/webuntis_probe.py --dump-fixture` (Kalenderwoche ab 06.07.2026,
ausgewählt wegen Verlegungen und Vertretungen). Kurzbezeichner sind durch Platzhalter
ersetzt, Freitextfelder geleert; IDs, Zeiten und Zustände sind unverändert.

Die Aufzeichnung hat drei Annahmen widerlegt, die vorher plausibel aussahen — siehe
`test_verlegung_*`, `test_vertretung_*` und `SLOT_CATEGORY`. Genau dafür gibt es sie.
"""
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.calendar import (
    AuthenticationError,
    CalendarSourceError,
    LessonState,
    NoActiveSchoolYearError,
)
from app.calendar.base import SLOT_CATEGORY
from app.calendar.webuntis import WebUntisAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES / f"webuntis_{name}.json").read_text(encoding="utf-8"))


WEEK = _load("week")
TIMEGRID = _load("timegrid")
HOLIDAYS = _load("holidays")
PAGECONFIG = _load("pageconfig")

# Der Plan der Woche gehört Element 640; die Aufzeichnung stammt aus dessen Stundenplan.
ELEMENT_NAME = next(
    entry["name"] for entry in PAGECONFIG["data"]["elements"] if entry["id"] == 640
)
MONDAY = date(2026, 7, 6)
PASSWORD = "P@ss wort!$geheim"


# Wie am GGD: das laufende und ein vorheriges Schuljahr.
SCHOOLYEARS = [
    {"id": 15, "name": "2024/2025", "startDate": 20240916, "endDate": 20250730},
    {"id": 18, "name": "2025/2026", "startDate": 20250915, "endDate": 20260729},
]

# Ferien mehrerer Jahre — `getHolidays` ignoriert das gesetzte Schuljahr und liefert alle.
FREMDJAHR = [
    {"id": 200, "name": "Alt", "longName": "Herbstferien",
     "startDate": 20241028, "endDate": 20241101},
]


def make_adapter(
    *, rpc_errors=None, week=WEEK, timegrid=TIMEGRID, holidays=HOLIDAYS,
    schoolyears=SCHOOLYEARS, needs_context=True,
):
    """Simuliert WebUntis samt Schuljahresbezug der Sitzung.

    `needs_context=True` bildet das belegte Verhalten nach: Ohne vorherigen Aufruf mit
    Datumsbereich scheitern `getHolidays` und `getTimegridUnits` mit -8998.
    """
    rpc_errors = rpc_errors or {}
    calls: list[str] = []
    zustand = {"context": False}
    NPE = {"code": -8998, "message": 'Cannot invoke "…Schoolyear.getStartDate()" '
                                     'because "sy" is null'}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/WebUntis/jsonrpc.do":
            body = json.loads(request.content)
            method, params = body["method"], body.get("params") or {}
            calls.append(method)
            if method in rpc_errors:
                return httpx.Response(200, json={"error": rpc_errors[method]})
            if method == "authenticate":
                zustand["context"] = False       # Bezug hängt an der Sitzung
                return httpx.Response(200, json={"result": {
                    "sessionId": "SESSION", "personType": 17, "personId": -1}})
            if method == "getSchoolyears":
                return httpx.Response(200, json={"result": schoolyears})
            if method in ("getClassregEvents", "getTimetable", "getExams"):
                zustand["context"] = True        # prägt das Jahr auf
                return httpx.Response(200, json={"result": []})
            if method in ("getHolidays", "getTimegridUnits", "getCurrentSchoolyear"):
                if needs_context and not zustand["context"]:
                    return httpx.Response(200, json={"error": NPE})
                if method == "getHolidays":
                    return httpx.Response(200, json={"result": holidays})
                if method == "getTimegridUnits":
                    return httpx.Response(200, json={"result": timegrid})
            return httpx.Response(200, json={"result": {}})
        if request.url.path.endswith("/weekly/pageconfig"):
            calls.append("pageconfig")
            return httpx.Response(200, json=PAGECONFIG)
        if request.url.path.endswith("/weekly/data"):
            calls.append(f"weekly:{request.url.params.get('date')}")
            return httpx.Response(200, json=week)
        return httpx.Response(404, text="unbekannter Pfad")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return WebUntisAdapter(
        server="ggd.webuntis.com", user="svc", password=PASSWORD, client=client
    ), calls


async def fetch(**kwargs):
    adapter, calls = make_adapter(**kwargs)
    async with adapter:
        return await adapter.fetch_week(ELEMENT_NAME, MONDAY), calls


def at(result, day: date, period: int):
    """Die Stunde an einem Termin — mehrere möglich, dann die erste."""
    return next(
        entry for entry in result.lessons
        if entry.date == day and entry.start_period == period
    )


def all_at(result, day: date, period: int):
    return [
        entry for entry in result.lessons
        if entry.date == day and entry.start_period == period
    ]


# ── Grundlast: die echte Woche geht vollständig durch ────────────────────────


@pytest.mark.asyncio
async def test_echte_woche_wird_vollstaendig_geparst():
    result, _ = await fetch()
    assert len(result.lessons) == 34
    assert result.warnings == []          # kein Zustand unbekannt, kein Datum fehlerhaft


@pytest.mark.asyncio
async def test_alle_vorkommenden_zustaende_sind_abgebildet():
    """Ein UNKNOWN in echten Daten hieße: eine Lücke in CELL_STATES."""
    result, _ = await fetch()
    assert not [entry for entry in result.lessons if entry.state is LessonState.UNKNOWN]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "day,period,expected,creates_slot",
    [
        (date(2026, 7, 6), 1, LessonState.REGULAR, True),          # STANDARD
        (date(2026, 7, 6), 3, LessonState.CANCELLED, True),        # CANCEL (Ursprung)
        (date(2026, 7, 6), 4, LessonState.SHIFTED, True),          # SHIFT (Ziel)
        # SUBSTITUTION: hier übernehme ICH die Aufsicht — fremder Unterricht, kein Slot.
        (date(2026, 7, 8), 4, LessonState.SUBSTITUTION, False),
        (date(2026, 7, 8), 3, LessonState.REGULAR, True),          # ROOMSUBSTITUTION
    ],
)
async def test_cellstate_abbildung(day, period, expected, creates_slot):
    result, _ = await fetch()
    lesson = at(result, day, period)
    assert lesson.state is expected
    assert lesson.creates_slot is creates_slot


@pytest.mark.asyncio
async def test_pausenaufsicht_erzeugt_keinen_slot():
    """`BREAKSUPERVISION` — der Zustand, der in der Juli-Erhebung noch fehlte."""
    result, _ = await fetch()
    aufsicht = [
        entry for entry in result.lessons
        if entry.state is LessonState.NON_TEACHING and entry.date == date(2026, 7, 6)
    ]
    assert aufsicht and not any(entry.creates_slot for entry in aufsicht)


@pytest.mark.asyncio
async def test_zusatztermin_erzeugt_keinen_slot():
    """`ADDITIONAL` (hier eine mehrtägige Fahrt) gehört nicht in die Jahresplanung."""
    result, _ = await fetch()
    zusatz = [entry for entry in result.lessons if entry.date == date(2026, 7, 10)
              and entry.state is LessonState.NON_TEACHING]
    assert zusatz and not any(entry.creates_slot for entry in zusatz)


# ── Verlegungen: das Paar aus CANCEL und SHIFT ───────────────────────────────


@pytest.mark.asyncio
async def test_verlegung_ist_ein_paar_mit_richtung():
    """Der Kern des Befunds vom 06.08.2026.

    Eine Verlegung steht **zweimal** in den Daten: am Ursprung als `CANCEL`
    (`isSource=true`), am Ziel als `SHIFT` (`isSource=false`) — mit derselben `lessonId`.
    Ohne die Richtung wäre nicht zu unterscheiden, wer abgegeben und wer aufgenommen hat.
    """
    result, _ = await fetch()
    ursprung = at(result, date(2026, 7, 6), 3)       # 9:50, CANCEL
    ziel = at(result, date(2026, 7, 6), 4)           # 10:35, SHIFT

    assert ursprung.external_uid == ziel.external_uid        # dieselbe Stunde
    assert ursprung.state is LessonState.CANCELLED
    assert ursprung.reschedule.is_source is True
    assert ursprung.reschedule.moved_to == date(2026, 7, 6)
    assert ursprung.reschedule.start_period == 4             # dorthin verlegt

    assert ziel.state is LessonState.SHIFTED
    assert ziel.reschedule.is_source is False
    assert ziel.reschedule.moved_from == date(2026, 7, 6)
    assert ziel.reschedule.moved_to is None                  # das Ziel gibt nichts ab


@pytest.mark.asyncio
async def test_verlegung_ueber_tage_hinweg():
    """Verlegt wird auch rückwärts: vom 09.07. auf den 06.07."""
    result, _ = await fetch()
    ziel = at(result, date(2026, 7, 6), 10)
    ursprung = next(
        entry for entry in all_at(result, date(2026, 7, 9), 10) if entry.reschedule
    )
    assert ziel.reschedule.moved_from == date(2026, 7, 9)
    assert ursprung.reschedule.moved_to == date(2026, 7, 6)
    assert ursprung.external_uid == ziel.external_uid


@pytest.mark.asyncio
async def test_zwei_eintraege_koennen_denselben_termin_belegen():
    """Am 09.07. um 15:40 liegen die mehrtägige Fahrt und die verlegte Stunde übereinander.

    Beim Anlegen der Slots (Schritt 8) darf das keine Kollision auslösen: Die Fahrt ist
    `NON_TEACHING` und erzeugt gar keinen Slot, der Ausfall schon. Der Adapter muss beide
    liefern — verwerfen wäre eine Entscheidung, die ihm nicht zusteht.
    """
    result, _ = await fetch()
    gleichzeitig = all_at(result, date(2026, 7, 9), 10)
    assert len(gleichzeitig) == 2
    assert sum(entry.creates_slot for entry in gleichzeitig) == 1


def test_verlegtes_ziel_ist_unterricht_kein_ausfall():
    """Die Stunde am SHIFT-Termin findet statt.

    Als `ausfall` geführt, verschwände sie aus der Jahresplanung, obwohl unterrichtet
    wird. Der Ausfall steckt in der Gegenseite des Paares, die ohnehin `CANCELLED` ist.
    """
    assert SLOT_CATEGORY[LessonState.SHIFTED] == "unterricht"
    assert SLOT_CATEGORY[LessonState.CANCELLED] == "ausfall"


# ── Vertretung ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_uebernommene_aufsicht_nennt_die_vertretene_lehrkraft():
    """Zweiter Befund der Aufzeichnung.

    Die Stammliste einer Wochenantwort enthält **nur** Elemente aus dem Plan der
    abgefragten Lehrkraft — die vertretene Kollegin steht gerade nicht darin. Ohne den
    Rückgriff auf die pageconfig-Zuordnung bliebe das Feld bei jeder Vertretung leer.
    """
    result, _ = await fetch()
    lesson = at(result, date(2026, 7, 8), 4)
    assert lesson.state is LessonState.SUBSTITUTION
    assert lesson.covering_for not in (None, ELEMENT_NAME)
    assert lesson.covered_by is None


@pytest.mark.asyncio
async def test_uebernommene_aufsicht_kommt_nicht_in_den_eigenen_jahresplan():
    """Wer im eigenen Plan eine Vertretung sieht, ist der **Vertretende**.

    Beleg aus der Aufzeichnung: Die beiden Vertretungsstunden tragen fremdes Fach und
    fremde Klasse und kommen genau **einmal** in der Woche vor — eigene Stunden 4–5×. Es
    ist der Unterricht einer anderen Lehrkraft. Als Slot angelegt, stünde eine fremde
    Stunde im eigenen Jahresplan.
    """
    result, _ = await fetch()
    aufsicht = [entry for entry in result.lessons if entry.covering_for]
    assert len(aufsicht) == 2
    assert not any(entry.creates_slot for entry in aufsicht)
    assert not any(entry.delivers_planned_content for entry in aufsicht)


@pytest.mark.asyncio
async def test_eigene_vertretene_stunde_verlangt_umplanung():
    """Die fachlich entscheidende Seite — **nicht** aufgezeichnet, siehe Modul-Kopf.

    „Vertretung" heißt an dieser Schule Aufsicht, nicht Fortführung des Unterrichts. Die
    vertretende Lehrkraft kann Aufgaben austeilen; das geplante Stundenziel wird nicht
    erreicht. Für die Jahresplanung ist die Stunde damit so gut wie ausgefallen: Sie
    erzeugt einen Slot, liefert aber keinen Inhalt.

    Konstruiert aus der echten Woche, indem die Rollen vertauscht werden: Die abgefragte
    Lehrkraft steht als `orgId`, eine andere als `id`.
    """
    kaputt = json.loads(json.dumps(WEEK))
    for periods in kaputt["data"]["result"]["data"]["elementPeriods"].values():
        for entry in periods:
            if entry["cellState"] != "SUBSTITUTION":
                continue
            for ref in entry["elements"]:
                if ref["type"] == 2 and ref.get("orgId"):
                    ref["id"], ref["orgId"] = ref["orgId"], 640

    result, _ = await fetch(week=kaputt)
    vertreten = [entry for entry in result.lessons if entry.covered_by]
    assert len(vertreten) == 2
    assert all(entry.covering_for is None for entry in vertreten)
    assert all(entry.creates_slot for entry in vertreten)              # Slot ja …
    assert not any(entry.delivers_planned_content for entry in vertreten)  # … Inhalt nein


@pytest.mark.asyncio
async def test_regulaere_stunde_erfindet_keine_vertretung():
    """`orgId = 0` heißt „kein Ersatz" — in der Aufzeichnung steht das an jedem Element."""
    result, _ = await fetch()
    regulaer = [entry for entry in result.lessons if entry.state is LessonState.REGULAR]
    assert regulaer
    assert all(entry.covering_for is None and entry.covered_by is None
               for entry in regulaer)
    assert all(entry.delivers_planned_content for entry in regulaer)


@pytest.mark.asyncio
async def test_ausfall_liefert_keinen_inhalt_verlegtes_ziel_schon():
    """Die Trennlinie zwischen `creates_slot` und `delivers_planned_content`."""
    result, _ = await fetch()
    assert not at(result, date(2026, 7, 10), 1).delivers_planned_content   # CANCEL
    assert at(result, date(2026, 7, 6), 4).delivers_planned_content        # SHIFT-Ziel


def test_orgid_null_ist_kein_element():
    """Direkt geprüft: Der Unterschied wird erst sichtbar, wenn die Stammliste einen
    Eintrag mit `id 0` enthält — sonst deckt die fehlgeschlagene Auflösung ihn zu."""
    from app.calendar.webuntis import ELEMENT_TEACHER, _original_name

    names = {(2, 0): "PHANTOM", (2, 11): "ABC", (2, 12): "XYZ"}
    assert _original_name({"elements": [{"type": 2, "id": 11, "orgId": 0}]},
                          ELEMENT_TEACHER, names) is None
    assert _original_name({"elements": [{"type": 2, "id": 11, "orgId": 12}]},
                          ELEMENT_TEACHER, names) == "XYZ"


# ── Unterrichtsgruppe (Grundlage für Schritt 7) ──────────────────────────────


@pytest.mark.asyncio
async def test_studentgroup_wird_uebernommen():
    """`studentGroup` trägt die Gruppenidentität (am GGD `Fach_Jahrgang_Kürzel`).

    Ohne sie müsste die Zuordnung zur `teaching_group` in Schritt 7 aus Fach und Klasse
    erraten werden — bei Differenzierungsgruppen mehrdeutig.
    """
    result, _ = await fetch()
    mit_gruppe = [entry for entry in result.lessons if entry.student_group]
    assert mit_gruppe
    assert at(result, date(2026, 7, 9), 3).student_group


# ── Zeitraster ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stundennummern_aus_dem_echten_zeitraster():
    """Elf Einheiten ab 7:55 — 1. Stunde 7:55, 2. 8:40, 3. 9:50, 4. 10:35."""
    result, _ = await fetch()
    assert at(result, date(2026, 7, 6), 1).state is LessonState.REGULAR
    assert at(result, date(2026, 7, 7), 3).state is LessonState.REGULAR
    assert {entry.start_period for entry in result.lessons if entry.start_period} <= set(
        range(1, 12)
    )


def test_alle_wochentage_teilen_ein_raster():
    """Die Sammel-und-sortiere-Logik setzt das voraus — an echten Daten geprüft."""
    raster = {
        tuple((unit["startTime"], unit["endTime"]) for unit in day["timeUnits"])
        for day in TIMEGRID
    }
    assert len(raster) == 1
    assert len(next(iter(raster))) == 11


@pytest.mark.asyncio
async def test_ohne_zeitraster_bleiben_stundennummern_offen():
    """Lieber keine Nummer als eine erfundene — mit Hinweis."""
    result, _ = await fetch(timegrid=[])
    assert all(entry.start_period is None for entry in result.lessons)
    assert any("Zeitraster" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_ergebnis_ist_chronologisch():
    result, _ = await fetch()
    reihenfolge = [(entry.date, entry.start_period or 0) for entry in result.lessons]
    assert reihenfolge == sorted(reihenfolge)


# ── Robustheit ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unbekannter_zustand_wird_gemeldet_nicht_verschluckt():
    """Eine sichtbare Lücke plus Meldung ist besser als ein geratener Slot."""
    kaputt = json.loads(json.dumps(WEEK))
    node = kaputt["data"]["result"]["data"]["elementPeriods"]["640"]
    node[0]["cellState"] = "WASIMMERDASIST"
    result, _ = await fetch(week=kaputt)
    betroffen = [entry for entry in result.lessons if entry.raw_state == "WASIMMERDASIST"]
    assert betroffen and not betroffen[0].creates_slot
    assert any("WASIMMERDASIST" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_eintrag_ohne_datum_wird_uebersprungen_und_gemeldet():
    kaputt = json.loads(json.dumps(WEEK))
    kaputt["data"]["result"]["data"]["elementPeriods"]["640"][0]["date"] = None
    result, _ = await fetch(week=kaputt)
    assert len(result.lessons) == 33
    assert any("ohne verwertbares Datum" in warning for warning in result.warnings)


# ── Abruf-Verhalten ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_beliebiges_datum_der_woche_ergibt_den_montag():
    adapter, calls = make_adapter()
    async with adapter:
        await adapter.fetch_week(ELEMENT_NAME, date(2026, 7, 9))   # Donnerstag
    assert "weekly:2026-07-06" in calls


@pytest.mark.asyncio
async def test_pro_lauf_genau_eine_anmeldung():
    adapter, calls = make_adapter()
    async with adapter:
        await adapter.fetch_week(ELEMENT_NAME, MONDAY)
        await adapter.fetch_week(ELEMENT_NAME, MONDAY)
    assert calls.count("authenticate") == 1
    assert calls.count("logout") == 1
    assert calls.count("pageconfig") == 1        # Zuordnung wird gemerkt


@pytest.mark.asyncio
async def test_kuerzel_ohne_ruecksicht_auf_gross_klein():
    adapter, _ = make_adapter()
    async with adapter:
        result = await adapter.fetch_week(ELEMENT_NAME.lower(), MONDAY)
    assert result.lessons


@pytest.mark.asyncio
async def test_unbekanntes_kuerzel_meldet_sich_klar():
    adapter, _ = make_adapter()
    async with adapter:
        with pytest.raises(CalendarSourceError, match="QQQ"):
            await adapter.fetch_week("QQQ", MONDAY)


@pytest.mark.asyncio
async def test_pageconfig_kennt_das_ganze_kollegium():
    """90 Lehrkräfte — die Grundlage für die Kürzel-Auswahl in Schritt 3."""
    adapter, _ = make_adapter()
    async with adapter:
        ids = await adapter.element_ids()
    assert len(ids) >= 90


# ── Ferienkalender ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ferien_werden_gelesen_aber_nicht_zusammengefuehrt():
    """Der Adapter liefert, was dasteht — Zusammenführen ist Sache des Imports.

    Die Aufzeichnung enthält die Weihnachtsferien als Block **plus** Einzeltag mit
    demselben Namen; genau das darf hier noch nicht verschwinden.
    """
    adapter, _ = make_adapter()
    async with adapter:
        holidays = await adapter.fetch_holidays()
    assert len(holidays) == len([h for h in HOLIDAYS if h.get("startDate")])
    assert holidays == sorted(holidays, key=lambda h: h.start)
    namen = [h.name for h in holidays]
    assert len(namen) > len(set(namen))          # ein Name kommt doppelt vor


@pytest.mark.asyncio
async def test_ferien_enthalten_einzeltage_und_bloecke():
    adapter, _ = make_adapter()
    async with adapter:
        holidays = await adapter.fetch_holidays()
    assert any(entry.is_single_day for entry in holidays)
    assert any(not entry.is_single_day for entry in holidays)


@pytest.mark.asyncio
async def test_ferieneintrag_ohne_datum_wird_uebersprungen():
    adapter, _ = make_adapter(holidays=[*HOLIDAYS, {"id": 9, "name": "kaputt",
                                                   "startDate": None, "endDate": None}])
    async with adapter:
        holidays = await adapter.fetch_holidays()
    assert len(holidays) == len([h for h in HOLIDAYS if h.get("startDate")])


@pytest.mark.asyncio
async def test_ferien_gehen_auch_ohne_laufendes_schuljahr():
    """Der Kern des Befunds aus `BEFUND-Schuljahreskontext.md`.

    Eine frische Sitzung hat **keinen** Schuljahresbezug; `getHolidays` scheitert dann mit
    -8998. Das ist kein Zeitpunktproblem, das man aussitzen müsste: Ein Aufruf mit
    Datumsbereich prägt der Sitzung das Jahr auf. Damit funktioniert der Abruf **auch in
    den Sommerferien**.
    """
    adapter, calls = make_adapter(needs_context=True)
    async with adapter:
        holidays = await adapter.fetch_holidays(
            within=(date(2025, 9, 15), date(2026, 7, 29))
        )
    assert holidays
    # Der Bezug wurde vor dem Ferienabruf gesetzt.
    assert calls.index("getClassregEvents") < calls.index("getHolidays")


@pytest.mark.asyncio
async def test_zieljahr_kommt_aus_getschoolyears():
    """Nicht aus `getCurrentSchoolyear` — genau die Methode fällt ohne Bezug aus, sie
    taugt also nicht zur Bestimmung dessen, was sie voraussetzt."""
    adapter, calls = make_adapter()
    async with adapter:
        await adapter.fetch_holidays(within=(date(2025, 9, 15), date(2026, 7, 29)))
    assert "getSchoolyears" in calls
    assert "getCurrentSchoolyear" not in calls


@pytest.mark.asyncio
async def test_rueckfall_auf_gettimetable_ohne_klassenbuchrecht():
    """Ein Konto ohne Klassenbuch-Recht wird bei `getClassregEvents` mit -8509 abgewiesen.
    Dann setzt `getTimetable` den Bezug — sonst bliebe der Ferienabruf unmöglich."""
    adapter, calls = make_adapter(rpc_errors={
        "getClassregEvents": {"code": -8509, "message": "no right for classregevents"},
    })
    async with adapter:
        holidays = await adapter.fetch_holidays(
            within=(date(2025, 9, 15), date(2026, 7, 29))
        )
    assert holidays
    assert "getTimetable" in calls


@pytest.mark.asyncio
async def test_ferien_fremder_jahre_werden_ausgefiltert():
    """`getHolidays` ignoriert das gesetzte Jahr und liefert alle (beobachtet: 72 Sätze
    ab 2020). Ohne Eingrenzung bekäme der Import lauter Abschnitte zum Verwerfen."""
    adapter, _ = make_adapter(holidays=[*HOLIDAYS, *FREMDJAHR])
    async with adapter:
        holidays = await adapter.fetch_holidays(
            within=(date(2025, 9, 15), date(2026, 7, 29))
        )
    assert all(h.start >= date(2025, 9, 15) for h in holidays)
    assert len(holidays) == len([h for h in HOLIDAYS if h.get("startDate")])


@pytest.mark.asyncio
async def test_ohne_eingrenzung_kommt_alles():
    adapter, _ = make_adapter(holidays=[*HOLIDAYS, *FREMDJAHR])
    async with adapter:
        holidays = await adapter.fetch_holidays()
    assert any(h.start.year == 2024 for h in holidays)


@pytest.mark.asyncio
async def test_zeitraster_braucht_ebenfalls_den_bezug():
    """`getTimegridUnits` fällt ohne Jahresbezug genauso aus — sonst blieben alle
    Stundennummern leer."""
    adapter, calls = make_adapter(needs_context=True)
    async with adapter:
        result = await adapter.fetch_week(ELEMENT_NAME, MONDAY)
    assert any(entry.start_period for entry in result.lessons)
    assert "Zeitraster" not in " ".join(result.warnings)


@pytest.mark.asyncio
async def test_bezug_wird_nur_einmal_gesetzt():
    """Ein Aufruf je Sitzung genügt — er überlebt beliebige weitere Aufrufe."""
    adapter, calls = make_adapter()
    async with adapter:
        await adapter.fetch_week(ELEMENT_NAME, MONDAY)
        await adapter.fetch_holidays(within=(date(2025, 9, 15), date(2026, 7, 29)))
    assert calls.count("getClassregEvents") == 1


@pytest.mark.asyncio
async def test_unsetzbarer_bezug_meldet_sich_verstaendlich():
    """Wenn beide Auslöser scheitern, ist das ein Rechteproblem — und wird so benannt,
    nicht als „warte auf das Schuljahr"."""
    adapter, _ = make_adapter(rpc_errors={
        "getClassregEvents": {"code": -8509, "message": "no right"},
        "getTimetable": {"code": -8509, "message": "no right"},
        "getHolidays": {"code": -8998, "message": '"sy" is null'},
    })
    async with adapter:
        with pytest.raises(CalendarSourceError, match="Berechtigung"):
            await adapter.fetch_holidays()


# ── Fehler und Geheimnisse ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_falsche_zugangsdaten_ergeben_authentication_error():
    adapter, _ = make_adapter(rpc_errors={"authenticate": {
        "code": -8504, "message": "bad credentials"}})
    with pytest.raises(AuthenticationError):
        await adapter.check()
    await adapter.close()


@pytest.mark.asyncio
async def test_schulkuerzel_fehler_erklaert_die_subdomain():
    """-8500 hat genau eine übliche Ursache — die gehört in die Meldung."""
    adapter, _ = make_adapter(rpc_errors={"authenticate": {
        "code": -8500, "message": "invalid schoolname"}})
    with pytest.raises(CalendarSourceError, match="Subdomain"):
        await adapter.check()
    await adapter.close()


@pytest.mark.asyncio
async def test_fehlermeldung_enthaelt_niemals_das_passwort():
    """Diese Meldung landet in `last_error` und damit in der Datenbank."""
    adapter, _ = make_adapter(rpc_errors={"authenticate": {
        "code": -7999,
        "message": f"failed for params {{'user': 'svc', 'password': '{PASSWORD}'}}",
    }})
    with pytest.raises(CalendarSourceError) as exc:
        await adapter.check()
    await adapter.close()
    assert PASSWORD not in str(exc.value)
    assert "geheim" not in str(exc.value)


@pytest.mark.asyncio
async def test_gescheiterte_abmeldung_entwertet_den_abruf_nicht():
    adapter, _ = make_adapter(rpc_errors={"logout": {"code": -1, "message": "weg"}})
    async with adapter:
        result = await adapter.fetch_week(ELEMENT_NAME, MONDAY)
    assert result.lessons


def test_leerer_server_wird_frueh_abgelehnt():
    with pytest.raises(CalendarSourceError, match="Server"):
        WebUntisAdapter(server="", user="svc", password="x")


def test_server_ohne_schema_bekommt_https():
    adapter = WebUntisAdapter(server="ggd.webuntis.com", user="svc", password="x")
    assert adapter.base == "https://ggd.webuntis.com"


# ── Datenschutz der Fixtures ─────────────────────────────────────────────────


def test_fixtures_enthalten_keine_freitexte():
    """Aufgezeichnete Antworten tragen Unterrichtsinhalte — die dürfen nicht ins Repo.

    Der Probelauf fand dort vollständige Arbeitsaufträge und den Namen einer Lehrkraft.
    `anonymize()` leert diese Felder; dieser Test hält fest, dass das so bleibt.
    """
    periods = [
        entry
        for value in WEEK["data"]["result"]["data"]["elementPeriods"].values()
        for entry in value
    ]
    for feld in ("lessonText", "periodText", "substText", "staffText", "periodInfo"):
        assert all(not entry.get(feld) for entry in periods), f"{feld} ist nicht leer"
