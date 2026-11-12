"""Angabe „stellt her" (0.40, Päckchen AM): eine Liste, und Migration und Fähigkeiten passen dazu."""
import importlib.util
from pathlib import Path

from app.assistants import produkte
from app.chat.tools import FAEHIGKEITEN

_MIGRATION = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0102_assistant_produces.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("migration_0102", _MIGRATION)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_kennungen_eindeutig_und_beschriftet():
    ids = [p.id for p in produkte.PRODUKTARTEN]
    assert len(ids) == len(set(ids))
    assert ids == ["image", "diagram", "document", "lesson_plan", "year_plan"]
    for p in produkte.PRODUKTARTEN:
        assert p.marke and p.filter


def test_vorschlag_nennt_nur_vorhandene_faehigkeiten():
    for p in produkte.PRODUKTARTEN:
        assert p.faehigkeit is None or p.faehigkeit in FAEHIGKEITEN, p.id


def test_migration_belegt_vor_wie_die_liste_vorschlaegt():
    """Die Migration schreibt ihre Zuordnung fest — sie darf der Liste heute nicht widersprechen."""
    aus_liste = {(p.faehigkeit, p.id) for p in produkte.PRODUKTARTEN if p.faehigkeit}
    assert set(_migration()._VORBELEGUNG) == aus_liste


def test_geordnet_ohne_doppelte_in_listenreihenfolge():
    assert produkte.geordnet(["year_plan", "image", "image"]) == ["image", "year_plan"]
    assert produkte.geordnet([]) == []


def test_unbekannte_werden_genannt():
    assert produkte.unbekannte(["image", "zeitreise"]) == ["zeitreise"]
    assert produkte.unbekannte(["image"]) == []
