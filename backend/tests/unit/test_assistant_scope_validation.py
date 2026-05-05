"""Tests für Assistenten-Scope-Validierung nach der class_group → teaching_group Umbenennung."""
import pytest
from fastapi import HTTPException

from app.api.admin.assistants import (
    VALID_SCOPES,
    GROUP_SCOPES,
    _validate_assistant_fields,
)


# ── VALID_SCOPES / GROUP_SCOPES Konstanten ─────────────────────────────────────

def test_teaching_group_in_valid_scopes():
    assert "teaching_group" in VALID_SCOPES


def test_class_group_not_in_valid_scopes():
    assert "class_group" not in VALID_SCOPES


def test_teaching_group_in_group_scopes():
    assert "teaching_group" in GROUP_SCOPES


def test_subject_department_in_group_scopes():
    assert "subject_department" in GROUP_SCOPES


def test_activity_group_in_group_scopes():
    assert "activity_group" in GROUP_SCOPES


# ── _validate_assistant_fields: ungültige Scopes ──────────────────────────────

def test_class_group_scope_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_assistant_fields(scope="class_group")
    assert exc.value.status_code == 422
    assert "scope" in exc.value.detail.lower()


def test_unknown_scope_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_assistant_fields(scope="nonexistent")
    assert exc.value.status_code == 422


# ── _validate_assistant_fields: Gruppen-Scope ohne scope_group_id ─────────────

@pytest.mark.parametrize("scope", ["teaching_group", "subject_department", "activity_group"])
def test_group_scope_without_scope_group_id_raises(scope):
    with pytest.raises(HTTPException) as exc:
        _validate_assistant_fields(scope=scope, scope_group_id=None)
    assert exc.value.status_code == 422
    assert "scope_group_id" in exc.value.detail


# ── _validate_assistant_fields: scope_group_id bei Nicht-Gruppen-Scope ────────

@pytest.mark.parametrize("scope", ["private", "teachers", "grade", "all_students", "all"])
def test_non_group_scope_with_scope_group_id_raises(scope):
    with pytest.raises(HTTPException) as exc:
        _validate_assistant_fields(scope=scope, scope_group_id=42)
    assert exc.value.status_code == 422
    assert "scope_group_id" in exc.value.detail


# ── _validate_assistant_fields: korrekte Kombinationen ───────────────────────

@pytest.mark.parametrize("scope", ["teaching_group", "subject_department", "activity_group"])
def test_group_scope_with_scope_group_id_valid(scope):
    _validate_assistant_fields(scope=scope, scope_group_id=1)  # darf nicht werfen


@pytest.mark.parametrize("scope", ["private", "teachers", "grade", "all_students", "all"])
def test_non_group_scope_without_scope_group_id_valid(scope):
    _validate_assistant_fields(scope=scope, scope_group_id=None)  # darf nicht werfen
