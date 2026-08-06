"""Ferienkalender aus der Quelle in einen Vorschlag für `school_year.yaml` überführen
(UP-8, Schritt 4).

**Der Import schlägt vor, er entscheidet nicht** — und er **ergänzt, statt zu ersetzen.**
Das ist hier keine Höflichkeit, sondern notwendig: Der Abgleich vom 06.08.2026 hat gezeigt,
dass beide Seiten Tage kennen, die die andere nicht hat.

    nur in WebUntis          nur in der Config
    ─────────────────────    ───────────────────────
    Faschingsferien          Reisewoche
    beweglicher Ferientag    letzter Schultag

Links steht der **feststehende** Kalender, den die Handpflege übersehen hat. Rechts stehen
**von der Schule gelegte** Tage — die stehen nicht im Ferienkalender und kommen über
Datenstrom C herein (Plan §2.1). Ein Vorschlag, der die Config einfach überschreibt, würde
sie stillschweigend löschen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from app.calendar.base import Holiday
from app.planning.calendar import SchoolYearConfig


def easter(year: int) -> date:
    """Ostersonntag nach dem gregorianischen Kalender (Anonyme Gaußsche Osterformel).

    Berechnet statt konfiguriert: Fünf der BW-Feiertage hängen daran, und eine gepflegte
    Liste veraltet — eine berechnete nie.
    """
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f, g = (b + 8) // 25, (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    lam = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lam) // 451
    month = (h + lam - 7 * m + 114) // 31
    day = (h + lam - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def bw_public_holidays(year: int) -> dict[date, str]:
    """Gesetzliche Feiertage in Baden-Württemberg."""
    ostern = easter(year)
    return {
        date(year, 1, 1): "Neujahr",
        date(year, 1, 6): "Heilige Drei Könige",
        ostern - timedelta(days=2): "Karfreitag",
        ostern + timedelta(days=1): "Ostermontag",
        date(year, 5, 1): "Tag der Arbeit",
        ostern + timedelta(days=39): "Christi Himmelfahrt",
        ostern + timedelta(days=50): "Pfingstmontag",
        ostern + timedelta(days=60): "Fronleichnam",
        date(year, 10, 3): "Tag der Deutschen Einheit",
        date(year, 11, 1): "Allerheiligen",
        date(year, 12, 25): "1. Weihnachtsfeiertag",
        date(year, 12, 26): "2. Weihnachtsfeiertag",
    }


def merge_adjacent(holidays: list[Holiday]) -> list[Holiday]:
    """Gleichnamige, zusammenhängende Abschnitte zusammenführen.

    WebUntis zerlegt Abschnitte: Am GGD stehen die Weihnachtsferien als Block
    22.12.–04.01. **plus** ein Einzeltag 05.01. mit demselben Namen. Ohne Zusammenführung
    sähe dieses Bruchstück wie ein einzelner unterrichtsfreier Tag aus.

    Zusammengeführt wird nur bei gleichem Namen und wenn dazwischen höchstens ein Wochenende
    liegt. Verschiedene Namen bleiben getrennt — Christi Himmelfahrt und der Brückentag
    danach grenzen aneinander, sind aber zwei Sachverhalte.
    """
    merged: list[Holiday] = []
    for entry in sorted(holidays, key=lambda h: (h.start, h.end)):
        if merged:
            last = merged[-1]
            luecke = [
                last.end + timedelta(days=n)
                for n in range(1, (entry.start - last.end).days)
            ]
            if last.name.strip().lower() == entry.name.strip().lower() and all(
                tag.weekday() >= 5 for tag in luecke
            ):
                merged[-1] = Holiday(
                    start=last.start, end=max(last.end, entry.end), name=last.name
                )
                continue
        merged.append(entry)
    return merged


def school_days(start: date, end: date) -> set[date]:
    """Wochentage (Mo–Fr) in einem Zeitraum."""
    return {
        start + timedelta(days=n)
        for n in range((end - start).days + 1)
        if (start + timedelta(days=n)).weekday() < 5
    }


def config_free_days(cfg: SchoolYearConfig) -> set[date]:
    """Alle unterrichtsfreien Wochentage der bestehenden Konfiguration.

    Über alle drei Schlüssel hinweg, weil `is_schoolday()` sie gleich behandelt — die
    Einteilung ist Lesbarkeit, keine Funktion.
    """
    frei: set[date] = set()
    for periode in cfg.ferien:
        frei |= school_days(periode.von, periode.bis)
    for tag in (*cfg.feiertage, *cfg.unterrichtsfreie_tage):
        if tag.datum.weekday() < 5:
            frei.add(tag.datum)
    return frei


@dataclass
class Proposal:
    """Was der Import vorschlägt — getrennt nach Herkunft, damit nichts verlorengeht."""

    ferien: list[dict] = field(default_factory=list)
    feiertage: list[dict] = field(default_factory=list)
    unterrichtsfreie_tage: list[dict] = field(default_factory=list)
    # Tage, die die Quelle kennt und die Config nicht — der eigentliche Gewinn.
    neu: list[date] = field(default_factory=list)
    # Tage, die nur die Config kennt. **Nicht löschen**: mutmaßlich von der Schule gelegt
    # (Wandertag, Projektwoche), die stehen nicht im Ferienkalender.
    nur_in_config: list[date] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    freie_wochentage: int = 0


def build_proposal(holidays: list[Holiday], cfg: SchoolYearConfig) -> Proposal:
    """Aus den Abschnitten der Quelle einen Vorschlag bauen.

    Bewusst **ohne** Prüfung „sind es acht bewegliche Ferientage?": Sie sind nicht einzeln
    erkennbar — in BW gehen die meisten in Blöcken auf (die Faschingsferien bestehen
    vollständig aus ihnen), und die meisten Einzeltage sind gesetzliche Feiertage. Eine
    solche Zählung löste verlässlich falschen Alarm aus.
    """
    proposal = Proposal()
    passend: list[Holiday] = []

    for entry in merge_adjacent(holidays):
        if entry.end < cfg.beginn or entry.start > cfg.ende:
            # `SchoolYearConfig` weist Ferien außerhalb des Schuljahres per Validator ab —
            # ein ungeprüft übernommener Randeintrag machte die Datei unladbar.
            proposal.warnungen.append(
                f"'{entry.name}' ({entry.start}–{entry.end}) liegt außerhalb des "
                f"Schuljahres und wurde verworfen."
            )
            continue
        if entry.start < cfg.beginn or entry.end > cfg.ende:
            gekuerzt = Holiday(
                start=max(entry.start, cfg.beginn),
                end=min(entry.end, cfg.ende),
                name=entry.name,
            )
            proposal.warnungen.append(
                f"'{entry.name}' ragt über das Schuljahr hinaus und wurde auf "
                f"{gekuerzt.start}–{gekuerzt.end} gekürzt."
            )
            entry = gekuerzt
        passend.append(entry)

    feiertage = {
        **bw_public_holidays(cfg.beginn.year),
        **bw_public_holidays(cfg.ende.year),
    }

    for entry in passend:
        if not entry.is_single_day:
            proposal.ferien.append(
                {"name": entry.name, "von": entry.start, "bis": entry.end}
            )
        elif entry.start in feiertage:
            proposal.feiertage.append(
                {"name": feiertage[entry.start], "datum": entry.start}
            )
        else:
            # Die sichere Richtung: Was nicht als Feiertag belegt ist, gilt als
            # unterrichtsfrei — lieber ein Eintrag zu viel auf dem Prüftisch als ein
            # stillschweigend verworfener freier Tag.
            proposal.unterrichtsfreie_tage.append(
                {"name": entry.name, "datum": entry.start}
            )

    aus_quelle: set[date] = set()
    for entry in passend:
        aus_quelle |= school_days(entry.start, entry.end)
    aus_config = config_free_days(cfg)

    proposal.neu = sorted(aus_quelle - aus_config)
    proposal.nur_in_config = sorted(aus_config - aus_quelle)
    proposal.freie_wochentage = len(aus_quelle | aus_config)
    return proposal


def render_school_year(
    proposal: Proposal,
    cfg: SchoolYearConfig,
    bounds: tuple[date, date] | None = None,
) -> str:
    """Die **vollständige** `school_year.yaml` — bereit zum Schreiben.

    Zwei Felder werden aus der bestehenden Datei **übernommen, nie erzeugt**:

    * `halbjahreswechsel` — die WebUntis-Schnittstelle kennt ihn nicht (`getSchoolyears`
      liefert nur Name und Grenzen). Eine Schulentscheidung.
    * `schuljahr` — dessen Schreibweise wird anderswo gelesen (`parse_schuljahr_start` für
      die Bildungsplan-Edition). Eine Quelle, die „2025/2026" statt „2025/26" schreibt,
      hätte hier nichts zu suchen.

    `bounds` überschreibt Beginn und Ende, wenn die Quelle sie kennt.
    """
    beginn, ende = bounds or (cfg.beginn, cfg.ende)
    kopf = [
        "# Erzeugt vom Ferienkalender-Import (UP-8). Von Hand nachbearbeitbar.",
        "# `schuljahr` und `halbjahreswechsel` stammen aus der bisherigen Fassung —",
        "# die Stundenplanquelle kennt sie nicht.",
        f'schuljahr: "{cfg.schuljahr}"',
        f"beginn: {beginn}",
        f"ende: {ende}",
        f"halbjahreswechsel: {cfg.halbjahreswechsel}",
        "",
    ]
    return "\n".join(kopf) + to_yaml_block(proposal, cfg)


def write_school_year(
    path: Path, inhalt: str, backup_suffix: str = ".bak"
) -> Path | None:
    """Datei schreiben, vorherige Fassung daneben sichern. Gibt den Sicherungspfad zurück.

    Geschrieben wird über eine temporäre Datei und `replace` — ein Abbruch mitten im
    Schreiben hinterlässt sonst eine halbe Konfiguration, und die Plattform lädt sie beim
    nächsten Start nicht mehr.

    **Der Zwischenspeicher muss danach geleert werden** (`load_school_year.cache_clear()`),
    sonst arbeitet der laufende Prozess weiter mit dem alten Stand — die Datei wäre neu,
    die Anwendung wüsste nichts davon.
    """
    backup: Path | None = None
    if path.exists():
        backup = path.with_suffix(path.suffix + backup_suffix)
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(inhalt, encoding="utf-8")
    temp.replace(path)
    return backup


def to_yaml_block(proposal: Proposal, cfg: SchoolYearConfig) -> str:
    """Die drei Abschnitte als YAML — zum Übernehmen in `school_year.yaml`.

    **Ergänzt statt zu ersetzen:** Einträge, die nur die Config kennt, bleiben erhalten und
    werden als solche gekennzeichnet. Ein Block, der sie unterschlüge, wäre die
    bequemste Art, die Reisewoche zu verlieren.
    """
    aus_quelle = {tag["datum"] for tag in proposal.feiertage}
    aus_quelle |= {tag["datum"] for tag in proposal.unterrichtsfreie_tage}

    zeilen = ["ferien:"]
    for eintrag in proposal.ferien:
        zeilen.append(
            f'  - {{ name: "{eintrag["name"]}", von: {eintrag["von"]}, '
            f'bis: {eintrag["bis"]} }}'
        )
    for periode in cfg.ferien:
        if not any(
            eintrag["von"] <= periode.von <= eintrag["bis"] for eintrag in proposal.ferien
        ):
            zeilen.append(
                f'  - {{ name: "{periode.name}", von: {periode.von}, '
                f'bis: {periode.bis} }}   # bisher, nicht in der Quelle'
            )

    # Tage, die schon von einem vorgeschlagenen Ferienblock abgedeckt sind. Ein Feiertag
    # darin ist **redundant, nicht fehlend** — WebUntis führt seine Feiertagsliste
    # operativ und nennt nur, was nicht ohnehin in einem Block liegt (am GGD 4 statt 12).
    # Ohne diese Unterscheidung läse der Admin bei jedem Weihnachtsfeiertag „nicht in der
    # Quelle" und fragte sich, ob er ihn löschen soll.
    in_block: set[date] = set()
    for eintrag in proposal.ferien:
        in_block |= school_days(eintrag["von"], eintrag["bis"])

    for schluessel, neue, alte in (
        ("feiertage", proposal.feiertage, cfg.feiertage),
        ("unterrichtsfreie_tage", proposal.unterrichtsfreie_tage, cfg.unterrichtsfreie_tage),
    ):
        zeilen.append("")
        zeilen.append(f"{schluessel}:")
        for eintrag in neue:
            zeilen.append(
                f'  - {{ name: "{eintrag["name"]}", datum: {eintrag["datum"]} }}'
            )
        for tag in sorted(alte, key=lambda t: t.datum):
            if tag.datum in aus_quelle:
                continue
            name = tag.name or "unterrichtsfrei"
            if tag.datum in in_block or tag.datum.weekday() >= 5:
                hinweis = "# liegt in einem Ferienabschnitt bzw. am Wochenende"
            else:
                hinweis = "# NUR hier bekannt — vermutlich schulintern gelegt, nicht löschen"
            zeilen.append(f'  - {{ name: "{name}", datum: {tag.datum} }}   {hinweis}')
    return "\n".join(zeilen) + "\n"
