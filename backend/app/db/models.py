from datetime import datetime, date
from uuid import UUID, UUID as UUIDType

from sqlalchemy import CheckConstraint, ForeignKey, Index, text, TIMESTAMP, Text, ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Numeric, Boolean
from pgvector.sqlalchemy import Vector

import enum
from typing import Optional


class Base(DeclarativeBase):
    pass


# Enums for CHECK constraints
class AssistantStatus(enum.Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
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


class AssistantVisibility(enum.Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    HIDDEN = "hidden"


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
    # Bildungsplan-Fachkürzel (z. B. 'M', 'CH'); aus config/subjects.yaml geseedet.
    # Nullable: nicht jedes Fach hat einen Bildungsplan-Code (z. B. Deutsch).
    fach_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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

    visibility: Mapped[str] = mapped_column(
        Text, default="public", server_default=text("'public'")
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

    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_by_pseudonym: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    creator_role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'admin'")
    )
    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','pending_review','active','disabled','archived')",
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
        CheckConstraint(
            "visibility IN ('public','private','hidden')",
            name="check_assistant_visibility",
        ),
        CheckConstraint(
            "creator_role IN ('admin', 'teacher')",
            name="check_assistant_creator_role",
        ),
        Index("idx_assistants_status", "status"),
        Index("idx_assistants_subject_id", "subject_id"),
    )


# 4b. assistant_documents
class AssistantDocument(Base):
    __tablename__ = "assistant_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    assistant_id: Mapped[int] = mapped_column(
        ForeignKey("assistants.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        Index("idx_assistant_documents_assistant_id", "assistant_id"),
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
    # Ab Phase 8: aktuell aktiver Assistent (wird bei Wechsel mid-Chat aktualisiert)
    assistant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("assistants.id", ondelete="SET NULL")
    )
    # Ab Phase 8: Snapshot beim letzten Assistentenwechsel (nicht nur beim Start)
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
    assistant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("assistants.id", ondelete="SET NULL"), nullable=True
    )
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
        Index("idx_messages_assistant_id", "assistant_id"),
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


# 11. site_config
class SiteConfig(Base):
    __tablename__ = "site_config"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False,
        server_default=text("now()")
    )
    updated_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# 12. context_nodes
class ContextNode(Base):
    __tablename__ = "context_nodes"

    id: Mapped[UUIDType] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'")
    )
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)

    owner_pseudonym: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    read_scope: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'school'")
    )
    write_scope: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'private'")
    )
    read_scope_group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )
    write_scope_group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )
    assistant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("assistants.id", ondelete="SET NULL"), nullable=True
    )
    subject_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True
    )
    min_grade: Mapped[Optional[int]] = mapped_column(nullable=True)
    max_grade: Mapped[Optional[int]] = mapped_column(nullable=True)
    niveau: Mapped[str] = mapped_column(server_default="regulär")

    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'active'")
    )
    valid_until: Mapped[Optional[date]] = mapped_column(nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    schuljahr: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "category IN ('document','knowledge','artifact','concept')",
            name="check_context_nodes_category",
        ),
        CheckConstraint(
            "read_scope IN ('global','school','subject','group','private')",
            name="check_context_nodes_read_scope",
        ),
        CheckConstraint(
            "write_scope IN ('global','school','subject','group','private')",
            name="check_context_nodes_write_scope",
        ),
        CheckConstraint(
            "status IN ('active','archived','deleted')",
            name="check_context_nodes_status",
        ),
        CheckConstraint(
            "read_scope NOT IN ('subject','group') OR read_scope_group_id IS NOT NULL",
            name="check_context_nodes_read_group_id",
        ),
        CheckConstraint(
            "write_scope NOT IN ('subject','group') OR write_scope_group_id IS NOT NULL",
            name="check_context_nodes_write_group_id",
        ),
        CheckConstraint(
            """
            CASE write_scope
              WHEN 'private' THEN 0 WHEN 'group'   THEN 1 WHEN 'subject' THEN 2
              WHEN 'school'  THEN 3 WHEN 'global'  THEN 4
            END
            <=
            CASE read_scope
              WHEN 'private' THEN 0 WHEN 'group'   THEN 1 WHEN 'subject' THEN 2
              WHEN 'school'  THEN 3 WHEN 'global'  THEN 4
            END
            """,
            name="check_context_nodes_scope_restrictivity",
        ),
        Index("idx_context_nodes_cat_type", "category", "content_type"),
        Index("idx_context_nodes_read", "read_scope", "read_scope_group_id"),
        Index(
            "idx_context_nodes_owner", "owner_pseudonym",
            postgresql_where=text("owner_pseudonym IS NOT NULL"),
        ),
        Index(
            "idx_context_nodes_assistant", "assistant_id",
            postgresql_where=text("assistant_id IS NOT NULL"),
        ),
        Index("idx_context_nodes_status", "status"),
        Index(
            "idx_context_nodes_valid_until", "valid_until",
            postgresql_where=text("valid_until IS NOT NULL"),
        ),
        Index(
            "idx_context_nodes_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=text("embedding IS NOT NULL"),
        ),
    )


