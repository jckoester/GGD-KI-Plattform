"""Unit-Tests für app.planning.phasen — AP6b, Schritt 3.

Die Kennung einer Phase ist Referenz: `phasen_status` schlüsselt danach, die
Übertragung wählt Phasen darüber aus, und die Materialkanten vermerken, in welchen
Phasen ein Baustein vorkommt. Fehlt sie, fällt nichts aus — es wird still ungenau.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.planning.phasen import sichere_phasen_kennungen


def test_fehlender_schluessel_bekommt_eine_kennung():
    [phase] = sichere_phasen_kennungen([{"name": "Erarbeitung"}])
    assert phase["id"]
    assert phase["name"] == "Erarbeitung"


def test_null_bekommt_eine_kennung():
    """Der Fall aus der Praxis: `patch_lesson` speichert mit `exclude_none=False`,
    eine Phase ohne Kennung landet also als ``"id": null`` in den Metadaten."""
    [phase] = sichere_phasen_kennungen([{"id": None, "name": "P"}])
    assert isinstance(phase["id"], str) and phase["id"]


def test_leerer_string_bekommt_eine_kennung():
    [phase] = sichere_phasen_kennungen([{"id": "   ", "name": "P"}])
    assert phase["id"].strip()


def test_vorhandene_kennung_bleibt_unangetastet():
    """Sie neu zu vergeben ließe `phasen_status` und Übertragungen ins Leere laufen."""
    [phase] = sichere_phasen_kennungen([{"id": "p1", "name": "P"}])
    assert phase["id"] == "p1"


def test_kennungen_sind_untereinander_verschieden():
    phasen = sichere_phasen_kennungen([{"name": "A"}, {"name": "B"}, {"name": "C"}])
    assert len({p["id"] for p in phasen}) == 3


def test_zwei_laeufe_aendern_einen_fertigen_stand_nicht():
    """Sonst schriebe jedes Speichern neue Kennungen — und bräche alle Verweise."""
    einmal = sichere_phasen_kennungen([{"name": "A"}, {"id": "p2", "name": "B"}])
    zweimal = sichere_phasen_kennungen(einmal)
    assert [p["id"] for p in einmal] == [p["id"] for p in zweimal]


def test_uebrige_felder_bleiben_erhalten():
    [phase] = sichere_phasen_kennungen(
        [{"name": "P", "dauer_min": 15, "material": [{"typ": "text", "wert": "x"}]}]
    )
    assert phase["dauer_min"] == 15
    assert phase["material"] == [{"typ": "text", "wert": "x"}]


def test_eingabe_wird_nicht_veraendert():
    """Die Funktion gibt Neues zurück; der Aufrufer entscheidet, was er speichert."""
    eingabe = [{"name": "P"}]
    sichere_phasen_kennungen(eingabe)
    assert "id" not in eingabe[0]


def test_leeres_und_fehlendes():
    assert sichere_phasen_kennungen([]) == []
    assert sichere_phasen_kennungen(None) == []


def test_nicht_dicts_werden_durchgereicht():
    """Kaputte Daten sollen hier nicht den Speichervorgang sprengen."""
    assert sichere_phasen_kennungen(["kaputt", None]) == ["kaputt", None]
