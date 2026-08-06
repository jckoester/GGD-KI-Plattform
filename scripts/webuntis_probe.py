#!/usr/bin/env python3
"""
Prüft ein technisches WebUntis-Servicekonto — Entscheidungsgrundlage für UP-8.

**Diagnosewerkzeug, kein Produktcode.** Es schreibt nichts und ändert nichts; es liest und
berichtet. Gedacht für einen einmaligen Lauf, sobald der Untis-Betreuer ein Servicekonto
eingerichtet hat, und für eine Wiederholung nach WebUntis-Updates.

Hintergrund (Konzept: `Notiz-Stundenplan-Kalender-Integration.md`): Die Wochenschnittstelle
`/WebUntis/api/public/timetable/weekly/data` liefert typisierte Stundenpläne samt `cellState`
(Entfall, Vertretung, Verlegung). Am 28.07.2026 wurde sie über 26 vergangene Wochen geprüft —
allerdings mit einem **persönlichen** Zugang. Anonymer Zugang wird am GGD nicht freigeschaltet
(Sicherheitsentscheidung, 05.08.2026). Es bleibt die Frage, ob ein **technisches Konto**
denselben Zugang bekommt — und was es dabei zu sehen bekommt.

Sechs Fragen, die der Lauf beantwortet:

  A  Kommt das Konto neben dem SSO an eine Anmeldung?
  B  Liefert die Wochenschnittstelle dieselben Felder wie die Probe (cellState, rescheduleInfo,
     elements/orgId, lessonId)?
  C  Wie weit reicht sie in die Vergangenheit? (löst das Sommerferien-Datenproblem)
  D  Datenoberfläche: nur ein Plan oder alle — und kommt das Konto an Schülerdaten?
  E  Liefert sie den Ferienkalender samt der acht **beweglichen** Ferientage? Die legt jede
     Stadt bzw. Schule selbst; in keinem Landeskalender stehen sie. Ein JA erspart Datenstrom A
     die zweite Quelle. `getHolidays` bezieht sich auf das **laufende** Schuljahr — ist keines
     aktiv (Sommerferien), scheitert es mit `-8998`. Der Abschnitt probiert deshalb mehrere
     Aufrufformen durch (ohne Parameter, `schoolyearId`, Datumsbereich) und durchsucht
     zuletzt die Wochenantwort, die auch ohne aktives Schuljahr funktioniert.
     Mit `--schoolyear` lässt sich ein bestimmtes Jahr vorgeben.
  F  Sitzungsverhalten: hält eine Anmeldung, oder braucht jeder Lauf eine neue?

⚠️ **Frage D kann bewusst GEGEN das Servicekonto ausgehen.** Sieht es die ganze Schule
einschließlich Schülerdaten, ist das datenschutzrechtlich teuer — dann ist Weg 1 (persönliches
ICS-Abo, genau ein Plan) trotz seiner funktionalen Schwächen die bessere Wahl. Der Lauf soll
diese Entscheidung ermöglichen, nicht vorwegnehmen.

Zugangsdaten — **niemals** in diese Datei schreiben:

    export WEBUNTIS_BASE="ggd.webuntis.com"      # mit oder ohne https:// — beides geht
    export WEBUNTIS_USER="<servicekonto>"
    export WEBUNTIS_SCHOOL="<schulkuerzel>"      # NUR bei geteiltem Server nötig

**Das Passwort wird abgefragt**, wenn es nicht gesetzt ist — kein Quoting-Ärger mit
Sonderzeichen, keine Spur in der Shell-History, und es steht nicht in der Prozessumgebung
(die `ps e` und Kindprozesse mitlesen können). Drei Wege, in dieser Reihenfolge:

    python scripts/webuntis_probe.py                     # fragt interaktiv (empfohlen)
    pass show untis/service | python scripts/webuntis_probe.py --password-stdin
    export WEBUNTIS_PASSWORD='...'                       # einfache Anführungszeichen!

Bei `export` schützen **einfache** Anführungszeichen fast alles — `$`, `!`, Leerzeichen,
Backslash. Nur ein einfaches Anführungszeichen im Passwort selbst braucht dann `'\''`.

`WEBUNTIS_SCHOOL` ist das Kürzel aus der Login-URL (`.../WebUntis/?school=<kuerzel>`). Bei
einer **schulspezifischen Subdomain** wie `ggd.webuntis.com` gibt es keines — dann leer
lassen bzw. weglassen; der Server kennt die Schule implizit. Wird es fälschlich mitgeschickt,
antwortet WebUntis mit `invalid schoolname` (-8500).

Verwendung:

    python scripts/webuntis_probe.py                       # alle Prüfungen
    python scripts/webuntis_probe.py --element-id 42       # Plan einer bestimmten Lehrkraft
    python scripts/webuntis_probe.py --weeks 2026-03-02 2026-06-15
    python scripts/webuntis_probe.py --no-surface          # Frage D auslassen

Abhängigkeit: `httpx` (in `requirements-scripts.txt`).
"""
import argparse
import base64
import getpass
import json
import os
import sys
from collections import Counter
from datetime import date, timedelta

