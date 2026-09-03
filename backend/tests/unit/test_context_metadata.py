"""Unit-Tests für die schemagestützte Metadaten- und Inhaltsprüfung (AP2, AP5a).

Die Regeln stehen seit AP5a als `felder:` am Typ in der Taxonomie — ein Ort für Editor
und Backend. Diese Tests prüfen die **Wirkung** der Beschreibung, nicht ihre Syntax; für
die sorgt die Startprüfung (`pruefe_schema_konsistenz`).
"""

import pytest

from app.context.metadata import (
    ist_stub,
    pruefe_schema_konsistenz,
    validate_node_content,
    validate_node_metadata,
)


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

    @pytest.mark.parametrize("wert,erwartet", [
        (0, "mindestens 1"), (-1, "mindestens 1"), (14, "höchstens 13"), (99, "höchstens 13"),
    ])
    def test_ausserhalb_der_stufen(self, wert, erwartet):
        with pytest.raises(ValueError, match=erwartet):
            validate_node_metadata("begriff", {"ab_klasse": wert})

    def test_gilt_nur_fuer_begriff(self):
        """Andere Typen dürfen `ab_klasse` frei belegen — es bedeutet dort nichts."""
        validate_node_metadata("arbeitsblatt", {"ab_klasse": "irgendwas"})


class TestStrukturierungForm:

    @pytest.mark.parametrize("wert", ["gliederung", "mindmap"])
    def test_gueltige_formen(self, wert):
        validate_node_metadata("strukturierung", {"form": wert})

    @pytest.mark.parametrize("wert", ["skizze", "Mindmap", 3])
    def test_ungueltige_form(self, wert):
        with pytest.raises(ValueError, match="gliederung, mindmap"):
            validate_node_metadata("strukturierung", {"form": wert})

    @pytest.mark.parametrize("wert", ["", None])
    def test_leer_gelassen_ist_erlaubt(self, wert):
        """Ein leeres Feld ist ein unvollständiger Eintrag, kein kaputter."""
        validate_node_metadata("strukturierung", {"form": wert})

    def test_schema_gilt_auch_ohne_sammlung(self):
        """⚠️ `strukturierung` **ruht** und hat keine Sammlungsansicht.

        Im ersten AP5a-Entwurf hing das Feldschema unter `collection:` — damit verlor
        jeder ruhende Typ seine Feldprüfung, ohne dass es aufgefallen wäre. Deshalb
        steht `felder:` am Typ.
        """
        from app.context.taxonomy import COLLECTIONS, feld_schema

        assert "strukturierung" not in COLLECTIONS
        assert "form" in feld_schema("strukturierung")

    def test_fehlendes_feld_wird_hier_nicht_erzwungen(self):
        """Pflichtfeld ist es im Formular (AP8), nicht in dieser Prüfung."""
        validate_node_metadata("strukturierung", {"titel_alt": "x"})


class TestUnberuehrt:

    def test_leere_metadaten(self):
        validate_node_metadata("begriff", None)
        validate_node_metadata("begriff", {})

    def test_ohne_content_type(self):
        validate_node_metadata(None, {"ab_klasse": "kaputt"})


class TestContentPflicht:
    """`methode` und `begriff` verlangen einen Text — mit gutem Grund.

    Beide tragen ein Embedding. Ohne Text bestünde ihr Vektor faktisch aus dem Titel,
    und genau solche Knoten weist `traegt_substanz()` ab: Der Eintrag wäre thematisch
    unsichtbar, ohne dass es jemandem auffiele.
    """

    @pytest.mark.parametrize("typ", ["methode", "begriff"])
    def test_leerer_text_wird_abgelehnt(self, typ):
        for leer in (None, "", "   "):
            with pytest.raises(ValueError, match="Pflichtfeld"):
                validate_node_content(typ, leer)

    @pytest.mark.parametrize("typ", ["methode", "begriff"])
    def test_text_genuegt(self, typ):
        validate_node_content(typ, "Eine Beschreibung.")

    @pytest.mark.parametrize("typ", ["sozialform", "methodenblatt", "arbeitsblatt"])
    def test_andere_typen_duerfen_leer_bleiben(self, typ):
        validate_node_content(typ, None)

    def test_fehlermeldung_nennt_das_feldlabel(self):
        """Bei `begriff` heißt das Feld „Definition", nicht „Inhalt"."""
        with pytest.raises(ValueError, match="Definition"):
            validate_node_content("begriff", "")


