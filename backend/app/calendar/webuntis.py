"""WebUntis-Adapter (UP-8, Schritt 2).

Produktive Fassung dessen, was `scripts/webuntis_probe.py` am 06.08.2026 erkundet hat. Das
Skript bleibt als Diagnosewerkzeug bestehen — es beantwortet Fragen, dieser Adapter
liefert Daten.

Belegtes Verhalten des Dienstes, das hier hineinspielt:

* **Anmeldung ohne `school`-Parameter** bei eigener Subdomain (`ggd.webuntis.com`). Wird er
  mitgeschickt, antwortet WebUntis mit `invalid schoolname` (-8500).
* **Servicekonto ohne Personenbindung** (`personId = -1`) — Element-IDs kommen daher aus
  `weekly/pageconfig`, nicht aus dem eigenen Profil.
* **`getHolidays` zieht das Schuljahr aus der Sitzung**, nicht aus Parametern. Ohne aktives
  Schuljahr scheitert es mit -8998; das ist kein Defekt, sondern ein Zeitpunktproblem und
  bekommt deshalb `NoActiveSchoolYearError`.
* **Neu gegenüber der Juli-Erhebung:** der `cellState` `BREAKSUPERVISION` (Pausenaufsicht).

**Pro Lauf wird neu angemeldet.** Wie lange eine Sitzung über Stunden trägt, ist unbekannt
(Plan §7). Eine Anmeldung je Lauf kostet einen Request und erspart die gesamte Fehlerklasse
„Sitzung war doch abgelaufen" — die sich sonst als leerer Stundenplan tarnt.
"""
from __future__ import annotations

import base64
import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from app.calendar.base import (
    AuthenticationError,
    CalendarAdapter,
    CalendarSourceError,
    FetchResult,
    Holiday,
    Lesson,
    LessonState,
    NoActiveSchoolYearError,
    Reschedule,
)

logger = logging.getLogger(__name__)

# elementType der Wochenschnittstelle
ELEMENT_CLASS, ELEMENT_TEACHER, ELEMENT_SUBJECT, ELEMENT_ROOM = 1, 2, 3, 4

# `cellState` → normalisierter Zustand.
#
# Was hier NICHT steht, wird `UNKNOWN` und erzeugt keinen Slot — mit Warnung. Die Richtung
# ist bewusst: Eine sichtbare Lücke plus Meldung ist besser als ein Slot, dessen Kategorie
# geraten wurde. Führt WebUntis einen neuen Zustand ein, fällt das im Status auf, statt
# still falsche Einträge zu erzeugen.
CELL_STATES: dict[str, LessonState] = {
    "STANDARD": LessonState.REGULAR,
    # Raumwechsel ist Unterricht wie geplant, nur woanders.
    "ROOMSUBSTITUTION": LessonState.REGULAR,
    "EXAM": LessonState.EXAM,
    "CANCEL": LessonState.CANCELLED,
    "SUBSTITUTION": LessonState.SUBSTITUTION,
    "SHIFT": LessonState.SHIFTED,
    # Kein Unterricht: Pausenaufsicht, Bereitschaft, Zusatztermine.
    "BREAKSUPERVISION": LessonState.NON_TEACHING,
    "STANDBY": LessonState.NON_TEACHING,
    "ADDITIONAL": LessonState.NON_TEACHING,
    "FREE": LessonState.NON_TEACHING,
}

_RPC_TIMEOUT = 30.0


def _parse_untis_date(value: object) -> date | None:
    """`20260518` (int oder str) → `date`. Ungültiges ergibt None, nicht eine Ausnahme."""
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError:
        return None


def _parse_untis_time(value: object) -> int | None:
    """`815` / `1345` → Minuten seit Mitternacht. WebUntis schreibt HHMM ohne führende Null."""
    try:
        raw = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    hour, minute = divmod(raw, 100)
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return hour * 60 + minute