try:
    import httpx
except ImportError:  # pragma: no cover
    sys.exit("httpx fehlt — `pip install -r requirements-scripts.txt`")

# elementType der Wochenschnittstelle
ELEMENT_CLASS, ELEMENT_TEACHER, ELEMENT_SUBJECT, ELEMENT_ROOM, ELEMENT_STUDENT = 1, 2, 3, 4, 5

# Felder, deren Vorhandensein die Machbarkeit von Datenstrom C entscheidet.
REQUIRED_FIELDS = {
    "cellState": "Entfall/Vertretung überhaupt erkennbar",
    "lessonId": "stabile Identität für idempotente Läufe (external_uid)",
    "elements": "typisierte Klasse/Lehrkraft/Fach/Raum statt Freitext",
}


def _mark(ok: bool | None) -> str:
    return {True: "  JA   ", False: "  NEIN ", None: "  ?    "}[ok]


def _section(title: str) -> None:
    print(f"\n{'─' * 78}\n{title}\n{'─' * 78}")


class WebUntis:
    """Minimaler Client — nur so viel, wie die Prüfung braucht."""

    def __init__(self, base: str, school: str = "") -> None:
        # Host mit oder ohne Schema akzeptieren — die vorhandenen webuntis-Tools führen ihn
        # ohne (`ggd.webuntis.com`), da soll man nicht umlernen müssen.
        base = base.strip().rstrip("/")
        if not base.startswith(("http://", "https://")):
            base = f"https://{base}"
        self.base = base
        self.school = school
        self.client = httpx.Client(timeout=30.0, follow_redirects=False)
        self.person_type: int | None = None
        self.person_id: int | None = None

    def rpc(self, method: str, params: dict | None = None) -> tuple[bool, object]:
        """Ein JSON-RPC-Aufruf. Gibt (Erfolg, Ergebnis|Fehlermeldung) zurück.

        Der JSON-RPC-Weg ist der stabilste über WebUntis-Versionen hinweg. Schlägt er fehl,
        ist die Meldung des Servers wichtiger als jede Vermutung — sie wird durchgereicht.
        """
        # Bei schulspezifischer Subdomain darf `school` NICHT mitgeschickt werden —
        # sonst antwortet WebUntis mit `invalid schoolname` (-8500).
        try:
            response = self.client.post(
                f"{self.base}/WebUntis/jsonrpc.do",
                params={"school": self.school} if self.school else {},
                json={"id": "probe", "method": method,
                      "params": params or {}, "jsonrpc": "2.0"},
            )
        except Exception as exc:
            return False, f"Verbindung fehlgeschlagen: {type(exc).__name__}: {exc}"

        if response.status_code != 200:
            return False, f"HTTP {response.status_code} — {response.text[:200]}"
        try:
            data = response.json()
        except Exception:
            return False, f"Keine JSON-Antwort: {response.text[:160]}"
        if "error" in data:
            err = data["error"]
            hint = ""
            if err.get("code") == -8500 or "schoolname" in str(err.get("message", "")):
                hint = (
                    "\n       → WEBUNTIS_SCHOOL passt nicht. Bei einer schulspezifischen "
                    "Subdomain (z. B. ggd.webuntis.com) die Variable ganz weglassen; sonst "
                    "das Kürzel aus der Login-URL `?school=…` verwenden."
                )
            return False, f"{err.get('code')}: {err.get('message')}{hint}"
        return True, data.get("result")

    def login(self, user: str, password: str) -> tuple[bool, str]:
        """Anmeldung. Gibt (Erfolg, Meldung) zurück."""
        ok, result = self.rpc(
            "authenticate",
            {"user": user, "password": password, "client": "ggd-ki-probe"},
        )
        if not ok:
            return False, str(result)
        if not isinstance(result, dict):
            return False, f"Unerwartete Antwort: {json.dumps(result)[:200]}"
        session_id = result.get("sessionId")
        if not session_id:
            return False, f"Kein sessionId in der Antwort: {json.dumps(result)[:200]}"

        self.person_type = result.get("personType")
        self.person_id = result.get("personId")
        self.client.cookies.set("JSESSIONID", session_id)
        # Das `schoolname`-Cookie braucht die Wochenschnittstelle nur auf geteilten Servern.
        # Bei eigener Subdomain würde ein gesetztes Cookie eher stören als helfen.
        if self.school:
            self.client.cookies.set(
                "schoolname", base64.b64encode(f"_{self.school}".encode()).decode()
            )
        return True, f"personType={self.person_type}, personId={self.person_id}"

    def weekly(self, element_type: int, element_id: int, day: date) -> tuple[int, dict | str]:
        """Rohantwort der Wochenschnittstelle. (status, json|text)"""
        response = self.client.get(
            f"{self.base}/WebUntis/api/public/timetable/weekly/data",
            params={
                "elementType": element_type,
                "elementId": element_id,
                "date": day.isoformat(),
                "formatId": 1,
            },
        )
        try:
            return response.status_code, response.json()
        except Exception:
            return response.status_code, response.text[:300]

    def pageconfig(self, element_type: int) -> tuple[int, list[dict]]:
        """Auswählbare Elemente eines Typs (Lehrkräfte, Klassen, Schüler:innen).

        Das ist zugleich die ehrlichere Datenschutz-Prüfung als ein Stundenplan-Abruf:
        Schon die **Aufzählbarkeit** ist die Exposition. Wer alle Schüler:innen listen kann,
        hat Zugriff auf personenbezogene Daten — unabhängig davon, ob ein Plan zurückkommt.
        """
        response = self.client.get(
            f"{self.base}/WebUntis/api/public/timetable/weekly/pageconfig",
            params={"type": element_type},
        )
        if response.status_code != 200:
            return response.status_code, []
        try:
            payload = response.json()
        except Exception:
            return response.status_code, []
        node = payload.get("data", payload)
        elements = node.get("elements") if isinstance(node, dict) else None
        return response.status_code, [e for e in (elements or []) if isinstance(e, dict)]

    def holidays(self) -> tuple[bool, object]:
        """Ferienkalender der Schule, wie er in WebUntis gepflegt ist.

        Entscheidend für UP-8 Schritt 4: Die **beweglichen Ferientage** legt jede Stadt bzw.
        Schule selbst; in einem allgemeinen Landeskalender stehen sie nicht. Gibt WebUntis
        sie heraus, entfällt für Datenstrom A die zweite Quelle.

        Der Aufruf bezieht sich implizit auf das **laufende** Schuljahr. Ist keines aktiv
        (typisch in den Sommerferien, bevor das neue Jahr freigeschaltet ist), scheitert er
        serverseitig — siehe `interpret_holiday_error`.
        """
        return self.rpc("getHolidays")

    def schoolyears(self) -> tuple[bool, object]:
        """Alle angelegten Schuljahre — Kontext für die Deutung von `getHolidays`."""
        return self.rpc("getSchoolyears")

    def current_schoolyear(self) -> tuple[bool, object]:
        """Das laufende Schuljahr, falls eines aktiv ist."""
        return self.rpc("getCurrentSchoolyear")

    def close(self) -> None:
        try:
            self.rpc("logout")
        except Exception:
            pass
        self.client.close()