class TestSchemaKonsistenz:
    """Die Startprüfung über die Konfiguration selbst (ADR-018)."""

    def test_auslieferungsstand_ist_konsistent(self):
        assert pruefe_schema_konsistenz() == []

    def test_unbekannter_feldtyp_faellt_auf(self, monkeypatch):
        from app.context import taxonomy

        monkeypatch.setattr(
            taxonomy, "FELD_SCHEMATA",
            {"begriff": {"ab_klasse": {"typ": "zahl", "label": "X"}}},
        )
        assert any("unbekannter Feldtyp" in b for b in pruefe_schema_konsistenz())

    def test_auswahlfeld_ohne_werte(self, monkeypatch):
        from app.context import taxonomy

        monkeypatch.setattr(
            taxonomy, "FELD_SCHEMATA",
            {"begriff": {"art": {"typ": "auswahl", "label": "Art"}}},
        )
        assert any("ohne `werte`" in b for b in pruefe_schema_konsistenz())

    def test_spalte_ohne_feld(self, monkeypatch):
        """Eine Spalte, die auf kein Feld zeigt, bliebe in der Liste leer."""
        from app.context import taxonomy

        monkeypatch.setattr(taxonomy, "FELD_SCHEMATA", {})
        monkeypatch.setattr(
            taxonomy, "COLLECTIONS",
            {"begriff": {"beschreibung": "x", "spalten": ["titel", "gibt_es_nicht"]}},
        )
        assert any("gibt_es_nicht" in b for b in pruefe_schema_konsistenz())

    def test_sammlung_ohne_beschreibung(self, monkeypatch):
        from app.context import taxonomy

        monkeypatch.setattr(taxonomy, "FELD_SCHEMATA", {})
        monkeypatch.setattr(
            taxonomy, "COLLECTIONS", {"begriff": {"spalten": ["titel"]}},
        )
        assert any("keine `beschreibung`" in b for b in pruefe_schema_konsistenz())


class TestStubs:
    """Der Verknüpfen-Dialog legt Bausteine ohne Inhalt an (UI-Notiz A8).

    Das ist die eine Ausnahme von der Inhaltspflicht — und sie ist **markiert**. Genau
    darin liegt der Unterschied zu einem stillschweigend leeren Eintrag: Ein Stub ist
    zählbar und filterbar, die Fachschaft findet ihn wieder.
    """

    def test_markierter_stub_darf_ohne_inhalt(self):
        validate_node_content("begriff", None, {"unvollstaendig": True})
        validate_node_content("methode", "", {"unvollstaendig": True})

    def test_ohne_markierung_gilt_die_pflicht(self):
        with pytest.raises(ValueError, match="Pflichtfeld"):
            validate_node_content("begriff", None, {})

    def test_markierung_hebelt_die_feldpruefung_nicht_aus(self):
        """Ein Stub darf unvollständig sein, nicht falsch."""
        with pytest.raises(ValueError, match="höchstens 13"):
            validate_node_metadata("begriff", {"unvollstaendig": True, "ab_klasse": 99})

    def test_ist_stub(self):
        assert ist_stub({"unvollstaendig": True})
        assert not ist_stub({"unvollstaendig": False})
        assert not ist_stub({})
        assert not ist_stub(None)


class TestRelationsKonfiguration:
    """Der Verknüpfen-Dialog darf nur Relationen anbieten, die die Datenbank kennt."""

    def test_auslieferungsstand_ist_gueltig(self):
        assert pruefe_schema_konsistenz() == []

    def test_unbekannte_relation_faellt_auf(self, monkeypatch):
        from app.context import taxonomy

        monkeypatch.setattr(
            taxonomy, "COLLECTIONS",
            {"begriff": {
                "beschreibung": "x", "spalten": ["titel"],
                "relationen": {"gehoert_irgendwie_zu": {"label": "…"}},
            }},
        )
        monkeypatch.setattr(taxonomy, "FELD_SCHEMATA", {})
        befunde = pruefe_schema_konsistenz()
        assert any("unbekannte Relation" in b for b in befunde)

    def test_relation_ohne_label(self, monkeypatch):
        """Die Oberfläche zeigt die Richtung als Satz — dafür braucht sie einen."""
        from app.context import taxonomy

        monkeypatch.setattr(
            taxonomy, "COLLECTIONS",
            {"begriff": {
                "beschreibung": "x", "spalten": ["titel"],
                "relationen": {"related_to": {}},
            }},
        )
        monkeypatch.setattr(taxonomy, "FELD_SCHEMATA", {})
        assert any("kein `label`" in b for b in pruefe_schema_konsistenz())
