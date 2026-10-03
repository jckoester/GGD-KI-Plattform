"""Phasenfelder überleben das Speichern — `uebernimm_zusatzfelder` (0.13, P2).

Nachbereitung, Streichen und Übertragen schreiben Felder in eine Phase, die kein
Editor kennt. Bis 0.12 verwarf jedes Speichern im Planer sie; eine als „offen"
nachbereitete Phase war danach im Reflow nicht mehr offen.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.planning.phasen import uebernimm_zusatzfelder

GESPEICHERT = [
    {"id": "p1", "name": "Einstieg", "dauer_min": 10, "prio": "kern", "status": "erledigt"},
    {"id": "p2", "name": "Erarbeitung", "dauer_min": 20, "prio": "kern",
     "status": "gestrichen", "kuerzung": True},
    {"id": "p3", "name": "Übertragen", "dauer_min": 5, "prio": "uebung",
     "status": "geplant", "uebertrag_von": "stunde-a"},
]


def test_bekannte_phase_behaelt_was_der_editor_nicht_kennt():
    neu = [{"id": "p2", "name": "Erarbeitung (neu)", "dauer_min": 25, "prio": "kern"}]
    [phase] = uebernimm_zusatzfelder(neu, GESPEICHERT)
    assert phase["status"] == "gestrichen" and phase["kuerzung"] is True
    # Die Schemafelder gehören dem Editor.
    assert phase["name"] == "Erarbeitung (neu)" and phase["dauer_min"] == 25


def test_uebertragsmarke_bleibt():
    [phase] = uebernimm_zusatzfelder([{"id": "p3", "name": "Übertragen", "dauer_min": 5}], GESPEICHERT)
    assert phase["uebertrag_von"] == "stunde-a"


def test_neue_phase_bekommt_nichts_auch_kein_null():
    for neu in ([{"name": "Neu"}], [{"id": None, "name": "Neu"}], [{"id": "unbekannt", "name": "Neu"}]):
        [phase] = uebernimm_zusatzfelder(neu, GESPEICHERT)
        assert "status" not in phase and "kuerzung" not in phase, neu


def test_weggelassene_phase_ist_weg_samt_feldern():
    ergebnis = uebernimm_zusatzfelder([{"id": "p1", "name": "Einstieg", "dauer_min": 10}], GESPEICHERT)
    assert [p["id"] for p in ergebnis] == ["p1"]
    assert all("kuerzung" not in p for p in ergebnis)


def test_was_der_editor_darueber_hinaus_schickt_zaehlt_nicht():
    """Der Assistent liest die Phasen samt `status` und könnte ihn zurückschicken — der
    gespeicherte gilt, ein erfundener zählt nicht."""
    neu = [{"id": "p1", "name": "Einstieg", "dauer_min": 10, "status": "offen", "erfunden": 1},
           {"name": "Neu", "status": "erledigt"}]
    eins, zwei = uebernimm_zusatzfelder(neu, GESPEICHERT)
    assert eins["status"] == "erledigt" and "erfunden" not in eins
    assert "status" not in zwei


def test_nicht_jedes_feld_einzeln_genannt():
    """„Alles, was das Schema nicht kennt" statt einer festen Liste: Ein Feld, das eine
    künftige Operation setzt, ist gleich mit geschützt."""
    gespeichert = [{"id": "p1", "name": "E", "dauer_min": 5, "kuenftig": {"x": 1}}]
    [phase] = uebernimm_zusatzfelder([{"id": "p1", "name": "E", "dauer_min": 5}], gespeichert)
    assert phase["kuenftig"] == {"x": 1}


def test_leere_und_kaputte_eingaben():
    assert uebernimm_zusatzfelder(None, GESPEICHERT) == []
    assert uebernimm_zusatzfelder([{"name": "E"}], None) == [{"name": "E"}]
    assert uebernimm_zusatzfelder(["kaputt"], GESPEICHERT) == ["kaputt"]


def test_planungsassistent_kann_die_kennung_zurueckgeben():
    """Ohne `id` im Werkzeugschema greift die Regel beim Assistenten nie: Er schickt dann
    jede Phase als neue, und Nachbereitungsstatus und Marken gehen verloren."""
    import app.planning.assistant_tools  # noqa: F401 — registriert die Werkzeuge
    from app.chat.tools import TOOL_REGISTRY

    definition = TOOL_REGISTRY["update_lesson_phases"].definition
    phase = definition["function"]["parameters"]["properties"]["phasen"]["items"]
    assert "id" in phase["properties"]
    assert "id" not in phase.get("required", [])   # neue Phasen kommen ohne
