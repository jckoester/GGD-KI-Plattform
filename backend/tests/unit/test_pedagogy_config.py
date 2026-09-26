"""Unit-Tests für app.pedagogy.config (Phase 13, Schritt 1)."""

import os

import pytest
from pydantic import ValidationError

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.config import settings
from app.pedagogy.config import (
    PedagogyConfig,
    get_student_augmentations,
    invalidate_pedagogy_cache,
    list_augmentations,
    load_pedagogy,
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    invalidate_pedagogy_cache()
    yield
    invalidate_pedagogy_cache()


def test_load_pedagogy_has_preambles():
    cfg = load_pedagogy()
    assert cfg.preambles.universal_base.strip()
    assert "Lernassistent" in cfg.preambles.student_extension
    assert "Lehrkräfte" in cfg.preambles.teacher_extension
    assert cfg.output_format.strip()


def test_load_pedagogy_has_augmentations():
    cfg = load_pedagogy()
    keys = {a.key for a in cfg.student_augmentations}
    assert "no_complete_homework_solutions" in keys
    assert "socratic_preference" in keys


def test_get_student_augmentations_all_by_default():
    texts = get_student_augmentations()
    assert len(texts) == len(load_pedagogy().student_augmentations)
    assert all(isinstance(t, str) and t for t in texts)


def test_get_student_augmentations_excludes_disabled():
    full = get_student_augmentations()
    reduced = get_student_augmentations(disabled=["no_complete_homework_solutions"])
    assert len(reduced) == len(full) - 1


def test_get_student_augmentations_unknown_disabled_key_ignored():
    full = get_student_augmentations()
    same = get_student_augmentations(disabled=["does_not_exist"])
    assert len(same) == len(full)


def test_list_augmentations_returns_key_and_label():
    items = list_augmentations()
    assert all("key" in i and "label" in i for i in items)
    keys = {i["key"] for i in items}
    assert "metacognitive_nudges" in keys


def test_caching_returns_same_instance():
    a = load_pedagogy()
    b = load_pedagogy()
    assert a is b


def test_missing_file_raises(monkeypatch):
    invalidate_pedagogy_cache()
    monkeypatch.setattr(settings, "pedagogy_path", "config/does_not_exist.yaml")
    with pytest.raises(FileNotFoundError):
        load_pedagogy()


def test_validation_rejects_missing_preamble():
    with pytest.raises(ValidationError):
        PedagogyConfig.model_validate(
            {"preambles": {"universal_base": "x", "student_extension": "y"}}
        )


class TestSchuelerPraeambelN8:
    """Zusagen der Schüler-Präambel in der Fassung N8 (Paket 9, Nachgang AP7 Schritt 5).

    Die Texte selbst sind Redaktionssache und werden hier **nicht** festgenagelt —
    geprüft ist, was daran Mechanik ist.
    """

    def test_schluessel_der_zusaetze_unveraendert(self):
        """⚠️ **Stumme Falle.** `assistants.disabled_augmentations` ist eine
        Textspalte mit genau diesen Schlüsseln (Alembic 0032). Wer einen Schlüssel
        umbenennt, schaltet bei jedem Assistenten, der ihn abgewählt hatte, den
        Zusatz **wieder ein** — ohne Fehler, ohne Migration, ohne Hinweis in der
        Oberfläche. N8 hat alle vier Texte neu gefasst und die Schlüssel bewusst
        stehen lassen.
        """
        vorhanden = {a.key for a in load_pedagogy().student_augmentations}
        # Teilmenge, nicht Gleichheit: Ein **neuer** Zusatz ist harmlos (er ist überall
        # an, bis ihn jemand abwählt). Gefährlich ist nur, wenn einer verschwindet.
        assert vorhanden >= {
            "no_complete_homework_solutions",
            "socratic_preference",
            "no_verbatim_copy_from_sources",
            "metacognitive_nudges",
        }, f"vorhanden: {sorted(vorhanden)}"

    def _nummern(self, text: str) -> list[int]:
        import re
        return [int(m) for m in re.findall(r"^\s*(\d+)\. ", text, re.MULTILINE)]

    def test_nummerierung_laeuft_ueber_die_praeambeln_durch(self):
        """Die Grundsätze sind **eine** Liste, verteilt auf zwei Bausteine.

        ⚠️ Das Modell sieht `universal_base` und die Zielgruppen-Erweiterung als
        fortlaufenden Text. Ein zusätzlicher Grundsatz in der Basis, ohne die
        Erweiterungen nachzuziehen, ergibt „1, 2, 3, 4 · 4, 5" — zwei Punkte 4.
        """
        cfg = load_pedagogy()
        basis = self._nummern(cfg.preambles.universal_base)
        assert basis == list(range(1, len(basis) + 1))
        for erweiterung in (cfg.preambles.student_extension,
                            cfg.preambles.teacher_extension):
            nummern = self._nummern(erweiterung)
            assert nummern == list(range(basis[-1] + 1, basis[-1] + 1 + len(nummern)))

    def test_querverweis_auf_eigene_punkte_trifft(self):
        """„Die Punkte 4 bis 6 gelten, sofern …" — ein Verweis im Text auf Nummern,
        die die Umnummerierung aus dem vorigen Test mitverschöbe, ohne dass jemand
        den Satz anfasst."""
        import re
        cfg = load_pedagogy()
        nummern = set(self._nummern(cfg.preambles.student_extension))
        verweise = re.findall(r"Punkte (\d+) bis (\d+)", cfg.preambles.student_extension)
        assert verweise, "Der Querverweis fehlt — dann gehört dieser Test weg."
        for von, bis in verweise:
            assert {int(von), int(bis)} <= nummern, (
                f"Verweis auf Punkte {von}–{bis}, vorhanden sind {sorted(nummern)}"
            )
