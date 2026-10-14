"""Bezugsfächer aus `subjects.yaml` (0.16, Schritt 2) — der Seed prüft, bevor er schreibt.

Ein Tippfehler im Slug wäre sonst stumm: kein Bezug, und NwT fände die Biologie-Begriffe
nicht, ohne dass es jemand merkt.
"""
import asyncio
import importlib.util
from pathlib import Path

import pytest
import yaml

_BACKEND = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("seed_subjects", _BACKEND / "scripts" / "seed_subjects.py")
seed_subjects = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_subjects)


def _faecher(**bezug):
    return [{"slug": s, "name": s.title(), **({"bezugsfaecher": b} if b is not None else {})}
            for s, b in bezug.items()]


def test_normalisiert_gerichtet_und_ohne_eintrag_leer():
    ergebnis, fehler = seed_subjects.bezugsfaecher(
        _faecher(nwt=["Chemie", "biologie", "chemie "], chemie=None, biologie=None))
    assert fehler == []
    assert ergebnis == {"nwt": ["biologie", "chemie"], "chemie": [], "biologie": []}


def test_unbekannter_slug_faellt_auf():
    _, fehler = seed_subjects.bezugsfaecher(_faecher(nwt=["bio"], biologie=None))
    assert len(fehler) == 1 and "'bio'" in fehler[0]


def test_ein_fach_nennt_sich_nicht_selbst():
    _, fehler = seed_subjects.bezugsfaecher(_faecher(nwt=["nwt"]))
    assert len(fehler) == 1 and "selbst" in fehler[0]


def test_keine_liste_faellt_auf():
    _, fehler = seed_subjects.bezugsfaecher(_faecher(nwt="biologie", biologie=None))
    assert len(fehler) == 1 and "Liste" in fehler[0]


def test_bei_fehlern_schreibt_der_seed_nichts(tmp_path, monkeypatch):
    """Geprüft wird **vor** der Verbindung — ein halb geschriebener Seed hätte die übrigen
    Fächer schon aktualisiert."""
    datei = tmp_path / "subjects.yaml"
    datei.write_text(yaml.safe_dump({"subjects": _faecher(nwt=["bio"], biologie=None)}), encoding="utf-8")

    def keine_verbindung(*_a, **_k):
        raise AssertionError("Der Seed hat trotz Fehler eine Verbindung geöffnet")
    monkeypatch.setattr(seed_subjects, "create_async_engine", keine_verbindung)

    with pytest.raises(SystemExit):
        asyncio.run(seed_subjects.seed(datei))


def test_die_beispielkonfiguration_ist_gueltig():
    daten = yaml.safe_load((_BACKEND.parent / "config" / "subjects.example.yaml").read_text(encoding="utf-8"))
    assert seed_subjects.bezugsfaecher(daten["subjects"])[1] == []
