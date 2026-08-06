"""UP-8 Schritt 4 — Ferienkalender-Import.

Gearbeitet wird gegen die **echte, anonymisierte** Ferienantwort vom 06.08.2026. Die
lieferte den Fall, der die Zusammenführung nötig macht: Weihnachtsferien als Block **plus**
Einzeltag mit demselben Namen.
"""
import json
from datetime import date
from pathlib import Path

import pytest
import yaml as pyyaml

from app.calendar.base import Holiday
from app.calendar.holidays import (
    build_proposal,
    bw_public_holidays,
    config_free_days,
    easter,
    merge_adjacent,
    to_yaml_block,
)
from app.planning.calendar import SchoolYearConfig, is_schoolday

FIXTURES = Path(__file__).parent / "fixtures"


def _untis_date(value) -> date:
    text = str(value)
    return date(int(text[:4]), int(text[4:6]), int(text[6:]))


def _fixture_holidays() -> list[Holiday]:
    roh = json.loads((FIXTURES / "webuntis_holidays.json").read_text(encoding="utf-8"))
    return [
        Holiday(
            start=_untis_date(entry["startDate"]),
            end=_untis_date(entry["endDate"] or entry["startDate"]),
            name=str(entry.get("longName") or entry.get("name")),
        )
        for entry in roh
        if entry.get("startDate")
    ]


HOLIDAYS = _fixture_holidays()

CONFIG = SchoolYearConfig(
    schuljahr="2025/26",
    beginn=date(2025, 9, 15),
    ende=date(2026, 7, 29),
    halbjahreswechsel=date(2026, 2, 2),
    ferien=[
        {"name": "Herbstferien", "von": date(2025, 10, 27), "bis": date(2025, 10, 31)},
        {"name": "Weihnachtsferien", "von": date(2025, 12, 22), "bis": date(2026, 1, 6)},
        {"name": "Osterferien", "von": date(2026, 3, 30), "bis": date(2026, 4, 10)},
        {"name": "Pfingstferien", "von": date(2026, 5, 25), "bis": date(2026, 6, 5)},
    ],
    # Vollständig wie die echte `config/school_year.yaml` — eine verkürzte Liste würde
    # Feiertage als „neu" ausweisen, die längst eingetragen sind, und damit den Gewinn
    # dieses Schritts überzeichnen.
    feiertage=[
        {"name": "Tag der Deutschen Einheit", "datum": date(2025, 10, 3)},
        {"name": "1. Weihnachtsfeiertag", "datum": date(2025, 12, 25)},
        {"name": "2. Weihnachtsfeiertag", "datum": date(2025, 12, 26)},
        {"name": "Neujahr", "datum": date(2026, 1, 1)},
        {"name": "Heilige Drei Könige", "datum": date(2026, 1, 6)},
        {"name": "Karfreitag", "datum": date(2026, 4, 3)},
        {"name": "Ostermontag", "datum": date(2026, 4, 5)},
        {"name": "Tag der Arbeit", "datum": date(2026, 5, 1)},
        {"name": "Christi Himmelfahrt", "datum": date(2026, 5, 14)},
        {"name": "Pfingstsonntag", "datum": date(2026, 5, 24)},
        {"name": "Pfingstmontag", "datum": date(2026, 5, 25)},
        {"name": "Fronleichnam", "datum": date(2026, 6, 4)},
    ],
    unterrichtsfreie_tage=[
        {"name": "Reisewoche", "datum": date(2026, 7, 20)},
        {"name": "Reisewoche", "datum": date(2026, 7, 21)},
        {"name": "Reisewoche", "datum": date(2026, 7, 22)},
        {"name": "Reisewoche", "datum": date(2026, 7, 23)},
        {"name": "Reisewoche", "datum": date(2026, 7, 24)},
        {"name": "letzter Schultag", "datum": date(2026, 7, 29)},
    ],
)


