"""Der Methodik-Seed darf die Arbeit der Schule nicht überschreiben (AP6).

Nach dem ersten Lauf gehören die Knoten der Schule: `write_scope = school` heißt, jede
Lehrkraft darf sie über die Sammlung bearbeiten. Ein Seed, der bei jedem Lauf Text und
Aliase zurücksetzt, nähme diese Arbeit **lautlos** weg — niemand führt Buch darüber, und
die Datenbank sieht danach aus wie ein sauberer Erstlauf.

Der zweite Schwerpunkt ist die Markierung `metadata.unvollstaendig`: Sie ist der
Unterschied zwischen einem Eintrag, dem die Beschreibung noch fehlt, und einem, der
stillschweigend leer bleibt — und sie hält den Titel-Vektor fern, den `traegt_substanz()`
ohnehin abweisen würde.

Geprüft wird `plane_aenderung()` — die Entscheidung selbst, ohne Datenbank. Die
Datenbankarbeit ringsherum (SELECT, `setattr`, commit) ist mechanisch; die Regeln sind es
nicht.
"""
import importlib.util
from pathlib import Path

import pytest

from app.context.metadata import STUB_MARKIERUNG

SKRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_methodik.py"


def _laden():
    """Über den Dateipfad laden — `backend/scripts/` ist bewusst kein Paket."""
    spec = importlib.util.spec_from_file_location("seed_methodik", SKRIPT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="module")
def seed():
    return _laden()


def _ist(**abweichungen):
    """Ein vorhandener Knoten im Zielzustand — Abweichungen werden übergeben."""
    zustand = {
        "content": "Bestehender Text.",
        "aliase": [],
        "metadata": {},
        "read_scope": "school",
        "write_scope": "school",
        "read_scope_group_id": None,
        "write_scope_group_id": None,
        "embedding_vorhanden": True,
    }
    zustand.update(abweichungen)
    if "aliase" in abweichungen:
        zustand["metadata"] = {**zustand["metadata"], "aliase": abweichungen["aliase"]}
    return zustand


def _anwenden(ist, aenderung):
    """Die geplante Änderung auf den Ist-Zustand anwenden — für die Idempotenzprobe."""
    neu = dict(ist)
    for name, wert in aenderung.felder.items():
        if name == "metadata_":
            neu["metadata"] = wert
            neu["aliase"] = list(wert.get("aliase") or [])
        else:
            neu[name] = wert
    if aenderung.embedding_verwerfen:
        neu["embedding_vorhanden"] = False
    return neu


class TestNeuerKnoten:
    def test_traegt_text_scopes_und_aliase(self, seed):
        baustein = seed.Baustein("Placemat", ("Platzdeckchen",), content="Vier Felder …")
        a = seed.plane_aenderung({}, baustein, "methode")

        assert a.felder["content"] == "Vier Felder …"
        assert a.felder["read_scope"] == "school"
        assert a.felder["write_scope"] == "school"
        assert a.felder["write_scope_group_id"] is None
        assert a.metadata["aliase"] == ["Platzdeckchen"]
        assert STUB_MARKIERUNG not in a.metadata

    def test_ohne_text_wird_als_unvollstaendig_markiert(self, seed):
        a = seed.plane_aenderung({}, seed.Baustein("Placemat"), "methode")
        assert a.metadata[STUB_MARKIERUNG] is True

    def test_sozialform_ohne_text_ist_vollstaendig(self, seed):
        """`content` ist bei `sozialform` kein Pflichtfeld — die Taxonomie entscheidet das."""
        a = seed.plane_aenderung({}, seed.Baustein("Plenum"), "sozialform")
        assert STUB_MARKIERUNG not in a.metadata


