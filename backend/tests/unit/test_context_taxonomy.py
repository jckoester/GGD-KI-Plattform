"""Unit-Tests für app.context.taxonomy."""

import pytest

from app.context.taxonomy import (
    VALID_CONTENT_TYPES,
    validate_content_type,
    get_valid_until_offset,
    get_scope_defaults,
)


# ── validate_content_type ─────────────────────────────────────────────────────

class TestValidateContentType:

    def test_valid_document_types(self):
        for ct in VALID_CONTENT_TYPES["document"]:
            validate_content_type("document", ct)  # kein Fehler

    def test_valid_knowledge_types(self):
        for ct in VALID_CONTENT_TYPES["knowledge"]:
            validate_content_type("knowledge", ct)

    def test_valid_artifact_types(self):
        for ct in VALID_CONTENT_TYPES["artifact"]:
            validate_content_type("artifact", ct)

    def test_valid_concept_types(self):
        for ct in VALID_CONTENT_TYPES["concept"]:
            validate_content_type("concept", ct)

    def test_none_content_type_always_valid(self):
        for cat in ("document", "knowledge", "artifact", "concept"):
            validate_content_type(cat, None)  # kein Fehler

    def test_cross_category_raises(self):
        # knowledge-Type in document-category
        with pytest.raises(ValueError, match="fachplan"):
            validate_content_type("document", "fachplan")

    def test_cross_category_raises_artifact_in_knowledge(self):
        with pytest.raises(ValueError, match="unterrichtsentwurf"):
            validate_content_type("knowledge", "unterrichtsentwurf")

    def test_cross_category_raises_concept_in_artifact(self):
        with pytest.raises(ValueError, match="funktion"):
            validate_content_type("artifact", "funktion")

    def test_unknown_category_raises(self):
        with pytest.raises(ValueError, match="Unbekannte category"):
            validate_content_type("invalid_cat", "something")

    def test_unknown_content_type_raises(self):
        with pytest.raises(ValueError):
            validate_content_type("document", "nonexistent_type")

    def test_error_message_contains_allowed_types(self):
        with pytest.raises(ValueError) as exc_info:
            validate_content_type("concept", "funktion_x")
        assert "Erlaubt:" in str(exc_info.value)


# ── get_valid_until_offset ────────────────────────────────────────────────────

class TestGetValidUntilOffset:

    def test_permanent_types_return_none(self):
        permanent = ["fachplan", "ik_kompetenz", "aufgabe", "arbeitsblatt", "funktion"]
        for ct in permanent:
            assert get_valid_until_offset(ct) is None

    def test_temporary_types_return_days(self):
        temporary = ["lernplan", "gliederung", "mindmap", "schuelertext", "feedback_text"]
        for ct in temporary:
            offset = get_valid_until_offset(ct)
            assert isinstance(offset, int) and offset > 0

    def test_none_content_type_returns_none(self):
        assert get_valid_until_offset(None) is None

    def test_unknown_content_type_returns_none(self):
        assert get_valid_until_offset("unbekannt") is None


# ── get_scope_defaults ────────────────────────────────────────────────────────

class TestGetScopeDefaults:

    def test_global_types(self):
        for ct in ("fachplan", "ik_kompetenz", "pk_kompetenz", "leitidee"):
            read, write = get_scope_defaults(ct)
            assert read == "global" and write == "global"

    def test_school_subject_curriculum(self):
        read, write = get_scope_defaults("curriculum")
        assert read == "school" and write == "subject"

    def test_private_artifacts(self):
        for ct in ("klausur", "unterrichtsstunde", "lernplan"):
            read, write = get_scope_defaults(ct)
            assert read == "private" and write == "private"

    def test_none_returns_fallback(self):
        read, write = get_scope_defaults(None)
        assert read == "school" and write == "private"

    def test_unknown_returns_fallback(self):
        read, write = get_scope_defaults("completely_unknown")
        assert read == "school" and write == "private"

    def test_scope_restrictivity_invariant(self):
        """write_scope darf nie permissiver sein als read_scope."""
        scope_order = {"private": 0, "group": 1, "subject": 2, "school": 3, "global": 4}
        for ct in list(VALID_CONTENT_TYPES["document"]) + \
                  list(VALID_CONTENT_TYPES["knowledge"]) + \
                  list(VALID_CONTENT_TYPES["artifact"]) + \
                  list(VALID_CONTENT_TYPES["concept"]):
            read, write = get_scope_defaults(ct)
            assert scope_order[write] <= scope_order[read], (
                f"{ct}: write_scope={write!r} ist permissiver als read_scope={read!r}"
            )