# ── Osterrechnung ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "jahr,ostern",
    [
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
        (2027, date(2027, 3, 28)),
        (2030, date(2030, 4, 21)),
    ],
)
def test_osterformel(jahr, ostern):
    assert easter(jahr) == ostern


def test_bewegliche_feiertage_stimmen_mit_der_quelle_ueberein():
    """Gegenprobe an echten Daten: WebUntis führt Christi Himmelfahrt am 14.05.2026."""
    feiertage = bw_public_holidays(2026)
    assert feiertage[date(2026, 5, 14)] == "Christi Himmelfahrt"
    assert feiertage[date(2026, 1, 6)] == "Heilige Drei Könige"
    assert feiertage[date(2026, 6, 4)] == "Fronleichnam"


# ── Zusammenführung ──────────────────────────────────────────────────────────


def test_gleichnamiges_bruchstueck_wird_zusammengefuehrt():
    """Der Fall aus der Aufzeichnung: Block 22.12.–04.01. plus Einzeltag 05.01."""
    merged = merge_adjacent(HOLIDAYS)
    assert len(merged) == len(HOLIDAYS) - 1
    weihnachten = [h for h in merged if h.start == date(2025, 12, 22)]
    assert weihnachten[0].end == date(2026, 1, 5)


def test_verschiedene_namen_bleiben_getrennt():
    """Christi Himmelfahrt und der Brückentag danach sind zwei Sachverhalte."""
    merged = merge_adjacent([
        Holiday(start=date(2026, 5, 14), end=date(2026, 5, 14), name="Christi Himmelfahrt"),
        Holiday(start=date(2026, 5, 15), end=date(2026, 5, 15), name="beweglicher Ferientag"),
    ])
    assert len(merged) == 2


def test_wochenende_dazwischen_verbindet_gleichnamige():
    merged = merge_adjacent([
        Holiday(start=date(2026, 2, 16), end=date(2026, 2, 20), name="Fasching"),
        Holiday(start=date(2026, 2, 23), end=date(2026, 2, 24), name="Fasching"),
    ])
    assert len(merged) == 1
    assert merged[0].end == date(2026, 2, 24)


def test_werktag_dazwischen_verbindet_nicht():
    """Eine echte Lücke bleibt eine Lücke — auch bei gleichem Namen."""
    merged = merge_adjacent([
        Holiday(start=date(2026, 2, 16), end=date(2026, 2, 17), name="Fasching"),
        Holiday(start=date(2026, 2, 19), end=date(2026, 2, 20), name="Fasching"),
    ])
    assert len(merged) == 2


# ── Der Vorschlag ────────────────────────────────────────────────────────────


def test_einteilung_der_abschnitte():
    p = build_proposal(HOLIDAYS, CONFIG)
    assert len(p.ferien) == 5              # inkl. der zusammengeführten Weihnachtsferien
    assert len(p.feiertage) == 4           # die 4, die nicht in Blöcken liegen
    assert len(p.unterrichtsfreie_tage) == 1   # der beweglicher Ferientag
    assert p.warnungen == []


def test_neue_tage_werden_benannt():
    """Der eigentliche Gewinn: was die Handpflege übersehen hat."""
    p = build_proposal(HOLIDAYS, CONFIG)
    assert date(2026, 2, 16) in p.neu      # Faschingsferien
    assert date(2026, 5, 15) in p.neu      # beweglicher Ferientag
    assert len(p.neu) == 6


def test_schulinterne_tage_werden_nicht_verworfen():
    """Der wichtigste Test dieses Schritts.

    Reisewoche und letzter Schultag stehen **nicht** im Ferienkalender — sie sind von der
    Schule gelegt und kommen über Datenstrom C (Plan §2.1). Ein Vorschlag, der die Config
    ersetzt statt sie zu ergänzen, löschte sie stillschweigend.
    """
    p = build_proposal(HOLIDAYS, CONFIG)
    assert date(2026, 7, 20) in p.nur_in_config
    assert date(2026, 7, 29) in p.nur_in_config


