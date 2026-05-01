"""Unit tests for Assistant model - testing model definition without DB."""
import pytest
from sqlalchemy import CheckConstraint, Index
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.db.models import Assistant, AssistantAudience, AssistantScope


class TestAssistantEnums:
    def test_assistant_audience_values(self):
        """AssistantAudience hat die korrekten Werte."""
        assert AssistantAudience.STUDENT.value == "student"
        assert AssistantAudience.TEACHER.value == "teacher"
        assert AssistantAudience.ALL.value == "all"

    def test_assistant_scope_values(self):
        """AssistantScope hat die korrekten Werte."""
        assert AssistantScope.PRIVATE.value == "private"
        assert AssistantScope.SUBJECT_DEPARTMENT.value == "subject_department"
        assert AssistantScope.TEACHERS.value == "teachers"
        assert AssistantScope.ACTIVITY_GROUP.value == "activity_group"
        assert AssistantScope.CLASS_GROUP.value == "class_group"
        assert AssistantScope.GRADE.value == "grade"
        assert AssistantScope.ALL_STUDENTS.value == "all_students"
        assert AssistantScope.ALL.value == "all"


class TestAssistantModel:
    def test_assistant_has_all_required_columns(self):
        """Assistant hat alle benoetigten Spalten."""
        # Pflichtfelder
        assert hasattr(Assistant, 'id')
        assert hasattr(Assistant, 'name')
        assert hasattr(Assistant, 'system_prompt')
        assert hasattr(Assistant, 'model')
        
        # Optionale Config-Felder
        assert hasattr(Assistant, 'description')
        assert hasattr(Assistant, 'temperature')
        assert hasattr(Assistant, 'max_tokens')
        
        # Sichtbarkeitsmodell
        assert hasattr(Assistant, 'audience')
        assert hasattr(Assistant, 'scope')
        assert hasattr(Assistant, 'scope_pending')
        assert hasattr(Assistant, 'scope_group_id')
        
        # Jahrgangseingrenzung
        assert hasattr(Assistant, 'min_grade')
        assert hasattr(Assistant, 'max_grade')
        
        # UI / Marktplatz
        assert hasattr(Assistant, 'tags')
        assert hasattr(Assistant, 'icon')
        assert hasattr(Assistant, 'import_metadata')
        
        # Sortierung & Audit
        assert hasattr(Assistant, 'sort_order')
        assert hasattr(Assistant, 'created_by_pseudonym')
        assert hasattr(Assistant, 'updated_by_pseudonym')
        assert hasattr(Assistant, 'created_at')
        assert hasattr(Assistant, 'updated_at')
        
        # Bestehende Felder
        assert hasattr(Assistant, 'subject_id')
        assert hasattr(Assistant, 'status')
        assert hasattr(Assistant, 'force_cost_display')

    def test_assistant_table_args_has_check_constraints(self):
        """Assistant __table_args__ enthält alle CHECK-Constraints."""
        table_args = Assistant.__table_args__
        constraint_names = [c.name for c in table_args if isinstance(c, CheckConstraint)]
        
        assert "check_assistant_status" in constraint_names
        assert "check_assistant_audience" in constraint_names
        assert "check_assistant_scope" in constraint_names
        assert "check_assistant_scope_pending" in constraint_names

    def test_assistant_table_args_has_indexes(self):
        """Assistant __table_args__ enthält alle Indizes."""
        table_args = Assistant.__table_args__
        index_names = [idx.name for idx in table_args if isinstance(idx, Index)]
        
        assert "idx_assistants_status" in index_names
        assert "idx_assistants_subject_id" in index_names

    def test_tags_column_type_is_array(self):
        """tags Spalte ist vom Typ ARRAY(Text)."""
        from sqlalchemy import inspect
        from sqlalchemy.sql.sqltypes import ARRAY as SQL_ARRAY
        mapper = inspect(Assistant)
        tags_col = mapper.columns['tags']
        # ARRAY(Text()) ist eine Instanz von ARRAY
        assert isinstance(tags_col.type, SQL_ARRAY)

    def test_import_metadata_column_type_is_jsonb(self):
        """import_metadata Spalte ist vom Typ JSONB."""
        from sqlalchemy import inspect
        mapper = inspect(Assistant)
        import_meta_col = mapper.columns['import_metadata']
        assert isinstance(import_meta_col.type, JSONB)