class WebUntisAdapter(CalendarAdapter):
    """Liest Stundenpläne und den Ferienkalender aus WebUntis.

    Als asynchroner Kontextmanager zu verwenden — dann sind An- und Abmeldung garantiert
    ein Paar:

        async with WebUntisAdapter(server=..., user=..., password=...) as api:
            result = await api.fetch_week("ABC", date.today())
    """

    def __init__(
        self,
        server: str,
        user: str,
        password: str,
        school: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        server = (server or "").strip().rstrip("/")
        if not server:
            raise CalendarSourceError("Kein WebUntis-Server konfiguriert")
        if not server.startswith(("http://", "https://")):
            server = f"https://{server}"
        self.base = server
        self._user = user
        self._password = password
        # Leer lassen bei eigener Subdomain — sonst -8500 `invalid schoolname`.
        self.school = (school or "").strip()
        self._client = client or httpx.AsyncClient(timeout=_RPC_TIMEOUT)
        self._owns_client = client is None
        self._logged_in = False
        self._element_ids: dict[str, int] | None = None
        self._timegrid: list[int] | None = None

    @property
    def name(self) -> str:
        return "webuntis"

    # ── Verbindung ────────────────────────────────────────────────────────────

    async def __aenter__(self) -> "WebUntisAdapter":
        await self._login()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def _rpc(self, method: str, params: dict | None = None) -> object:
        """Ein JSON-RPC-Aufruf. Wirft bei Fehlern eine passende `CalendarSourceError`.

        Serverantworten werden **nicht** unbesehen durchgereicht: Sie können den Aufruf
        samt Parametern enthalten, und die Parameter enthalten bei `authenticate` das
        Passwort. Was nach außen geht, ist hier formuliert.
        """
        try:
            response = await self._client.post(
                f"{self.base}/WebUntis/jsonrpc.do",
                params={"school": self.school} if self.school else {},
                json={"id": "ggd", "method": method, "params": params or {}, "jsonrpc": "2.0"},
            )
        except httpx.HTTPError as exc:
            raise CalendarSourceError(
                f"WebUntis nicht erreichbar ({type(exc).__name__})"
            ) from None

        if response.status_code != 200:
            raise CalendarSourceError(f"WebUntis antwortete mit HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise CalendarSourceError("WebUntis lieferte keine JSON-Antwort") from None

        if "error" in payload:
            raise self._translate_error(payload["error"], method)
        return payload.get("result")

    @staticmethod
    def _translate_error(error: object, method: str) -> CalendarSourceError:
        """Serverfehler in einen Typ übersetzen, der einen brauchbaren Rat trägt."""
        code = error.get("code") if isinstance(error, dict) else None
        message = str(error.get("message", "")) if isinstance(error, dict) else str(error)
        lowered = message.lower()

        if code == -8500 or "schoolname" in lowered:
            return CalendarSourceError(
                "WebUntis kennt das angegebene Schulkürzel nicht. Bei einer eigenen "
                "Subdomain muss das Feld leer bleiben."
            )
        if code == -8504 or "bad credentials" in lowered or "invalid credentials" in lowered:
            return AuthenticationError(
                "Anmeldung an WebUntis fehlgeschlagen — Benutzername oder Passwort falsch."
            )
        if code == -8998 or "schoolyear" in lowered or "sy is null" in lowered:
            return NoActiveSchoolYearError(
                "In WebUntis ist derzeit kein Schuljahr aktiv. Der Abruf ist erst möglich, "
                "wenn das Schuljahr freigeschaltet ist."
            )
        if code in (-8509, -8523) or "no right" in lowered or "not allowed" in lowered:
            return CalendarSourceError(
                f"Dem WebUntis-Konto fehlt die Berechtigung für '{method}'."
            )
        # Restfall: Code melden, Serviettentext nicht. Er könnte den Aufruf samt
        # Parametern enthalten — und die enthalten bei authenticate das Passwort.
        return CalendarSourceError(f"WebUntis meldete einen Fehler (Code {code}).")

    async def _login(self) -> None:
        if self._logged_in:
            return
        result = await self._rpc(
            "authenticate",
            {"user": self._user, "password": self._password, "client": "ggd-ki-plattform"},
        )
        if not isinstance(result, dict) or not result.get("sessionId"):
            raise AuthenticationError(
                "Anmeldung an WebUntis fehlgeschlagen — keine Sitzung erhalten."
            )
        self._client.cookies.set("JSESSIONID", str(result["sessionId"]))
        if self.school:
            # Nur auf geteilten Servern nötig; bei eigener Subdomain würde es stören.
            self._client.cookies.set(
                "schoolname", base64.b64encode(f"_{self.school}".encode()).decode()
            )
        self._logged_in = True

    async def close(self) -> None:
        if self._logged_in:
            try:
                await self._rpc("logout")
            except CalendarSourceError:
                # Eine gescheiterte Abmeldung darf keinen erfolgreichen Abruf entwerten.
                logger.debug("WebUntis-Abmeldung fehlgeschlagen", exc_info=True)
            self._logged_in = False
        if self._owns_client:
            await self._client.aclose()

    async def check(self) -> None:
        """Zugangsdaten prüfen, ohne Daten zu holen."""
        await self._login()

    # ── Stundenplan ───────────────────────────────────────────────────────────

    async def _get(self, path: str, params: dict) -> object:
        try:
            response = await self._client.get(f"{self.base}{path}", params=params)
        except httpx.HTTPError as exc:
            raise CalendarSourceError(
                f"WebUntis nicht erreichbar ({type(exc).__name__})"
            ) from None
        if response.status_code != 200:
            raise CalendarSourceError(f"WebUntis antwortete mit HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise CalendarSourceError("WebUntis lieferte keine JSON-Antwort") from None

    async def element_ids(self, element_type: int = ELEMENT_TEACHER) -> dict[str, int]:
        """Kürzel → `elementId`, aus `weekly/pageconfig`.

        Das Servicekonto hat keine Personenbindung, kann also nicht „den eigenen Plan"
        abrufen. Der Umweg über pageconfig ist deshalb keine Bequemlichkeit, sondern der
        einzige Weg an die IDs.
        """
        if self._element_ids is not None:
            return self._element_ids
        await self._login()
        payload = await self._get(
            "/WebUntis/api/public/timetable/weekly/pageconfig", {"type": element_type}
        )
        node = payload.get("data", payload) if isinstance(payload, dict) else {}
        elements = node.get("elements") if isinstance(node, dict) else None
        mapping: dict[str, int] = {}
        for entry in elements or []:
            if not isinstance(entry, dict) or entry.get("id") is None:
                continue
            for key in ("name", "displayname"):
                label = str(entry.get(key) or "").strip()
                if label:
                    mapping.setdefault(label.upper(), int(entry["id"]))
        self._element_ids = mapping
        return mapping

    async def _timegrid_starts(self) -> list[int]:
        """Beginnzeiten der Stunden in Minuten, aufsteigend.

        Grundlage für `start_period`: WebUntis nennt Uhrzeiten, die Planung zählt Stunden.
        Ohne diese Abbildung wäre jede Stundennummer geraten.
        """
        if self._timegrid is not None:
            return self._timegrid
        starts: set[int] = set()
        try:
            units = await self._rpc("getTimegridUnits")
        except CalendarSourceError:
            logger.info("Zeitraster nicht abrufbar — Stundennummern bleiben offen")
            units = None
        for day in units if isinstance(units, list) else []:
            for unit in (day.get("timeUnits") or []) if isinstance(day, dict) else []:
                minutes = _parse_untis_time(unit.get("startTime")) if isinstance(unit, dict) else None
                if minutes is not None:
                    starts.add(minutes)
        self._timegrid = sorted(starts)
        return self._timegrid

    async def fetch_week(self, element: str, week: date) -> FetchResult:
        """Stunden einer Kalenderwoche für ein Lehrkraft-Kürzel."""
        await self._login()
        ids = await self.element_ids()
        element_id = ids.get(element.strip().upper())
        if element_id is None:
            raise CalendarSourceError(
                f"WebUntis kennt das Kürzel '{element}' nicht."
            )

        monday = week - timedelta(days=week.weekday())
        payload = await self._get(
            "/WebUntis/api/public/timetable/weekly/data",
            {
                "elementType": ELEMENT_TEACHER,
                "elementId": element_id,
                "date": monday.isoformat(),
                "formatId": 1,
            },
        )
        starts = await self._timegrid_starts()
        # Umkehrung der pageconfig-Zuordnung: Die Stammliste einer Wochenantwort enthält
        # nur Elemente, die im Plan DIESER Lehrkraft vorkommen — die vertretene Kollegin
        # steht gerade nicht darin. Ohne diesen Rückgriff bliebe `original_teacher` bei
        # jeder Vertretung leer (belegt an der Aufzeichnung vom 06.08.2026).
        fallback = {(ELEMENT_TEACHER, eid): label for label, eid in ids.items()}
        return self._parse_week(payload, starts, fallback, element_id)

    def _parse_week(
        self,
        payload: object,
        period_starts: list[int],
        fallback_names: dict[tuple[int, int], str] | None = None,
        own_id: int | None = None,
    ) -> FetchResult:
        node = _dig(payload, ("data", "result", "data"))
        raw_periods = _collect_periods(node)
        names = {**(fallback_names or {}), **_element_names(node)}

        lessons: list[Lesson] = []
        skipped = 0
        unknown: set[str] = set()

        for entry in raw_periods:
            day = _parse_untis_date(entry.get("date"))
            if day is None:
                skipped += 1
                continue

            raw_state = str(entry.get("cellState") or "STANDARD").upper()
            state = CELL_STATES.get(raw_state, LessonState.UNKNOWN)
            if state is LessonState.UNKNOWN:
                unknown.add(raw_state)

            start_minutes = _parse_untis_time(entry.get("startTime"))
            end_minutes = _parse_untis_time(entry.get("endTime"))
            start_period = _period_number(start_minutes, period_starts)
            covering_for, covered_by = _substitution_roles(entry, names, own_id)
            lessons.append(
                Lesson(
                    date=day,
                    start_period=start_period,
                    periods=_period_count(start_minutes, end_minutes, period_starts),
                    state=state,
                    external_uid=str(entry["lessonId"]) if entry.get("lessonId") else None,
                    subject=_first_name(entry, ELEMENT_SUBJECT, names),
                    class_names=_all_names(entry, ELEMENT_CLASS, names),
                    teacher_names=_all_names(entry, ELEMENT_TEACHER, names),
                    room=_first_name(entry, ELEMENT_ROOM, names),
                    student_group=str(entry.get("studentGroup") or "") or None,
                    covering_for=covering_for,
                    covered_by=covered_by,
                    reschedule=_reschedule(entry, period_starts),
                    raw_state=raw_state if state is LessonState.UNKNOWN else None,
                )
            )

        warnings: list[str] = []
        if skipped:
            warnings.append(f"{skipped} Einträge ohne verwertbares Datum übersprungen")
        if unknown:
            warnings.append(
                "Unbekannte Stundenzustände übersprungen: " + ", ".join(sorted(unknown))
            )
        if not period_starts:
            warnings.append("Zeitraster nicht verfügbar — Stundennummern fehlen")

        lessons.sort(key=lambda entry: (entry.date, entry.start_period or 0))
        return FetchResult(
            lessons=lessons,
            warnings=warnings,
            fetched_at=datetime.now(timezone.utc),
        )

    # ── Ferienkalender ────────────────────────────────────────────────────────

    async def fetch_holidays(self) -> list[Holiday]:
        """Unterrichtsfreie Abschnitte des **laufenden** Schuljahres.

        Ohne aktives Schuljahr wirft der Dienst -8998; das übersetzt `_translate_error` in
        `NoActiveSchoolYearError`, damit die Oberfläche einen Zeitpunkt-Hinweis geben kann
        statt einer Fehlermeldung.

        Zusammengeführt wird hier **nicht**: WebUntis zerlegt Abschnitte (am GGD stehen die
        Weihnachtsferien als Block plus Einzeltag mit demselben Namen), das Zusammenführen
        gehört aber zum Import (Schritt 4), damit der Adapter liefert, was dasteht.
        """
        await self._login()
        result = await self._rpc("getHolidays")
        holidays: list[Holiday] = []
        for entry in result if isinstance(result, list) else []:
            if not isinstance(entry, dict):
                continue
            start = _parse_untis_date(entry.get("startDate"))
            if start is None:
                continue
            end = _parse_untis_date(entry.get("endDate")) or start
            holidays.append(
                Holiday(
                    start=start,
                    end=max(start, end),
                    name=str(entry.get("longName") or entry.get("name") or "Unterrichtsfrei"),
                )
            )
        holidays.sort(key=lambda h: h.start)
        return holidays


# ── Hilfsfunktionen zum Auswerten der Antwort ────────────────────────────────
#
# Die Verschachtelung der Wochenschnittstelle schwankt zwischen WebUntis-Versionen. Darum
# überall tolerant suchen statt einen festen Pfad anzunehmen — ein Adapter, der bei einem
# Zwischenschlüssel mehr aufgibt, ist bei der nächsten Aktualisierung fällig.


def _dig(payload: object, keys: tuple[str, ...]) -> object:
    node = payload
    for key in keys:
        if isinstance(node, dict) and key in node:
            node = node[key]
    return node


def _collect_periods(node: object) -> list[dict]:
    """Stundenliste aus `elementPeriods` (Dict {elementId: [...]}) oder einer Liste."""
    if isinstance(node, dict):
        periods = node.get("elementPeriods", node)
        if isinstance(periods, dict):
            return [
                entry
                for value in periods.values()
                if isinstance(value, list)
                for entry in value
                if isinstance(entry, dict)
            ]
        if isinstance(periods, list):
            return [entry for entry in periods if isinstance(entry, dict)]
    if isinstance(node, list):
        return [entry for entry in node if isinstance(entry, dict)]
    return []


def _element_names(node: object) -> dict[tuple[int, int], str]:
    """Stammliste (Typ, ID) → Kürzel.

    Die Perioden nennen nur IDs; die Klartexte stehen einmal zentral. Fehlt die Liste,
    bleiben die Namen leer — die Stunden selbst sind davon nicht betroffen.
    """
    elements = node.get("elements") if isinstance(node, dict) else None
    names: dict[tuple[int, int], str] = {}
    for entry in elements or []:
        if not isinstance(entry, dict) or entry.get("id") is None or entry.get("type") is None:
            continue
        label = str(entry.get("name") or entry.get("displayname") or "").strip()
        if label:
            names[(int(entry["type"]), int(entry["id"]))] = label
    return names


def _refs(entry: dict, element_type: int) -> list[dict]:
    return [
        ref
        for ref in (entry.get("elements") or [])
        if isinstance(ref, dict) and ref.get("type") == element_type
    ]


def _all_names(
    entry: dict, element_type: int, names: dict[tuple[int, int], str]
) -> tuple[str, ...]:
    found = []
    for ref in _refs(entry, element_type):
        label = names.get((element_type, ref.get("id")))
        if label and label not in found:
            found.append(label)
    return tuple(found)


def _first_name(
    entry: dict, element_type: int, names: dict[tuple[int, int], str]
) -> str | None:
    found = _all_names(entry, element_type, names)
    return found[0] if found else None


def _original_name(
    entry: dict, element_type: int, names: dict[tuple[int, int], str]
) -> str | None:
    """Wer ursprünglich vorgesehen war — `orgId` ist nur bei Vertretung gesetzt.

    `orgId = 0` heißt „kein Ersatz", nicht „Element 0". Ohne diese Prüfung würde jede
    reguläre Stunde eine erfundene Vertretung melden.
    """
    for ref in _refs(entry, element_type):
        org_id = ref.get("orgId")
        if org_id:
            label = names.get((element_type, int(org_id)))
            if label:
                return label
    return None


def _substitution_roles(
    entry: dict, names: dict[tuple[int, int], str], own_id: int | None
) -> tuple[str | None, str | None]:
    """Welche Rolle die abgefragte Lehrkraft in einer Vertretung hat.

    Gibt `(covering_for, covered_by)` zurück — höchstens eines ist gesetzt. Die
    Unterscheidung entscheidet, ob ein Slot entsteht:

    * **`id` ist meine, `orgId` eine fremde** → ich beaufsichtige fremden Unterricht. So
      liegt der Fall in der Aufzeichnung vom 06.08.2026 (belegt).
    * **`orgId` ist meine, `id` eine fremde** → meine Stunde wird beaufsichtigt, mein
      Stundenziel steht aus. Fachlich der wichtigere Fall, aber **nicht aufgezeichnet**:
      Dafür bräuchte es den Plan der abwesenden Lehrkraft. Die Zuordnung folgt der
      Bedeutung von `id`/`orgId`, nicht einer Beobachtung.

    Ohne bekannte eigene ID lässt sich nichts unterscheiden; dann wird die Stunde als
    „meine, beaufsichtigt" gelesen. Das ist die vorsichtige Richtung: Sie erzeugt einen
    Slot, der zur Umplanung auffordert, statt eine ausgefallene Stunde verschwinden zu
    lassen.
    """
    refs = _refs(entry, ELEMENT_TEACHER)
    substitute = None
    for ref in refs:
        org_id = ref.get("orgId")
        if not org_id:
            continue
        ref_id = ref.get("id")
        if own_id is not None and ref_id == own_id:
            return names.get((ELEMENT_TEACHER, int(org_id))) or "unbekannt", None
        if own_id is not None and int(org_id) == own_id:
            return None, names.get((ELEMENT_TEACHER, ref_id)) or "unbekannt"
        substitute = substitute or names.get((ELEMENT_TEACHER, ref_id))
    if substitute is not None:
        return None, substitute
    return None, None


def _reschedule(entry: dict, period_starts: list[int]) -> Reschedule | None:
    """Die andere Seite einer Verlegung.

    `isSource` trägt die Richtung: `true` an der abgebenden Seite (dort steht `CANCEL`),
    `false` an der aufnehmenden (dort steht `SHIFT`). Fehlt das Feld, wird der Termin als
    Ursprung gelesen — das ist die Lesart, bei der ein Irrtum nur einen überflüssigen
    Vorschlag erzeugt statt eine stattfindende Stunde zu verschlucken.
    """
    info = entry.get("rescheduleInfo")
    if not isinstance(info, dict):
        return None
    target = _parse_untis_date(info.get("date"))
    if target is None:
        return None
    return Reschedule(
        date=target,
        start_period=_period_number(_parse_untis_time(info.get("startTime")), period_starts),
        is_source=bool(info.get("isSource", True)),
    )


def _period_number(start_minutes: int | None, period_starts: list[int]) -> int | None:
    """Uhrzeit → Stundennummer (1-basiert) anhand des Zeitrasters."""
    if start_minutes is None or not period_starts:
        return None
    for index, begin in enumerate(period_starts, start=1):
        if start_minutes == begin:
            return index
    # Kein exakter Treffer: die letzte Stunde nehmen, die nicht später beginnt. Deckt
    # verschobene Anfangszeiten ab, ohne eine Stunde zu erfinden.
    earlier = [i for i, begin in enumerate(period_starts, start=1) if begin <= start_minutes]
    return earlier[-1] if earlier else None


def _period_count(
    start_minutes: int | None, end_minutes: int | None, period_starts: list[int]
) -> int:
    """Wie viele Stunden ein Eintrag umfasst (Doppelstunden kommen als ein Eintrag)."""
    if start_minutes is None or end_minutes is None or not period_starts:
        return 1
    covered = [b for b in period_starts if start_minutes <= b < end_minutes]
    return max(1, len(covered))