def test_keine_zaehlung_gegen_acht():
    """Die beweglichen Ferientage sind nicht einzeln erkennbar — eine Prüfung „sind es
    acht?" löste verlässlich falschen Alarm aus. Es darf keine solche Warnung geben."""
    p = build_proposal(HOLIDAYS, CONFIG)
    assert not any("acht" in w.lower() for w in p.warnungen)


def test_eintrag_ausserhalb_des_schuljahres_wird_verworfen():
    """`SchoolYearConfig` weist solche Perioden ab — ungeprüft übernommen wäre die Datei
    nicht mehr ladbar."""
    p = build_proposal(
        [*HOLIDAYS, Holiday(start=date(2026, 8, 3), end=date(2026, 8, 7), name="Sommer")],
        CONFIG,
    )
    assert any("außerhalb" in w for w in p.warnungen)
    assert not any(e["name"] == "Sommer" for e in p.ferien)


def test_ueberhaengender_eintrag_wird_gekuerzt():
    p = build_proposal(
        [Holiday(start=date(2026, 7, 27), end=date(2026, 8, 7), name="Sommerferien")],
        CONFIG,
    )
    assert any("gekürzt" in w for w in p.warnungen)
    assert p.ferien[0]["bis"] == CONFIG.ende


# ── Der YAML-Block ───────────────────────────────────────────────────────────


def test_yaml_ist_gueltig_und_laedt_als_config():
    """Ein Vorschlag, der die Datei unladbar macht, ist wertlos."""
    block = to_yaml_block(build_proposal(HOLIDAYS, CONFIG), CONFIG)
    geladen = SchoolYearConfig.model_validate({
        "schuljahr": CONFIG.schuljahr,
        "beginn": CONFIG.beginn,
        "ende": CONFIG.ende,
        "halbjahreswechsel": CONFIG.halbjahreswechsel,
        **pyyaml.safe_load(block),
    })
    assert geladen.ferien


def test_uebernahme_gewinnt_tage_und_verliert_keine():
    """Die Abnahme des Schritts, in Zahlen."""
    block = to_yaml_block(build_proposal(HOLIDAYS, CONFIG), CONFIG)
    neu = SchoolYearConfig.model_validate({
        "schuljahr": CONFIG.schuljahr,
        "beginn": CONFIG.beginn,
        "ende": CONFIG.ende,
        "halbjahreswechsel": CONFIG.halbjahreswechsel,
        **pyyaml.safe_load(block),
    })
    vorher, nachher = config_free_days(CONFIG), config_free_days(neu)
    assert vorher <= nachher                       # nichts verloren
    assert len(nachher - vorher) == 6              # Fasching + beweglicher Ferientag


def test_uebernahme_wirkt_auf_is_schoolday():
    """Das eigentliche Ziel: Der 16.02. ist danach kein Unterrichtstag mehr."""
    assert is_schoolday(date(2026, 2, 16), CONFIG)         # vorher fälschlich Unterricht
    block = to_yaml_block(build_proposal(HOLIDAYS, CONFIG), CONFIG)
    neu = SchoolYearConfig.model_validate({
        "schuljahr": CONFIG.schuljahr,
        "beginn": CONFIG.beginn,
        "ende": CONFIG.ende,
        "halbjahreswechsel": CONFIG.halbjahreswechsel,
        **pyyaml.safe_load(block),
    })
    assert not is_schoolday(date(2026, 2, 16), neu)
    assert not is_schoolday(date(2026, 7, 20), neu)        # Reisewoche überlebt


def test_yaml_unterscheidet_redundant_von_schulintern():
    """Der Admin muss sehen, was er löschen darf.

    Ein Feiertag innerhalb eines Ferienblocks ist redundant (WebUntis führt seine Liste
    operativ). Ein Tag, den nur die Config kennt, ist schulintern gelegt und muss bleiben.
    """
    block = to_yaml_block(build_proposal(HOLIDAYS, CONFIG), CONFIG)
    reisewoche = next(z for z in block.splitlines() if "Reisewoche" in z)
    assert "nicht löschen" in reisewoche