def _periods(payload: dict) -> list[dict]:
    """Gräbt die Stundenliste aus der verschachtelten Antwort.

    Die Struktur variiert zwischen WebUntis-Versionen; darum tolerant suchen statt einen
    festen Pfad anzunehmen.
    """
    if not isinstance(payload, dict):
        return []
    node = payload.get("data", payload)
    for key in ("result", "data", "elementPeriods"):
        if isinstance(node, dict) and key in node:
            node = node[key]
    if isinstance(node, dict):
        # elementPeriods ist ein Dict {elementId: [perioden]}
        collected: list[dict] = []
        for value in node.values():
            if isinstance(value, list):
                collected.extend(v for v in value if isinstance(v, dict))
        return collected
    if isinstance(node, list):
        return [v for v in node if isinstance(v, dict)]
    return []


def _untis_date(value: object) -> date | None:
    """WebUntis-Datum (`20260330` als int oder str) in ein `date` überführen."""
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError:
        return None


def parse_holidays(result: object) -> tuple[list[tuple[date, date, str]], int]:
    """Ferieneinträge in (start, ende, name) überführen. Gibt (Einträge, Übersprungene).

    Beschädigte Einträge dürfen die brauchbaren nicht mitreißen — sie werden gezählt und
    gemeldet, nicht verschwiegen.
    """
    entries: list[tuple[date, date, str]] = []
    skipped = 0
    for item in result if isinstance(result, list) else []:
        start = _untis_date(item.get("startDate")) if isinstance(item, dict) else None
        if not start:
            skipped += 1
            continue
        end = _untis_date(item.get("endDate")) or start
        entries.append((start, end, str(item.get("longName") or item.get("name") or "—")))
    entries.sort()
    return entries, skipped


def merge_adjacent(entries: list[tuple[date, date, str]]) -> list[tuple[date, date, str]]:
    """Führt gleichnamige, zusammenhängende Einträge zusammen.

    WebUntis zerlegt einen Ferienabschnitt mitunter in mehrere Einträge — am GGD stehen
    die Weihnachtsferien als Block 22.12.–04.01. **plus** ein Einzeltag 05.01. mit
    demselben Namen. Ohne Zusammenführung sähe dieser Bruchteil wie ein einzelner
    unterrichtsfreier Tag aus und würde falsch einsortiert.

    Zusammengeführt wird nur bei **gleichem Namen** und wenn zwischen beiden höchstens ein
    Wochenende liegt. Verschiedene Namen bleiben getrennt (Christi Himmelfahrt und der
    Brückentag danach sind zwei Sachverhalte, auch wenn sie aneinandergrenzen).
    """
    merged: list[tuple[date, date, str]] = []
    for start, end, name in sorted(entries):
        if merged:
            prev_start, prev_end, prev_name = merged[-1]
            gap = [prev_end + timedelta(days=n) for n in range(1, (start - prev_end).days)]
            if prev_name.strip().lower() == name.strip().lower() and all(
                d.weekday() >= 5 for d in gap
            ):
                merged[-1] = (prev_start, max(prev_end, end), prev_name)
                continue
        merged.append((start, end, name))
    return merged


