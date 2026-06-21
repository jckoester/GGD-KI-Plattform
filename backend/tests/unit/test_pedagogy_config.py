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
