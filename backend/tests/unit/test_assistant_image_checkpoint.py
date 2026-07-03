"""Jugendschutz-Prüfpunkt für Bild-Assistenten (Phase 16 Schritt 9).

Schulweite Bild-Assistenten, die Schüler:innen erreichen, müssen IMMER in
'pending_review' gehen — unabhängig vom teacher_schoolwide_sharing_requires_admin-
Schalter. Gruppen-/private Bild-Assistenten bleiben selbst-freigebbar.
"""
import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.config import settings
from app.api.assistants import _initial_status, _is_student_visible_image_assistant


# ── _is_student_visible_image_assistant ───────────────────────────────────────

@pytest.mark.parametrize("audience,tool_groups,expected", [
    ("student", ["image_generation"], True),
    ("all", ["image_generation"], True),
    ("all", ["planning", "image_generation"], True),
    ("teacher", ["image_generation"], False),       # nicht schülersichtbar
    ("student", ["planning"], False),               # kein Bild-Werkzeug
    ("student", [], False),
    ("all", None, False),
])
def test_is_student_visible_image_assistant(audience, tool_groups, expected):
    assert _is_student_visible_image_assistant(audience, tool_groups) is expected


# ── _initial_status: Admin startet immer im Draft ─────────────────────────────

def test_admin_always_draft_even_for_image():
    assert _initial_status("all", "admin", "all", ["image_generation"]) == "draft"


# ── _initial_status: Gruppen-/private Bild-Assistenten bleiben self-serve ──────

def test_group_image_assistant_stays_active(monkeypatch):
    monkeypatch.setattr(settings, "teacher_schoolwide_sharing_requires_admin", False)
    # teaching_group ist kein schulweiter Scope → keine Review-Pflicht (D1a)
    assert _initial_status("teaching_group", "teacher", "student", ["image_generation"]) == "active"


def test_private_image_assistant_stays_active(monkeypatch):
    monkeypatch.setattr(settings, "teacher_schoolwide_sharing_requires_admin", False)
    assert _initial_status("private", "teacher", "all", ["image_generation"]) == "active"


# ── _initial_status: schulweite schülersichtbare Bild-Assistenten → review ────

def test_schoolwide_student_image_forces_review_even_when_switch_off(monkeypatch):
    monkeypatch.setattr(settings, "teacher_schoolwide_sharing_requires_admin", False)
    # Ohne Bild wäre es 'active' (Schalter aus) — der Bild-Prüfpunkt überschreibt das.
    assert _initial_status("all_students", "teacher", "student", ["image_generation"]) == "pending_review"
    assert _initial_status("all", "teacher", "all", ["image_generation"]) == "pending_review"
    assert _initial_status("grade", "teacher", "student", ["image_generation"]) == "pending_review"


def test_schoolwide_non_image_follows_switch(monkeypatch):
    # Kein Bild-Werkzeug → normale Regel (Schalter entscheidet)
    monkeypatch.setattr(settings, "teacher_schoolwide_sharing_requires_admin", False)
    assert _initial_status("all_students", "teacher", "student", ["planning"]) == "active"
    monkeypatch.setattr(settings, "teacher_schoolwide_sharing_requires_admin", True)
    assert _initial_status("all_students", "teacher", "student", ["planning"]) == "pending_review"


def test_schoolwide_image_but_teacher_audience_follows_switch(monkeypatch):
    # Bild-Assistent nur für Lehrkräfte → nicht schülersichtbar → kein Sonder-Gate
    monkeypatch.setattr(settings, "teacher_schoolwide_sharing_requires_admin", False)
    assert _initial_status("grade", "teacher", "teacher", ["image_generation"]) == "active"


def test_schoolwide_image_default_switch_on_is_review(monkeypatch):
    monkeypatch.setattr(settings, "teacher_schoolwide_sharing_requires_admin", True)
    assert _initial_status("all_students", "teacher", "student", ["image_generation"]) == "pending_review"