def find_keys(node: object, needles: tuple[str, ...], path: str = "",
              depth: int = 0) -> list[tuple[str, str]]:
    """Sucht rekursiv nach Schlüsseln, deren Name eine der Nadeln enthält.

    Für die Sondierung unbekannter Antworten: Statt Endpunkte zu raten, wird die Antwort
    durchsucht, die nachweislich funktioniert. Was gefunden wird, ist belegt — was nicht,
    ist wenigstens nicht erfunden.
    """
    if depth > 6:
        return []
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if any(n in str(key).lower() for n in needles):
                found.append((here, json.dumps(value, ensure_ascii=False)[:70]))
            found.extend(find_keys(value, needles, here, depth + 1))
    elif isinstance(node, list):
        for value in node[:3]:            # Stichprobe genügt; Listen sind gleichförmig
            found.extend(find_keys(value, needles, f"{path}[]", depth + 1))
    return found


def interpret_holiday_error(message: str) -> str | None:
    """Deutet einen `getHolidays`-Fehler, soweit er eindeutig ist.

    Wichtig für die Aussagekraft des Laufs: Ein Fehler ist nicht automatisch ein Nein.
    Reicht der Server eine Java-NullPointer-Meldung über ein fehlendes `Schoolyear` durch,
    ist der Aufruf durch die **Rechteprüfung hindurch** und erst in der Fachlogik gescheitert
    — die Frage bleibt dann offen, statt verneint zu sein.
    """
    lowered = message.lower()
    if "schoolyear" in lowered or "sy is null" in lowered or "-8998" in lowered:
        return (
            "Kein aktives Schuljahr — der Server stolpert über `Schoolyear == null`.\n"
            "       Das ist KEINE Absage: Der Aufruf kam durch die Rechteprüfung und scheiterte\n"
            "       erst in der Fachlogik. Bei fehlender Berechtigung käme ein Rechte-Fehlercode,\n"
            "       keine NullPointer-Meldung. Die Frage bleibt damit OFFEN.\n"
            "       → Sobald das neue Schuljahr in WebUntis freigeschaltet ist, erneut laufen\n"
            "         lassen. Bis dahin gilt die Rückfallebene aus UP-8 Schritt 4."
        )
    if "no right" in lowered or "not allowed" in lowered or "-8509" in lowered:
        return (
            "Dem Konto fehlt das Recht, den Ferienkalender zu lesen.\n"
            "       Das ist ein echtes Nein — beim Untis-Betreuer erfragen, ob sich das\n"
            "       Leserecht ergänzen lässt; sonst greift die Rückfallebene."
        )
    return None


def probe_week(api: WebUntis, element_type: int, element_id: int, day: date) -> dict:
    status, payload = api.weekly(element_type, element_id, day)
    if status != 200 or isinstance(payload, str):
        return {"ok": False, "status": status, "detail": str(payload)[:160]}
    periods = _periods(payload)
    return {
        "ok": True,
        "status": status,
        "count": len(periods),
        "states": Counter(p.get("cellState") for p in periods if p.get("cellState")),
        "fields": {f: any(f in p for p in periods) for f in REQUIRED_FIELDS},
        "has_reschedule": any("rescheduleInfo" in p for p in periods),
        "has_orgid": any(
            isinstance(e, dict) and "orgId" in e
            for p in periods for e in (p.get("elements") or [])
        ),
    }


def _read_password(from_stdin: bool) -> str:
    """Passwort besorgen — Pipe, Umgebungsvariable oder interaktive Abfrage.

    Die Abfrage ist der Standardweg: Sonderzeichen brauchen dann kein Shell-Quoting, das
    Passwort landet weder in der History noch in der Prozessumgebung.
    """
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    from_env = os.environ.get("WEBUNTIS_PASSWORD")
    if from_env:
        return from_env
    if not sys.stdin.isatty():
        sys.exit("Kein Passwort: weder WEBUNTIS_PASSWORD gesetzt noch ein Terminal für die "
                 "Abfrage. Bei Pipes --password-stdin verwenden.")
    return getpass.getpass(f"Passwort für {os.environ['WEBUNTIS_USER']}: ")