# ── Schreiben der Datei ──────────────────────────────────────────────────────


def test_render_uebernimmt_halbjahreswechsel_und_schuljahr():
    """Beide Felder kennt die Quelle nicht — sie dürfen nur übernommen, nie erzeugt werden.

    `halbjahreswechsel` ist eine Schulentscheidung (`getSchoolyears` liefert nur Name und
    Grenzen). Die Schreibweise von `schuljahr` wird von `parse_schuljahr_start` für die
    Bildungsplan-Edition gelesen — „2025/2026" statt „2025/26" wäre eine stille Änderung
    an einer ganz anderen Stelle.
    """
    from app.calendar.holidays import render_school_year

    text = render_school_year(build_proposal(HOLIDAYS, CONFIG), CONFIG)
    geladen = SchoolYearConfig.model_validate(pyyaml.safe_load(text))
    assert geladen.schuljahr == CONFIG.schuljahr
    assert geladen.halbjahreswechsel == CONFIG.halbjahreswechsel


def test_render_uebernimmt_grenzen_der_quelle():
    from app.calendar.holidays import render_school_year

    neue = (date(2025, 9, 8), date(2026, 7, 31))
    text = render_school_year(build_proposal(HOLIDAYS, CONFIG), CONFIG, bounds=neue)
    geladen = SchoolYearConfig.model_validate(pyyaml.safe_load(text))
    assert (geladen.beginn, geladen.ende) == neue


def test_render_ergibt_ladbare_datei():
    """Der Rundlauf: schreiben → laden → dieselben freien Tage plus die neuen."""
    from app.calendar.holidays import render_school_year

    text = render_school_year(build_proposal(HOLIDAYS, CONFIG), CONFIG)
    geladen = SchoolYearConfig.model_validate(pyyaml.safe_load(text))
    assert config_free_days(CONFIG) <= config_free_days(geladen)


def test_grenzen_die_den_halbjahreswechsel_brechen_werden_abgelehnt():
    """`SchoolYearConfig` verlangt beginn < halbjahreswechsel < ende.

    Solche Grenzen zu schreiben machte die Datei unladbar — und zwar erst beim nächsten
    Start, ohne erkennbaren Zusammenhang.
    """
    from app.api.admin.holidays import _bounds_pruefen

    kaputt = (date(2026, 3, 1), date(2026, 7, 29))   # nach dem Halbjahreswechsel
    genutzt, hinweise = _bounds_pruefen(CONFIG, kaputt)
    assert genutzt is None
    assert any("Halbjahreswechsel" in h for h in hinweise)


def test_unveraenderte_grenzen_erzeugen_keinen_hinweis():
    from app.api.admin.holidays import _bounds_pruefen

    genutzt, hinweise = _bounds_pruefen(CONFIG, (CONFIG.beginn, CONFIG.ende))
    assert genutzt is None and hinweise == []


def test_write_sichert_die_bisherige_fassung(tmp_path):
    from app.calendar.holidays import write_school_year

    ziel = tmp_path / "school_year.yaml"
    ziel.write_text("alt: true\n", encoding="utf-8")
    sicherung = write_school_year(ziel, "neu: true\n")
    assert ziel.read_text(encoding="utf-8") == "neu: true\n"
    assert sicherung and sicherung.read_text(encoding="utf-8") == "alt: true\n"


def test_write_legt_neu_an_ohne_sicherung(tmp_path):
    from app.calendar.holidays import write_school_year

    ziel = tmp_path / "school_year.yaml"
    assert write_school_year(ziel, "neu: true\n") is None
    assert ziel.exists()


def test_write_laesst_keine_temporaerdatei_zurueck(tmp_path):
    """Geschrieben wird über eine Zwischendatei — die darf nicht liegenbleiben."""
    from app.calendar.holidays import write_school_year

    ziel = tmp_path / "school_year.yaml"
    write_school_year(ziel, "neu: true\n")
    assert [p.name for p in tmp_path.iterdir()] == ["school_year.yaml"]