class TestSchulbearbeitungBleibt:
    def test_text_der_schule_wird_nicht_ueberschrieben(self, seed):
        baustein = seed.Baustein("Placemat", content="Seed-Fassung")
        a = seed.plane_aenderung(_ist(content="Von der Fachschaft geschrieben"), baustein, "methode")

        assert "content" not in a.felder
        assert a.behalten == ["Text"]

    def test_ueberschreiben_erzwingt_die_seed_fassung(self, seed):
        baustein = seed.Baustein("Placemat", content="Seed-Fassung")
        a = seed.plane_aenderung(
            _ist(content="Von der Fachschaft geschrieben"),
            baustein,
            "methode",
            ueberschreiben=True,
        )

        assert a.felder["content"] == "Seed-Fassung"
        assert a.behalten == []
        assert a.embedding_verwerfen is True

    def test_aliase_der_schule_bleiben(self, seed):
        baustein = seed.Baustein("Placemat", ("Platzdeckchen",), content="Seed")
        a = seed.plane_aenderung(_ist(aliase=["Eigene Bezeichnung"]), baustein, "methode")

        assert "aliase" not in a.felder.get("metadata_", {})
        assert "Aliase" in a.behalten

    def test_leere_aliase_werden_gefuellt(self, seed):
        """Eine leere Liste ist keine Bearbeitung, sondern eine Lücke."""
        baustein = seed.Baustein("Placemat", ("Platzdeckchen",), content="Seed")
        a = seed.plane_aenderung(_ist(aliase=[]), baustein, "methode")

        assert a.metadata["aliase"] == ["Platzdeckchen"]


class TestMarkierung:
    def test_fehlender_text_markiert_bestehenden_knoten(self, seed):
        a = seed.plane_aenderung(_ist(content=""), seed.Baustein("Placemat"), "methode")
        assert a.metadata[STUB_MARKIERUNG] is True
        assert a.embedding_verwerfen is True

    def test_markierung_faellt_weg_wenn_die_schule_schreibt(self, seed):
        """Die Fachschaft hat den Text nachgetragen — der Seed bringt keinen mit."""
        ist = _ist(content="Nachgetragen", metadata={STUB_MARKIERUNG: True})
        a = seed.plane_aenderung(ist, seed.Baustein("Placemat"), "methode")

        assert STUB_MARKIERUNG not in a.metadata
        assert a.felder["metadata_"] == {}

    def test_markierung_faellt_weg_wenn_der_seed_den_text_bringt(self, seed):
        ist = _ist(content="", metadata={STUB_MARKIERUNG: True})
        a = seed.plane_aenderung(ist, seed.Baustein("Placemat", content="Jetzt da"), "methode")

        assert a.felder["content"] == "Jetzt da"
        assert STUB_MARKIERUNG not in a.metadata


class TestScopes:
    def test_abweichender_scope_wird_nachgezogen(self, seed):
        """Der Scope ist kein Redaktionsergebnis, sondern das Zielbild aus ADR-019."""
        ist = _ist(write_scope="subject", write_scope_group_id=7)
        a = seed.plane_aenderung(ist, seed.Baustein("Placemat", content="Text"), "methode")

        assert a.felder["write_scope"] == "school"
        assert a.felder["write_scope_group_id"] is None


class TestEmbedding:
    def test_ohne_vorhandenen_vektor_nichts_zu_verwerfen(self, seed):
        ist = _ist(content="", embedding_vorhanden=False)
        a = seed.plane_aenderung(ist, seed.Baustein("Placemat"), "methode")
        assert a.embedding_verwerfen is False

    def test_sozialform_hat_nie_einen_vektor(self, seed):
        """`sozialform` steht nicht in `EMBEDDING_CONTENT_TYPES` — auch nicht zu verwerfen."""
        ist = _ist(content="alt")
        a = seed.plane_aenderung(
            ist, seed.Baustein("Plenum", content="neu"), "sozialform", ueberschreiben=True
        )
        assert a.felder["content"] == "neu"
        assert a.embedding_verwerfen is False


class TestIdempotenz:
    @pytest.mark.parametrize(
        "content_type,baustein_args",
        [
            ("methode", ("Placemat", ("Platzdeckchen",), "Vier Felder …")),
            ("methode", ("Placemat", (), "")),
            ("sozialform", ("Plenum", ("Frontalunterricht",), "")),
        ],
    )
    def test_zweiter_lauf_wirkt_nicht_mehr(self, seed, content_type, baustein_args):
        titel, aliase, content = baustein_args
        baustein = seed.Baustein(titel, aliase, content=content)

        erst = seed.plane_aenderung({}, baustein, content_type)
        nachher = _anwenden(_ist(content="", aliase=[], embedding_vorhanden=False), erst)
        zweit = seed.plane_aenderung(nachher, baustein, content_type)

        assert zweit.wirkt is False, f"zweiter Lauf ändert: {zweit.geaendert}"