def main() -> None:
    parser = argparse.ArgumentParser(description="WebUntis-Servicekonto prüfen (UP-8)")
    parser.add_argument("--element-id", type=int, default=None,
                        help="elementId der Lehrkraft (Default: personId des Kontos)")
    parser.add_argument("--weeks", nargs="*", default=None,
                        help="Zusätzliche Wochen als YYYY-MM-DD (Default: Rückblick-Serie)")
    parser.add_argument("--no-surface", action="store_true",
                        help="Frage D (Datenoberfläche) auslassen")
    parser.add_argument("--schoolyear", default=None,
                        help="Schuljahr für die Ferienabfrage (Name oder id, z. B. "
                             "'2026/2027' oder '9'). Ohne Angabe werden die drei "
                             "jüngsten der Reihe nach probiert.")
    parser.add_argument("--password-stdin", action="store_true",
                        help="Passwort von der Standardeingabe lesen (z. B. aus einem "
                             "Passwortmanager) statt es abzufragen")
    args = parser.parse_args()

    # WEBUNTIS_SCHOOL ist bewusst optional — bei eigener Subdomain gibt es keins.
    missing = [v for v in ("WEBUNTIS_BASE", "WEBUNTIS_USER") if not os.environ.get(v)]
    if missing:
        sys.exit(f"Fehlende Umgebungsvariablen: {', '.join(missing)}\n"
                 f"Siehe Kopf dieser Datei. Zugangsdaten NICHT in die Datei schreiben.")

    password = _read_password(args.password_stdin)
    if not password:
        sys.exit("Kein Passwort angegeben.")

    api = WebUntis(os.environ["WEBUNTIS_BASE"], os.environ.get("WEBUNTIS_SCHOOL", ""))
    print(f"Server: {api.base}   Schulkürzel: {api.school or '— (eigene Subdomain)'}")

    # ── A: Anmeldung ────────────────────────────────────────────────────────────────
    _section("A — Kommt das Servicekonto neben dem SSO an eine Anmeldung?")
    ok, message = api.login(os.environ["WEBUNTIS_USER"], password)
    print(f"{_mark(ok)} {message}")
    if not ok:
        print("\n→ Ohne Anmeldung ist Weg 2 nicht nutzbar. Häufige Ursache: Das Konto hängt am "
              "SSO und hat kein eigenes Passwort. Beim Untis-Betreuer ein Konto mit lokaler "
              "Anmeldung erfragen — sonst bleibt nur Weg 1 (persönliches ICS-Abo).")
        api.close()
        sys.exit(1)
    if api.person_type != ELEMENT_TEACHER:
        print(f"       Hinweis: personType={api.person_type} (2 = Lehrkraft). Ein Konto ohne "
              f"Lehrkraft-Rolle sieht möglicherweise andere Pläne als erwartet.")

    # ── A2: Elemente ermitteln ──────────────────────────────────────────────────────
    _section("A2 — Welche Elemente kennt das Konto? (liefert die IDs für B–D)")
    if api.person_id in (None, -1):
        print("       personId=-1 → das Konto ist an KEINE Person gebunden. Für ein")
        print("       Servicekonto ist das normal; die Element-IDs müssen daher aus dem")
        print("       pageconfig-Endpunkt kommen statt aus dem eigenen Profil.\n")

    discovered: dict[int, list[dict]] = {}
    for label, etype in (("Lehrkräfte", ELEMENT_TEACHER), ("Klassen", ELEMENT_CLASS),
                         ("Schüler:innen", ELEMENT_STUDENT)):
        status, elements = api.pageconfig(etype)
        discovered[etype] = elements
        detail = f"{len(elements)} Einträge" if elements else f"HTTP {status}, keine Liste"
        print(f"{_mark(bool(elements))} {label:14} (type={etype})  {detail}")
        if elements:
            names = ", ".join(
                str(e.get("displayname") or e.get("name") or e.get("id"))[:18]
                for e in elements[:4]
            )
            print(f"       {'':14}   z. B. {names}{' …' if len(elements) > 4 else ''}")

    teachers = discovered.get(ELEMENT_TEACHER) or []
    element_id = args.element_id
    if not element_id and teachers:
        element_id = teachers[0].get("id")
    if not element_id:
        print("\n→ Keine Lehrkraft-ID ermittelbar — weder über pageconfig noch über")
        print("  --element-id. Ohne sie sind B–D nicht messbar. Beim Untis-Betreuer klären,")
        print("  ob das Konto Leserechte auf Stundenpläne hat.")
        api.close()
        sys.exit(1)

    # ── B: Felder ───────────────────────────────────────────────────────────────────
    _section(f"B — Liefert die Wochenschnittstelle die nötigen Felder? (elementId={element_id})")
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    # In den Ferien ist die laufende Woche leer. Eine leere Woche sagt NICHTS über die
    # Felder aus — dann bis zu ein Jahr zurückgehen, bis eine Woche Stunden enthält.
    # (Vorher meldete dieser Abschnitt fälschlich „NEIN", was Teil C dann widerlegte.)
    # `rescheduleInfo` gibt es nur in Wochen mit SHIFT, `orgId` nur mit SUBSTITUTION. Eine
    # beliebige nicht-leere Woche beweist deren Fehlen daher NICHT. Also gezielt eine Woche
    # suchen, die beides enthält — und explizit angegebene Wochen (--weeks) zuerst prüfen.
    if args.weeks:
        candidates = [date.fromisoformat(w) for w in args.weeks]
    else:
        candidates = [monday - timedelta(weeks=n) for n in range(0, 53)]

    reference = None
    for day in candidates:
        candidate = probe_week(api, ELEMENT_TEACHER, element_id, day)
        if not (candidate["ok"] and candidate["count"] > 0):
            continue
        candidate["week"] = day
        if reference is None:
            reference = candidate          # erste nicht-leere Woche als Rückfall
        if candidate["has_reschedule"] and candidate["has_orgid"]:
            reference = candidate          # aussagekräftigste Woche gefunden
            break

    if reference is None:
        print(f"{_mark(None)} Keine Woche mit Stunden gefunden —")
        print("       die Felder sind damit NICHT geprüft. Das ist kein Nein.")
    else:
        note = " (laufende Woche)" if reference["week"] == monday else f" (Woche ab {reference['week']})"
        print(f"       {reference['count']} Stunden{note}")
        for field, why in REQUIRED_FIELDS.items():
            print(f"{_mark(reference['fields'].get(field))} {field:12} — {why}")
        print(f"{_mark(reference['has_reschedule'])} rescheduleInfo — Verlegungen mit Zielzeitpunkt")
        print(f"{_mark(reference['has_orgid'])} elements[].orgId — wer wen vertritt")
        states = reference.get("states") or {}
        if not reference["has_reschedule"]:
            if states.get("SHIFT"):
                print(f"       ⚠️ Diese Woche enthält {states['SHIFT']}× SHIFT, aber KEIN")
                print("          rescheduleInfo — Verlegungen tragen also kein Zielziel.")
                print("          Der Verschiebe-Dialog könnte dann nur melden, nicht vorschlagen.")
            else:
                print("       (Diese Woche enthält keine Verlegung — damit ist rescheduleInfo")
                print("        UNGEPRÜFT, nicht abwesend. Woche mit SHIFT nachreichen.)")
        if not reference["has_orgid"] and not states.get("SUBSTITUTION"):
            print("       (Keine Vertretung in dieser Woche — orgId ebenfalls ungeprüft.)")

    # ── C: Reichweite in die Vergangenheit ──────────────────────────────────────────
    _section("C — Wie weit reicht die Schnittstelle zurück? (löst das Ferien-Datenproblem)")
    if args.weeks:
        days = [date.fromisoformat(w) for w in args.weeks]
    else:
        days = [today - timedelta(weeks=w) for w in (4, 8, 12, 16, 20, 26)]
    totals: Counter = Counter()
    for day in days:
        result = probe_week(api, ELEMENT_TEACHER, element_id, day)
        if not result["ok"]:
            print(f"{_mark(False)} {day}  HTTP {result['status']}: {result['detail'][:60]}")
            continue
        totals.update(result["states"])
        summary = ", ".join(f"{k}={v}" for k, v in sorted(result["states"].items())) or "—"
        print(f"{_mark(result['count'] > 0)} {day}  {result['count']:3} Stunden   {summary}")
    if totals:
        print(f"\n       Summe cellState über alle Wochen: "
              f"{', '.join(f'{k}={v}' for k, v in totals.most_common())}")
        if totals.get("CANCEL") or totals.get("SUBSTITUTION"):
            print("       → Entfall/Vertretung sind rückwirkend lesbar. Damit taugt die "
                  "Schnittstelle als Datenquelle für die Musterentwicklung, obwohl Ferien sind.")
    else:
        print("\n       → Keine historischen Daten erreichbar. Dann bleibt für die "
              "Musterentwicklung nur der Schuljahresbeginn abzuwarten.")

    # ── D: Datenoberfläche ──────────────────────────────────────────────────────────
    if not args.no_surface:
        _section("D — Datenoberfläche: Was sieht das Konto AUSSER dem eigenen Plan?")
        print("       (Ein weiter Zugriff ist datenschutzrechtlich teuer — hier kann der Test")
        print("        bewusst gegen Weg 2 ausgehen. Siehe ADR-006 / DSFA.)\n")
        print(f"{_mark(bool(discovered.get(ELEMENT_TEACHER)))} Lehrkräfte aufzählbar   "
              f"({len(discovered.get(ELEMENT_TEACHER) or [])})")
        print(f"{_mark(bool(discovered.get(ELEMENT_CLASS)))} Klassen aufzählbar      "
              f"({len(discovered.get(ELEMENT_CLASS) or [])})")
        print(f"{_mark(bool(discovered.get(ELEMENT_STUDENT)))} Schüler:innen aufzählbar"
              f" ({len(discovered.get(ELEMENT_STUDENT) or [])})   ← der kritische Punkt")

        # Zusätzlich: Plan einer ANDEREN Lehrkraft (echte ID, nicht geraten).
        monday = today - timedelta(days=today.weekday() + 28)
        others = [t for t in (discovered.get(ELEMENT_TEACHER) or [])
                  if t.get("id") != element_id]
        if others:
            other_id = others[0]["id"]
            result = probe_week(api, ELEMENT_TEACHER, other_id, monday)
            visible = result["ok"] and result.get("count", 0) > 0
            detail = (f"{result['count']} Stunden" if result["ok"]
                      else f"HTTP {result['status']}")
            print(f"{_mark(visible)} Plan einer fremden Lehrkraft (elementId={other_id})  {detail}")
        else:
            print(f"{_mark(None)} Plan einer fremden Lehrkraft — keine zweite ID bekannt")

        print("\n       Ein NEIN ist hier das datenschutzfreundlichere Ergebnis.")
        if discovered.get(ELEMENT_STUDENT):
            print("       ⚠️ Das Konto kann Schüler:innen aufzählen. Das ist die teure")
            print("          Variante — vor einem Einsatz mit DSB klären, ob sich der")
            print("          Zugriff einschränken lässt, sonst spricht viel für Weg 1.")

    # ── E: Ferienkalender ───────────────────────────────────────────────────────────
    _section("E — Liefert WebUntis den Ferienkalender samt beweglicher Ferientage?")
    print("       (Fällt das JA aus, entfällt für Datenstrom A die zweite Quelle: Der Admin")
    print("        müsste dann keinen ICS-Kalender mehr eintragen. Siehe UP-8 Schritt 4.)\n")
    # Erst den Kontext, dann den Abruf: `getHolidays` bezieht sich auf das laufende
    # Schuljahr. Ohne diese Zeilen liest sich ein Fehlschlag wie eine Absage, obwohl er
    # nur bedeutet, dass gerade kein Schuljahr aktiv ist.
    ok_current, current = api.current_schoolyear()
    if ok_current and isinstance(current, dict) and current.get("id"):
        print(f"{_mark(True)} Laufendes Schuljahr: {current.get('name', '?')} "
              f"({_untis_date(current.get('startDate'))} – "
              f"{_untis_date(current.get('endDate'))})")
    else:
        detail = current if not ok_current else "keines aktiv"
        print(f"{_mark(False)} Kein laufendes Schuljahr: {str(detail)[:90]}")
    ok_years, years = api.schoolyears()
    year_list = [y for y in years if isinstance(y, dict)] if ok_years and isinstance(years, list) else []
    # Jüngstes zuerst: Das laufende bzw. kommende Schuljahr ist der wahrscheinlichste Treffer.
    year_list.sort(key=lambda y: y.get("startDate") or 0, reverse=True)
    if year_list:
        names = ", ".join(f"{y.get('name', '?')}#{y.get('id')}" for y in year_list)
        print(f"{_mark(True)} Angelegte Schuljahre: {names[:130]}")
    else:
        print(f"{_mark(False)} Keine Schuljahresliste: {str(years)[:90]}")
    print()

    # Mehrere Aufrufformen durchprobieren, statt eine zu raten. `getHolidays` ist ohne
    # Parameter dokumentiert — aber `getClassregEvents` nimmt nachweislich einen
    # Datumsbereich (siehe webuntis-Tools/probes/08), also ist der Versuch billig.
    candidates = list(year_list)
    if args.schoolyear:
        wanted = args.schoolyear.lower()
        picked = [y for y in candidates
                  if wanted in str(y.get("name", "")).lower() or wanted == str(y.get("id"))]
        if picked:
            candidates = picked
        else:
            print(f"       ⚠️ Kein Schuljahr passt auf --schoolyear {args.schoolyear!r} — "
                  f"es werden alle geprüft.\n")

    attempts: list[tuple[str, dict | None]] = [("ohne Parameter (dokumentierte Form)", None)]
    for year in candidates[:3]:
        name, yid = year.get("name", "?"), year.get("id")
        if yid:
            attempts.append((f"schoolyearId={yid} ({name})", {"schoolyearId": yid}))
        if year.get("startDate") and year.get("endDate"):
            attempts.append((
                f"Datumsbereich {name}",
                {"startDate": year["startDate"], "endDate": year["endDate"]},
            ))

    holidays: object = None
    seen: set[str] = set()
    for label, params in attempts:
        ok, result = api.rpc("getHolidays", params)
        if ok and isinstance(result, list) and result:
            print(f"{_mark(True)} {label}: {len(result)} Einträge")
            holidays = result
            break
        detail = "leere Antwort" if ok else str(result)
        # Dieselbe Serverantwort fünfmal auszuschreiben verdeckt, worauf es ankommt:
        # WELCHE Aufrufform scheitert. Also einmal vollständig, danach nur der Verweis.
        if detail in seen:
            detail = "— derselbe Fehler"
        else:
            seen.add(detail)
        print(f"{_mark(False)} {label}: {detail[:150]}")

    if holidays is None:
        # Letzter Versuch ohne Raten: Die Wochenschnittstelle funktioniert nachweislich
        # mit beliebigen Daten — auch ohne aktives Schuljahr. Trägt ihre Antwort
        # Ferieninformation, hätten wir einen datumsgesteuerten Weg.
        print("\n       Sondierung: Trägt die Wochenschnittstelle Ferieninformation?")
        _, payload = api.weekly(ELEMENT_TEACHER, element_id,
                                date.today() - timedelta(weeks=30))
        hits = find_keys(payload, ("holiday", "ferien", "vacation", "freeday"))
        if hits:
            print(f"{_mark(True)} Fündig — {len(hits)} Treffer:")
            for where, preview in hits[:6]:
                print(f"       {where} = {preview}")
            print("       → Datumsgesteuerter Weg möglich; Struktur vor Schritt 4 ansehen.")
        else:
            print(f"{_mark(False)} Keine Ferienfelder in der Wochenantwort.")

        hint = interpret_holiday_error(str(result))
        print()
        if hint:
            print(f"       {hint}")
        else:
            print("       → Kein Beinbruch. Dann bleibt es beim eingetragenen ICS-Kalender")
            print("         bzw. bei der Pflege direkt in config/school_year.yaml.")
    else:
        entries, skipped = parse_holidays(holidays)
        print(f"{_mark(bool(entries))} {len(entries)} Einträge gelesen"
              f"{f', {skipped} ohne brauchbares Datum übersprungen' if skipped else ''}\n")

        # Gelingt der Aufruf, ist das voraussichtlich ein knappes Zeitfenster (ein aktives
        # Schuljahr muss dafür bestehen). Also gleich die vollständige Struktur festhalten,
        # statt für Schritt 4 ein zweites Mal anklopfen zu müssen.
        keys: set[str] = set()
        for item in holidays:
            if isinstance(item, dict):
                keys.update(item.keys())
        print(f"       Verfügbare Felder: {', '.join(sorted(keys))}")
        print("       Rohform des ersten Eintrags:")
        print(f"         {json.dumps(holidays[0], ensure_ascii=False)[:200]}\n")

        merged = merge_adjacent(entries)
        for start, end, name in merged:
            days = (end - start).days + 1
            kind = "Einzeltag" if days == 1 else f"{days} Tage"
            print(f"       {start} – {end}  {kind:9}  {name[:40]}")

        if len(merged) < len(entries):
            print(f"\n       {len(entries) - len(merged)} gleichnamige Einträge zusammen-")
            print("       geführt — WebUntis zerlegt Abschnitte mitunter. Ohne das sähe ein")
            print("       Bruchteil wie ein einzelner unterrichtsfreier Tag aus.")

        # Bewusst NICHT die Einzeltage gegen „acht" zählen: Die beweglichen Ferientage sind
        # nicht einzeln erkennbar. In BW gehen die meisten in Blöcken auf (die
        # Faschingsferien bestehen komplett aus ihnen), und umgekehrt sind die meisten
        # Einzeltage gesetzliche Feiertage. Für die Plattform ist die Einteilung ohnehin
        # gleichgültig — `is_schoolday()` fragt nur: Unterricht ja oder nein.
        free_days = sum(
            1
            for start, end, _ in merged
            for n in range((end - start).days + 1)
            if (start + timedelta(days=n)).weekday() < 5
        )
        print(f"\n       {len(merged)} Abschnitte, zusammen {free_days} unterrichtsfreie")
        print("       Wochentage. Das ist die Zahl, auf die es ankommt — die Einteilung in")
        print("       Ferien / Feiertag / beweglicher Tag ist für die Plattform kosmetisch.")
        print("\n       Zum Abgleich mit config/school_year.yaml: Fehlt dort einer dieser")
        print("       Abschnitte, wurden bisher Unterrichtstage gezählt, die keine sind.")

        print("\n       Hinweis: Die Liste ist operativ, nicht enzyklopädisch — gesetzliche")
        print("       Feiertage tauchen nur auf, wenn sie nicht ohnehin in einem Block oder")
        print("       auf ein Wochenende fallen. Eine kurze Feiertagsliste ist also normal.")

    # ── F: Sitzung ──────────────────────────────────────────────────────────────────
    _section("F — Sitzungsverhalten")
    again = probe_week(api, ELEMENT_TEACHER, element_id, today - timedelta(weeks=4))
    print(f"{_mark(again['ok'])} Zweiter Abruf mit derselben Sitzung erfolgreich")
    print("       (Sitzungsdauer über Stunden/Tage lässt sich hier nicht messen — vor einem "
          "Cron-Betrieb einmal beobachten, ob die Sitzung überlebt oder je Lauf neu angemeldet "
          "werden muss.)")

    api.close()
    print('\nAbgemeldet. Ergebnisse in Todo.md → "Technisches WebUntis-Servicekonto" eintragen.')


if __name__ == "__main__":
    main()