def test_zwischenspeicher_muss_geleert_werden(tmp_path, monkeypatch):
    """Ohne `cache_clear()` arbeitet der laufende Prozess mit dem alten Stand weiter.

    `load_school_year` ist `lru_cache`d — die Datei wäre neu, die Anwendung wüsste nichts
    davon, und niemand käme auf die Idee, das mit dem Import in Verbindung zu bringen.
    """
    from app.planning import calendar as kalender

    datei = tmp_path / "school_year.yaml"
    basis = {
        "schuljahr": "2025/26", "beginn": date(2025, 9, 15), "ende": date(2026, 7, 29),
        "halbjahreswechsel": date(2026, 2, 2), "ferien": [], "feiertage": [],
        "unterrichtsfreie_tage": [],
    }
    datei.write_text(pyyaml.safe_dump(basis), encoding="utf-8")
    monkeypatch.setattr(kalender, "_DEFAULT_PATH", datei)
    kalender.load_school_year.cache_clear()
    assert kalender.load_school_year().ferien == []

    datei.write_text(
        pyyaml.safe_dump({**basis, "ferien": [
            {"name": "Neu", "von": date(2026, 2, 16), "bis": date(2026, 2, 20)}]}),
        encoding="utf-8",
    )
    assert kalender.load_school_year().ferien == []          # noch der alte Stand
    kalender.load_school_year.cache_clear()
    assert len(kalender.load_school_year().ferien) == 1      # jetzt der neue
    kalender.load_school_year.cache_clear()


# ── Welches Schuljahr importiert wird ────────────────────────────────────────


class _Jahr:
    def __init__(self, name, start, end):
        self.name, self.start, self.end = name, start, end

    def contains(self, day):
        return self.start <= day <= self.end


JAHRE = [
    _Jahr("2024/2025", date(2024, 9, 9), date(2025, 7, 30)),
    _Jahr("2025/2026", date(2025, 9, 15), date(2026, 7, 29)),
    _Jahr("2026/2027", date(2026, 9, 14), date(2027, 7, 28)),
]


def test_ohne_wahl_gilt_das_jahr_der_konfiguration():
    """Wer mitten im Jahr abruft, soll nicht versehentlich auf das kommende umgestellt
    werden — auch dann nicht, wenn die Quelle es schon kennt."""
    from app.api.admin.holidays import _waehle_jahr

    assert _waehle_jahr(JAHRE, CONFIG, None).name == "2025/2026"


def test_jahr_ist_waehlbar():
    """Sonst wäre der Jahreswechsel ein Zirkelschluss: Solange die Datei 2025/26 sagt,
    käme der Import nie ins neue Jahr."""
    from app.api.admin.holidays import _waehle_jahr

    gewaehlt = _waehle_jahr(JAHRE, CONFIG, "2026/2027")
    assert (gewaehlt.start, gewaehlt.end) == (date(2026, 9, 14), date(2027, 7, 28))


def test_unbekanntes_jahr_nennt_die_bekannten():
    from fastapi import HTTPException
    from app.api.admin.holidays import _waehle_jahr

    with pytest.raises(HTTPException) as exc:
        _waehle_jahr(JAHRE, CONFIG, "2030/2031")
    assert "2025/2026" in exc.value.detail


def test_jahreswechsel_verlangt_passenden_halbjahreswechsel():
    """Der Ablauf beim Wechsel: neues Jahr wählen → Warnung → Halbjahreswechsel setzen.

    Ohne diese Prüfung schriebe der Import Grenzen, in denen der alte Halbjahreswechsel
    nicht mehr liegt — die Datei wäre beim nächsten Start nicht mehr ladbar.
    """
    from app.api.admin.holidays import _bounds_pruefen, _waehle_jahr

    neu = _waehle_jahr(JAHRE, CONFIG, "2026/2027")
    genutzt, hinweise = _bounds_pruefen(CONFIG, (neu.start, neu.end))
    assert genutzt is None
    assert any("Halbjahreswechsel" in h for h in hinweise)
