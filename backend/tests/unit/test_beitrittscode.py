"""AP4: Die reinen Regeln des Beitrittscodes — Alphabet, Normalisierung, Gültigkeit."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.groups.beitritt import (
    ALPHABET,
    BLOCKLAENGE,
    BLOECKE,
    GUELTIGKEIT_TAGE,
    code_erzeugen,
    normalisiere,
    pruefe_code,
)

JETZT = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)


def _code(**kwargs):
    vorgabe = dict(
        code="ABCD-EFGH",
        widerrufen_am=None,
        gueltig_bis=JETZT + timedelta(days=1),
    )
    vorgabe.update(kwargs)
    return SimpleNamespace(**vorgabe)


# ── Das Alphabet ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("zeichen", ["O", "0", "I", "1", "L"])
def test_verwechselbare_zeichen_fehlen(zeichen):
    """⚠️ **Der Code wird an die Tafel geschrieben oder diktiert.**

    `I` gegen `1` zu verwechseln ist nicht der Randfall, sondern der Normalfall. Jedes
    dieser Zeichen im Alphabet kostet in jeder zweiten Klasse eine Rückfrage.
    """
    assert zeichen not in ALPHABET


def test_code_hat_die_vereinbarte_form():
    code = code_erzeugen()
    bloecke = code.split("-")
    assert len(bloecke) == BLOECKE
    assert all(len(b) == BLOCKLAENGE for b in bloecke)
    assert all(c in ALPHABET for b in bloecke for c in b)


def test_zwei_codes_sind_verschieden():
    """Kein Beweis für Zufälligkeit, aber ein Wächter gegen eine feste Rückgabe."""
    assert len({code_erzeugen() for _ in range(50)}) > 45


# ── Eingabe-Toleranz ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "eingabe",
    ["ABCD-EFGH", "abcd-efgh", "ABCDEFGH", "abcd efgh", " ABCD-EFGH ", "AbCd EfGh"],
)
def test_schreibweisen_fuehren_zum_selben_code(eingabe):
    """Wer abtippt, macht Leerzeichen und Kleinbuchstaben — das ist kein Fehler."""
    assert normalisiere(eingabe) == "ABCD-EFGH"


def test_keine_ersetzung_aehnlicher_zeichen():
    """⚠️ Eine Tabelle `0`→`O` würde Codes gültig machen, die nie ausgegeben wurden.

    Die verwechselbaren Zeichen kommen im Alphabet gar nicht vor; sie zu *übersetzen*
    hieße, den Suchraum heimlich zu vergrößern.
    """
    assert normalisiere("0BCD-EFGH") != "OBCD-EFGH"


# ── Gültigkeit ───────────────────────────────────────────────────────────────


def test_frischer_code_gilt():
    assert pruefe_code(_code(), JETZT).gueltig


def test_abgelaufener_code_wird_benannt():
    """Abgelaufen darf klar gesagt werden — diesen Code hatte die Person in der Hand."""
    lage = pruefe_code(_code(gueltig_bis=JETZT - timedelta(minutes=1)), JETZT)
    assert not lage.gueltig
    assert lage.grund == "abgelaufen"


def test_widerrufener_code_sieht_aus_wie_ein_unbekannter():
    """⚠️ **Die Gegenprobe zum Abklopfen des Bestands.**

    Wer einen fremden Code probiert, soll nicht erfahren, ob es ihn gibt. Unterschiede
    die Antwort „widerrufen" von „unbekannt", ließe sich damit herausfinden, welche
    Codes einmal existierten.
    """
    widerrufen = pruefe_code(_code(widerrufen_am=JETZT), JETZT)
    unbekannt = pruefe_code(None, JETZT)
    assert widerrufen.grund == unbekannt.grund == "unbekannt"


def test_gueltigkeit_ist_kurz():
    """Drei Tage (Entscheidung Jan): im Unterricht ausgegeben, sofort eingelöst.

    Ein langlebiger Code ist praktisch dauerhaft — und machte die Rücknahme unbrauchbar,
    weil eine Code-Runde dann mehrere Anlässe umfasste.
    """
    assert GUELTIGKEIT_TAGE <= 7
