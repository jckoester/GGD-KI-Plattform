from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, text, TIMESTAMP, Text, ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Numeric, Boolean

import enum
from typing import Optional


class Base(DeclarativeBase):
    pass


# Enums for CHECK constraints
class AssistantStatus(enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class AssistantAudience(enum.Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ALL = "all"


class AssistantScope(enum.Enum):
    PRIVATE = "private"
    SUBJECT_DEPARTMENT = "subject_department"
    TEACHERS = "teachers"
    ACTIVITY_GROUP = "activity_group"
    TEACHING_GROUP = "teaching_group"
    GRADE = "grade"
    ALL_STUDENTS = "all_students"
    ALL = "all"


class MessageRole(enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ExchangeRateSource(enum.Enum):
    ECB = "ECB"
    MANUAL = "manual"


# 1. subjects
class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    min_grade: Mapped[Optional[int]] = mapped_column(nullable=True)
    max_grade: Mapped[Optional[int]] = mapped_column(nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)


# 2. groups
class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    sso_group_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_class_group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "type IN ('school_class','subject_department','teaching_group','activity_group','teachers')",
            name="check_groups_type",
        ),
        Index("idx_groups_type", "type"),
        Index("idx_groups_subject_id", "subject_id"),
        Index("idx_groups_source_class_group_id", "source_class_group_id"),
    )


# 2b. teacher_group_exclusions
class TeacherGroupExclusion(Base):
    __tablename__ = "teacher_group_exclusions"

    pseudonym: Mapped[str] = mapped_column(Text, primary_key=True)
    class_group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True
    )


# 3. group_memberships
class GroupMembership(Base):
    __tablename__ = "group_memberships"

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    pseudonym: Mapped[str] = mapped_column(Text, primary_key=True)
    role_in_group: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "role_in_group IS NULL OR role_in_group IN ('teacher','student')",
            name="check_group_memberships_role",
        ),
        Index("idx_group_memberships_pseudonym", "pseudonym"),
    )


# 4. assistants
class Assistant(Base):
    __tablename__ = "assistants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subject_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), nullable=True)
    max_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)

    status: Mapped[str] = mapped_column(default="draft", server_default=text("'draft'"))
    audience: Mapped[str] = mapped_column(default="student", server_default=text("'student'"))
    scope: Mapped[str] = mapped_column(default="private", server_default=text("'private'"))
    scope_pending: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope_group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )

    min_grade: Mapped[Optional[int]] = mapped_column(nullable=True)
    max_grade: Mapped[Optional[int]] = mapped_column(nullable=True)

    tags: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    import_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    force_cost_display: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    sort_order: Mapped[int] = mapped_column(default=0, server_default=text("0"))

    available_from:  Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    available_until: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    created_by_pseudonym: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_by_pseudonym: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','active','disabled','archived')",
            name="check_assistant_status",
        ),
        CheckConstraint(
            "audience IN ('student','teacher','all')",
            name="check_assistant_audience",
        ),
        CheckConstraint(
            "scope IN ('private','subject_department','teachers','activity_group',"
            "          'teaching_group','grade','all_students','all')",
            name="check_assistant_scope",
        ),
        CheckConstraint(
            "scope_pending IS NULL OR scope_pending IN "
            "('private','subject_department','teachers','activity_group',"
            " 'teaching_group','grade','all_students','all')",
            name="check_assistant_scope_pending",
        ),
        Index("idx_assistants_status", "status"),
        Index("idx_assistants_subject_id", "subject_id"),
    )


# 5. conversations
class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    pseudonym: Mapped[str] = mapped_column(nullable=False)
    subject_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL")
    )
    group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL")
    )
    assistant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("assistants.id", ondelete="SET NULL")
    )
    system_prompt_snapshot: Mapped[Optional[str]] = mapped_column(nullable=True)
    total_cost_usd: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 6), default=0, server_default=text("0")
    )
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    title: Mapped[Optional[str]] = mapped_column(nullable=True)
    model_used: Mapped[str] = mapped_column(nullable=False)
    is_test: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        Index("idx_conversations_pseudonym", "pseudonym"),
        Index("idx_conversations_last_message_at", "last_message_at"),
    )


# 6. messages
class Message(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False
    )
    role: Mapped[str] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(nullable=False)
    model: Mapped[Optional[str]] = mapped_column(nullable=True)
    # cost/token fields - nullable, only for assistant
    cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    tokens_input: Mapped[Optional[int]] = mapped_column(nullable=True)
    tokens_output: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="check_message_role"
        ),
        Index("idx_messages_conversation_id", "conversation_id"),
    )


# 7. user_preferences
class UserPreference(Base):
    __tablename__ = "user_preferences"

    pseudonym: Mapped[str] = mapped_column(primary_key=True)
    preferences: Mapped[dict] = mapped_column(
        JSONB, default={}, server_default=text("'{}'")
    )


# 8. pseudonym_audit
class PseudonymAudit(Base):
    __tablename__ = "pseudonym_audit"

    pseudonym: Mapped[str] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(nullable=False)
    grade: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    last_login_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    revoked_all_before: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    litellm_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# 9. jwt_revocations
class JwtRevocation(Base):
    __tablename__ = "jwt_revocations"

    jti: Mapped[str] = mapped_column(primary_key=True)
    pseudonym: Mapped[str] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    reason: Mapped[Optional[str]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        Index("idx_jwt_revocations_pseudonym", "pseudonym"),
        Index("idx_jwt_revocations_expires_at", "expires_at"),
    )


# 10. exchange_rates
class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    eur_usd_rate: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    source: Mapped[str] = mapped_column(nullable=False)
    effective_from: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        Index("idx_exchange_rates_effective_from", "effective_from"),
        CheckConstraint(
            "source IN ('ECB', 'manual')",
            name="check_exchange_rate_source"
        ),
    )


# 11. site_texts
class SiteText(Base):
    __tablename__ = "site_texts"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False,
        server_default=text("now()"),
        onupdate=text("now()")
    )
