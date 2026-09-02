"""Unit-Tests für die typgebundene Metadaten-Prüfung (AP2).

Bewusst schlank: Geprüft wird nur, was eine Bedeutung für die Anwendung hat. Ein
generisches Schema je Typ ist offen und gehört zu AP5.
"""

import pytest

from app.context.metadata import validate_node_metadata


class TestBegriffAbKlasse:

    @pytest.mark.parametrize("wert", [1, 5, 7, 13])
    def test_gueltige_klassenstufen(self, wert):
        validate_node_metadata("begriff", {"ab_klasse": wert})

    def test_none_ist_erlaubt(self):
        """Das Feld ist optional — ausdrücklich leer zu lassen ist kein Fehler."""
        validate_node_metadata("begriff", {"ab_klasse": None})

    def test_fehlendes_feld_ist_erlaubt(self):
        validate_node_metadata("begriff", {"quelle": "Duden"})

    @pytest.mark.parametrize("wert", ["7", 7.5, [7]])
    def test_nicht_ganzzahlig(self, wert):
        with pytest.raises(ValueError, match="ganze Zahl"):
            validate_node_metadata("begriff", {"ab_klasse": wert})

    def test_bool_gilt_nicht_als_zahl(self):
        """`True` ist in Python ein `int` und ginge sonst als Klasse 1 durch."""
        with pytest.raises(ValueError, match="ganze Zahl"):
            validate_node_metadata("begriff", {"ab_klasse": True})

    @pytest.mark.parametrize("wert", [0, -1, 14, 99])
    def test_ausserhalb_der_stufen(self, wert):
        with pytest.raises(ValueError, match="zwischen 1 und 13"):
            validate_node_metadata("begriff", {"ab_klasse": wert})

    def test_gilt_nur_fuer_begriff(self):
        """Andere Typen dürfen `ab_klasse` frei belegen — es bedeutet dort nichts."""
        validate_node_metadata("arbeitsblatt", {"ab_klasse": "irgendwas"})


class TestStrukturierungForm:

    @pytest.mark.parametrize("wert", ["gliederung", "mindmap"])
    def test_gueltige_formen(self, wert):
        validate_node_metadata("strukturierung", {"form": wert})

    @pytest.mark.parametrize("wert", ["skizze", "Mindmap", "", None])
    def test_ungueltige_form(self, wert):
        with pytest.raises(ValueError, match="gliederung oder mindmap"):
            validate_node_metadata("strukturierung", {"form": wert})

    def test_fehlendes_feld_wird_hier_nicht_erzwungen(self):
        """Pflichtfeld ist es im Formular (AP8), nicht in dieser Prüfung."""
        validate_node_metadata("strukturierung", {"titel_alt": "x"})


class TestUnberuehrt:

    def test_leere_metadaten(self):
        validate_node_metadata("begriff", None)
        validate_node_metadata("begriff", {})

    def test_ohne_content_type(self):
        validate_node_metadata(None, {"ab_klasse": "kaputt"})
