"""Was die Vorlage kennt und die eigene Konfiguration nicht (Paket 1 von 0.12, AP2).

Der Anlass steht in `app/core/vorlagenabgleich.py`: Instanzdateien unter `config/`
überleben jedes Update. Bei Navigationseinträgen war das ärgerlich (0.11, die
unsichtbare Startseite), bei einem Sicherheitsauslöser bedeutet es, dass eine Prüfung
schlicht nicht stattfindet — ohne dass irgendwo etwas davon steht.
"""

import logging
import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")

from app.core.vorlagenabgleich import beispielpfad, fehlende_namen, melde_fehlende


def _schreibe(pfad, namen, liste="triggers", schluessel="category"):
    zeilen = [f"{liste}:"] + [f"  - {schluessel}: {n}" for n in namen]
    pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8")


@pytest.fixture
def paar(tmp_path):
    """Instanzdatei + Vorlage daneben, wie unter `config/`."""
    eigen = tmp_path / "trigger.yaml"
    vorlage = tmp_path / "trigger.example.yaml"
    return eigen, vorlage


class TestBeispielpfad:
    @pytest.mark.parametrize("quelle,ziel", [
        ("config/crisis_triggers.yaml", "config/crisis_triggers.example.yaml"),
        ("config/home_experiment_triggers.yaml", "config/home_experiment_triggers.example.yaml"),
        ("/abs/ui_levels.yaml", "/abs/ui_levels.example.yaml"),
    ])
    def test_ersetzt_die_endung(self, quelle, ziel, tmp_path):
        from pathlib import Path
        assert str(beispielpfad(Path(quelle))) == ziel


class TestFehlendeNamen:
    def test_meldet_was_nur_in_der_vorlage_steht(self, paar):
        eigen, vorlage = paar
        _schreibe(eigen, ["suizidalitaet", "mobbing"])
        _schreibe(vorlage, ["suizidalitaet", "mobbing", "letalitaet"])
        assert fehlende_namen(eigen, liste="triggers", schluessel="category") == ["letalitaet"]

    def test_gleichstand_meldet_nichts(self, paar):
        eigen, vorlage = paar
        _schreibe(eigen, ["a", "b"])
        _schreibe(vorlage, ["a", "b"])
        assert fehlende_namen(eigen, liste="triggers", schluessel="category") == []

    def test_eigene_zusaetze_sind_kein_befund(self, paar):
        """Eine Schule darf eigene Kategorien führen — das ist der Sinn der Datei."""
        eigen, vorlage = paar
        _schreibe(eigen, ["a", "b", "eigenes_thema"])
        _schreibe(vorlage, ["a", "b"])
        assert fehlende_namen(eigen, liste="triggers", schluessel="category") == []

    def test_reihenfolge_der_vorlage_bleibt(self, paar):
        eigen, vorlage = paar
        _schreibe(eigen, ["b"])
        _schreibe(vorlage, ["a", "b", "c"])
        assert fehlende_namen(eigen, liste="triggers", schluessel="category") == ["a", "c"]

    def test_fehlende_vorlage_ist_kein_fehler(self, paar):
        """Die Vorlage ist Diagnosemittel, nicht Voraussetzung."""
        eigen, _ = paar
        _schreibe(eigen, ["a"])
        assert fehlende_namen(eigen, liste="triggers", schluessel="category") == []

    def test_defekte_vorlage_ist_kein_fehler(self, paar):
        eigen, vorlage = paar
        _schreibe(eigen, ["a"])
        vorlage.write_text("triggers: [unbalanced\n", encoding="utf-8")
        assert fehlende_namen(eigen, liste="triggers", schluessel="category") == []

    def test_andere_listennamen(self, paar, tmp_path):
        """Derselbe Wächter bedient die Gefahrenthemen — darum gibt es ihn einmal."""
        eigen = tmp_path / "themen.yaml"
        vorlage = tmp_path / "themen.example.yaml"
        _schreibe(eigen, ["Elektrolyse"], liste="themen", schluessel="thema")
        _schreibe(vorlage, ["Elektrolyse", "Giftigkeit und Dosis"],
                  liste="themen", schluessel="thema")
        assert fehlende_namen(eigen, liste="themen", schluessel="thema") == [
            "Giftigkeit und Dosis"
        ]


class TestMeldung:
    def test_nennt_name_datei_und_folge(self, paar, caplog):
        eigen, vorlage = paar
        _schreibe(eigen, ["a"])
        _schreibe(vorlage, ["a", "letalitaet"])
        with caplog.at_level(logging.WARNING):
            fehlend = melde_fehlende(
                eigen, liste="triggers", schluessel="category",
                bezeichnung="Die Krisenkategorie",
                folge="Ihre Krisenerkennung löst dafür nicht aus.",
                hinweis="Erst nach Abstimmung übernehmen.",
            )
        assert fehlend == ["letalitaet"]
        text = caplog.text
        assert "letalitaet" in text
        assert "trigger.example.yaml" in text and "trigger.yaml" in text
        # Die Folge ist der Inhalt der Meldung: „Eintrag fehlt" bewegt niemanden.
        assert "löst dafür nicht aus" in text
        assert "Erst nach Abstimmung übernehmen." in text

    def test_schweigt_bei_gleichstand(self, paar, caplog):
        eigen, vorlage = paar
        _schreibe(eigen, ["a"])
        _schreibe(vorlage, ["a"])
        with caplog.at_level(logging.WARNING):
            melde_fehlende(eigen, liste="triggers", schluessel="category",
                           bezeichnung="X", folge="Y")
        assert caplog.text == ""
