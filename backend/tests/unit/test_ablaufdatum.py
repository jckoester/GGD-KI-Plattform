"""Das Ablaufdatum wird beim Anlegen aus der Taxonomie vorbelegt (04.09.2026).

**Der Befund, der dazu führte:** `valid_until_default` stand seit ADR-013 in der
Taxonomie und wurde von **keinem** Anlegeweg gelesen — allein die Reaktivierung nutzte
es. Gemessen am Entwicklungsbestand: null von 19 134 Knoten trugen ein Ablaufdatum, der
nächtliche Lebenszyklus-Lauf aus AP4 archivierte also nie etwas. Die Mechanik war gebaut
und hatte keinen Eingang.

Geprüft wird beides: die reine Ableitung (:func:`vorgeschlagenes_ablaufdatum`) und die
``before_insert``-Regel am Modell, die sie an **allen** fünf Erzeugern wirksam macht,
ohne dass einer davon sie kennt.
"""
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.context.ablauf import vorgeschlagenes_ablaufdatum
from app.db.models import ContextNode


class _Schuljahr:
    def __init__(self, ende: date):
        self.ende = ende


def _mit_schuljahresende(ende: date):
    """Ersetzt die Schuljahres-Config — `load_school_year` ist `lru_cache`-gepuffert."""
    return patch("app.planning.calendar.load_school_year", return_value=_Schuljahr(ende))


class TestAbleitung:
    def test_typ_ohne_vorgabe_bleibt_dauerhaft(self):
        assert vorgeschlagenes_ablaufdatum("begriff") is None
        assert vorgeschlagenes_ablaufdatum("methode") is None
        assert vorgeschlagenes_ablaufdatum(None) is None

    def test_schuljahresende_wird_uebernommen(self):
        ende = date.today() + timedelta(days=200)
        with _mit_schuljahresende(ende):
            assert vorgeschlagenes_ablaufdatum("unterrichtsstunde") == ende
            assert vorgeschlagenes_ablaufdatum("unterrichtseinheit") == ende
            assert vorgeschlagenes_ablaufdatum("schuelertext") == ende

    def test_vergangenes_schuljahresende_ergibt_kein_datum(self):
        """Sonst archivierte der nächtliche Lauf den Knoten noch in derselben Nacht.

        Der Fall ist nicht konstruiert: Am 02.09.2026 stand die Produktiv-Config noch auf
        2025/26 (Ende 29.07.2026). Ein Anlegen sähe dann aus, als hätte es nicht
        funktioniert.
        """
        with _mit_schuljahresende(date.today() - timedelta(days=30)):
            assert vorgeschlagenes_ablaufdatum("unterrichtsstunde") is None

    def test_heute_zaehlt_noch_nicht_als_zukunft(self):
        with _mit_schuljahresende(date.today()):
            assert vorgeschlagenes_ablaufdatum("unterrichtsstunde") is None


class TestModellregel:
    """Die `before_insert`-Regel — ohne Datenbank, durch direktes Auslösen."""

    @staticmethod
    def _vor_dem_insert(node: ContextNode) -> None:
        """Löst die Regel direkt aus — `mapper` und `connection` nutzt sie nicht."""
        from app.db.models import _ablaufdatum_vorbelegen

        _ablaufdatum_vorbelegen(None, None, node)

    def test_planungsknoten_bekommt_das_schuljahresende(self):
        ende = date.today() + timedelta(days=100)
        node = ContextNode(category="artifact", content_type="unterrichtsstunde", title="T")
        with _mit_schuljahresende(ende):
            self._vor_dem_insert(node)
        assert node.valid_until == ende

    def test_gesetztes_datum_bleibt_unangetastet(self):
        """Nur füllen, nie überschreiben — auch nicht bei Import oder Migration."""
        eigenes = date.today() + timedelta(days=7)
        node = ContextNode(
            category="artifact", content_type="unterrichtsstunde", title="T",
            valid_until=eigenes,
        )
        with _mit_schuljahresende(date.today() + timedelta(days=100)):
            self._vor_dem_insert(node)
        assert node.valid_until == eigenes

    def test_typ_ohne_vorgabe_bleibt_leer(self):
        node = ContextNode(category="knowledge", content_type="methode", title="T")
        self._vor_dem_insert(node)
        assert node.valid_until is None

    @pytest.mark.parametrize("content_type", [
        "unterrichtsstunde", "unterrichtseinheit", "lernplan", "schuelertext",
        "schuelerpraesentation", "strukturierung", "feedback_text",
    ])
    def test_alle_sieben_ablaufenden_typen(self, content_type):
        """Der Beschluss vom 04.09.2026: alle sieben, auch die Planungsknoten."""
        from app.context.taxonomy import CONTENT_TYPE_TO_CATEGORY

        ende = date.today() + timedelta(days=100)
        node = ContextNode(
            category=CONTENT_TYPE_TO_CATEGORY[content_type],
            content_type=content_type, title="T",
        )
        with _mit_schuljahresende(ende):
            self._vor_dem_insert(node)
        assert node.valid_until == ende
