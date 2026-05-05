"""Unit tests für die Gruppen-Sync-Logik."""
import pytest

from app.auth.config import SsoGroupPatterns
from app.auth.group_sync import (
    parse_sso_groups,
    _sso_id_to_slug,
    _derive_subject_slug,
    ParsedGroup,
)


# Test-Patterns
PATTERNS = SsoGroupPatterns(
    subject_department=r'^FS\.(.+)$',
    school_class=r'^Klasse\.(.+)$',
    teaching_group=r'^unterricht\.(.+)$',
)


# =============================================================================
# Tests für _sso_id_to_slug
# =============================================================================

def test_slug_normalisation():
    """SSO-IDs werden korrekt zu Slugs normalisiert."""
    assert _sso_id_to_slug("FS.Mathematik") == "fs-mathematik"
    assert _sso_id_to_slug("Klasse.8a") == "klasse-8a"
    assert _sso_id_to_slug("unterricht.8a.Mathematik") == "unterricht-8a-mathematik"
    assert _sso_id_to_slug("FS-Physik") == "fs-physik"


def test_slug_with_special_chars():
    """Spezialzeichen werden zu Bindestrichen."""
    assert _sso_id_to_slug("FS_Mathematik") == "fs-mathematik"
    assert _sso_id_to_slug("FS.Mathe!@#") == "fs-mathe"
    assert _sso_id_to_slug("---Klasse---8a---") == "klasse-8a"


# =============================================================================
# Tests für _derive_subject_slug
# =============================================================================

def test_derive_subject_slug_subject_department():
    """Fachname aus subject_department wird korrekt abgeleitet."""
    assert _derive_subject_slug("Mathematik") == "mathematik"
    assert _derive_subject_slug("Deutsch") == "deutsch"
    assert _derive_subject_slug("Physik") == "physik"


def test_derive_subject_slug_teaching_group():
    """Fachname aus teaching_group (letzter Teil) wird korrekt abgeleitet."""
    assert _derive_subject_slug("8a.Mathematik") == "mathematik"
    assert _derive_subject_slug("10b.Deutsch.Englisch") == "englisch"


def test_derive_subject_slug_school_class_returns_none():
    """Jahrgangscode ohne Fachname liefert None."""
    assert _derive_subject_slug("8a") is None
    assert _derive_subject_slug("10b") is None


def test_derive_subject_slug_lowercase_only():
    """Nur reine Kleinbuchstaben-Namen werden als Fach erkannt."""
    assert _derive_subject_slug("Mathe") == "mathe"
    assert _derive_subject_slug("8a") is None


# =============================================================================
# Tests für parse_sso_groups
# =============================================================================

def test_parse_subject_department():
    """subject_department-Gruppen werden korrekt geparst."""
    result = parse_sso_groups(["FS.Mathematik"], PATTERNS)
    assert len(result) == 1
    r = result[0]
    assert r.type == "subject_department"
    assert r.name == "Mathematik"
    assert r.slug == "fs-mathematik"
    assert r.subject_slug == "mathematik"
    assert r.sso_group_id == "FS.Mathematik"


def test_parse_school_class():
    """school_class-Gruppen werden korrekt geparst."""
    result = parse_sso_groups(["Klasse.8a"], PATTERNS)
    assert len(result) == 1
    r = result[0]
    assert r.type == "school_class"
    assert r.name == "8a"
    assert r.slug == "klasse-8a"
    assert r.subject_slug is None
    assert r.sso_group_id == "Klasse.8a"


def test_parse_teaching_group():
    """teaching_group-Gruppen werden korrekt geparst."""
    result = parse_sso_groups(["unterricht.8a.Mathematik"], PATTERNS)
    assert len(result) == 1
    r = result[0]
    assert r.type == "teaching_group"
    assert r.name == "8a Mathematik"
    assert r.slug == "unterricht-8a-mathematik"
    assert r.subject_slug == "mathematik"
    assert r.sso_group_id == "unterricht.8a.Mathematik"


def test_unknown_group_ignored():
    """Nicht-konfigurierte Gruppen werden ignoriert."""
    result = parse_sso_groups(["AG.Chor", "unbekannt"], PATTERNS)
    assert result == []


def test_mixed_groups():
    """Mehrere Gruppen werden alle korrekt geparst."""
    result = parse_sso_groups(
        ["FS.Mathematik", "Klasse.8a", "AG.Chor", "unterricht.8a.Mathematik"],
        PATTERNS,
    )
    assert len(result) == 3
    types = [r.type for r in result]
    assert "subject_department" in types
    assert "school_class" in types
    assert "teaching_group" in types


def test_empty_groups():
    """Leere Liste ergibt leere Ergebnis-Liste."""
    result = parse_sso_groups([], PATTERNS)
    assert result == []


def test_no_patterns_configured():
    """Ohne konfigurierte Muster werden alle Gruppen ignoriert."""
    result = parse_sso_groups(["FS.Mathematik"], SsoGroupPatterns())
    assert result == []


def test_multiple_groups_same_type():
    """Mehrere Gruppen desselben Typs werden alle geparst."""
    result = parse_sso_groups(
        ["FS.Mathematik", "FS.Physik", "FS.Chemie"],
        PATTERNS,
    )
    assert len(result) == 3
    names = [r.name for r in result]
    assert "Mathematik" in names
    assert "Physik" in names
    assert "Chemie" in names


def test_first_pattern_matches():
    """Erste passende Regel gilt (kein Fallthrough)."""
    # Wenn eine Gruppe zu mehreren Mustern passt, wird das erste verwendet
    patterns_first = SsoGroupPatterns(
        subject_department=r'^FS\.(.+)$',
        school_class=r'^FS\.(.+)$',  # Würde auch passen, aber erst später geprüft
        teaching_group=None,
    )
    result = parse_sso_groups(["FS.Mathematik"], patterns_first)
    assert len(result) == 1
    assert result[0].type == "subject_department"


# =============================================================================
# Tests für SsoGroupPatterns-Validierung
# =============================================================================

def test_invalid_regex_raises_error():
    """Ungültiges Regex in Pattern löst ValueError aus."""
    with pytest.raises(ValueError, match="ist kein gültiges Regex"):
        SsoGroupPatterns(subject_department="[invalid")


def test_no_capture_group_raises_error():
    """Pattern ohne Capture-Group löst ValueError aus."""
    with pytest.raises(ValueError, match="muss genau eine Capture-Group enthalten"):
        SsoGroupPatterns(subject_department=r"^FS\..+$")


def test_valid_patterns():
    """Gültige Pattern werden akzeptiert."""
    patterns = SsoGroupPatterns(
        subject_department=r"^FS\.(.+)$",
        school_class=r"^Klasse\.(.+)$",
        teaching_group=r"^unterricht\.(.+)$",
    )
    assert patterns is not None