# 13. context_edges
class ContextEdge(Base):
    __tablename__ = "context_edges"

    id: Mapped[UUIDType] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    from_node_id: Mapped[UUIDType] = mapped_column(
        ForeignKey("context_nodes.id", ondelete="CASCADE"), nullable=False
    )
    to_node_id: Mapped[UUIDType] = mapped_column(
        ForeignKey("context_nodes.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "relation IN ('requires','used_with','part_of','develops',"
            "             'supersedes','references','follows','reflects_on','derived_from',"
            "             'related_to')",
            name="check_context_edges_relation",
        ),
        Index("idx_context_edges_from", "from_node_id"),
        Index("idx_context_edges_to", "to_node_id"),
        Index("idx_context_edges_relation", "relation"),
        Index(
            "idx_context_edges_unique",
            "from_node_id", "to_node_id", "relation",
            unique=True,
        ),
    )


# 14. node_engagement
class NodeEngagement(Base):
    __tablename__ = "node_engagement"

    id: Mapped[UUIDType] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    pseudonym: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=True
    )
    node_id: Mapped[UUIDType] = mapped_column(
        ForeignKey("context_nodes.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "relation IN ('introduced','knows','mastered','struggles_with')",
            name="check_node_engagement_relation",
        ),
        CheckConstraint(
            "(pseudonym IS NOT NULL) <> (group_id IS NOT NULL)",
            name="check_node_engagement_subject_xor",
        ),
        CheckConstraint(
            "group_id IS NULL OR relation = 'introduced'",
            name="check_node_engagement_group_relation",
        ),
        Index(
            "idx_engagement_pseudonym", "pseudonym",
            postgresql_where=text("pseudonym IS NOT NULL"),
        ),
        Index(
            "idx_engagement_group", "group_id",
            postgresql_where=text("group_id IS NOT NULL"),
        ),
        Index("idx_engagement_node", "node_id"),
        Index(
            "idx_engagement_unique_user",
            "pseudonym", "node_id", "relation",
            unique=True,
            postgresql_where=text("pseudonym IS NOT NULL"),
        ),
        Index(
            "idx_engagement_unique_group",
            "group_id", "node_id", "relation",
            unique=True,
            postgresql_where=text("group_id IS NOT NULL"),
        ),
    )


# 15. assistant_context_anchors
class AssistantContextAnchor(Base):
    __tablename__ = "assistant_context_anchors"

    assistant_id: Mapped[int] = mapped_column(
        ForeignKey("assistants.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[UUIDType] = mapped_column(
        ForeignKey("context_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, primary_key=True)

    __table_args__ = (
        CheckConstraint(
            "role IN ('always_include','retrieval_scope')",
            name="check_assistant_context_anchors_role",
        ),
    )


# 16. chat_context_nodes
class ChatContextNode(Base):
    __tablename__ = "chat_context_nodes"

    chat_id: Mapped[UUIDType] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[UUIDType] = mapped_column(
        ForeignKey("context_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
