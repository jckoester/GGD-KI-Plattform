"""Erkennung von Nachschlage-Anfragen (app/context/lookup.py).

Der Kern ist nicht, *dass* Namen gefunden werden, sondern **wann** die Regel greift. Eine
zu großzügige Regel richtet Schaden an: „Gedichte **interpretieren** und sprachliche
Bilder deuten" enthält den Namen eines Operators, meint aber Deutsch-Kompetenzen. Feuert
das Nachschlagen dort, verschlechtert es genau den Fall, um den es geht.
"""

import pytest

from app.context.lookup import nachschlage_begriff, normalisiere_titel, reduziere


class TestNachschlagenErkannt:
    @pytest.mark.parametrize("frage", [
        "nennen",
        "Operator nennen",
        "Was bedeutet der Operator nennen?",
        "Bedeutung des Operators nennen",
        'Erstelle eine Übersicht über die Operatorendefinitionen für "nennen" '
        "in den verschiedenen Fächern.",
    ])
    def test_verschiedene_frageformen_fuehren_auf_denselben_begriff(self, frage):
        assert nachschlage_begriff(frage) == "nennen"

    def test_zusammensetzung_wird_erkannt(self):
        """Im Deutschen steht der Kopf hinten: „Operatorendefinitionen" ist so generisch
        wie „Definitionen". Ohne diese Regel scheiterte genau der Prompt, der den Fall
        ausgelöst hat."""
        assert reduziere("Operatorendefinitionen für nennen") == ["nennen"]

    def test_mehrwortiger_name_bleibt_zusammen(self):
        assert nachschlage_begriff("Was ist die Leitidee Messen?") == "leitidee messen"


class TestNachschlagenNichtErkannt:
    def test_thematische_anfrage_liefert_keinen_einzelbegriff(self):
        """Die entscheidende Zusage.

        Die verworfene Regel „irgendein Wort trifft einen Titel" hätte hier
        „interpretieren" geliefert und den Operator nach vorn gezogen.
        """
        begriff = nachschlage_begriff(
            "Gedichte interpretieren und sprachliche Bilder deuten"
        )
        assert begriff is not None
        assert " " in begriff, "mehrere Wörter — trifft keinen Titel und bleibt folgenlos"
        assert begriff != "interpretieren"

    @pytest.mark.parametrize("frage", ["", "   ", "Was ist das?", "Bitte erkläre mir das"])
    def test_ohne_inhalt_kein_begriff(self, frage):
        assert nachschlage_begriff(frage) is None


class TestNormalisierung:
    @pytest.mark.parametrize("titel,erwartet", [
        ("3.3.2 Leitidee Messen", "leitidee messen"),
        ("3.6.1(13) etwas erläutern", "etwas erläutern"),
        ("(13) etwas erläutern", "etwas erläutern"),
        ("nennen", "nennen"),
        ("  Doppelte   Leerzeichen  ", "doppelte leerzeichen"),
    ])
    def test_titel_ohne_nummer_und_klein(self, titel, erwartet):
        assert normalisiere_titel(titel) == erwartet

    def test_gleiche_regel_wie_beim_einbetten(self):
        """`embedding.py` nutzt dieselbe Funktion — was dort vom Titel übrig bleibt, muss
        hier auffindbar sein."""
        from app.context import embedding

        assert embedding.normalisiere_titel is normalisiere_titel


class TestIndexUndAbfrageBleibenGleich:
    """Der Ausdrucksindex (Migration 0053) wirkt nur, wenn er **zeichengenau** dem
    Ausdruck der Abfrage entspricht. Weichen sie ab, benutzt PostgreSQL ihn nicht —
    ohne Fehler, nur rund 70 ms langsamer je Suche."""

    def test_abfrage_nutzt_die_gemeinsame_funktion(self):
        from app.chat.router import _NACHSCHLAGE_SQL
        from app.context.lookup import titel_normalisiert_sql

        assert titel_normalisiert_sql("c.title") in str(_NACHSCHLAGE_SQL)

    def test_migration_nutzt_die_gemeinsame_funktion(self):
        """Migrationen sind sonst eingefrorene Artefakte — hier ist die Kopplung gewollt,
        weil ein abgeschriebener Ausdruck genau der Fehler wäre, den niemand bemerkt."""
        from pathlib import Path

        quelle = (
            Path(__file__).resolve().parents[2]
            / "alembic" / "versions" / "0053_titel_nachschlagen_index.py"
        ).read_text(encoding="utf-8")
        assert "from app.context.lookup import titel_normalisiert_sql" in quelle
        assert "titel_normalisiert_sql('title')" in quelle
