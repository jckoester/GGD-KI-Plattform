"""Schema smoke tests for the database."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    Assistant,
    Conversation,
    ExchangeRate,
    JwtRevocation,
    Message,
    PseudonymAudit,
    Subject,
    UserPreference,
)


TABLE_MODELS = [
    Subject,
    Assistant,
    Conversation,
    Message,
    UserPreference,
    PseudonymAudit,
    JwtRevocation,
    ExchangeRate,
]


@pytest.mark.asyncio
async def test_all_tables_exist(db_session):
    """Test that all expected tables exist after migration."""
    for model in TABLE_MODELS:
        table_name = model.__tablename__
        result = await db_session.execute(
            text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')")
        )
        exists = result.scalar()
        assert exists, f"Table {table_name} does not exist"


@pytest.mark.asyncio
async def test_subject_crud(db_session):
    """Test CRUD roundtrip for Subject (within a rolled-back transaction)."""
    subject = Subject(slug="test-subject-schema", name="Test Fach", min_grade=5, max_grade=10, sort_order=99)
    db_session.add(subject)
    await db_session.flush()
    await db_session.refresh(subject)

    assert subject.id is not None
    assert subject.slug == "test-subject-schema"
    assert subject.min_grade == 5

    subject.slug = "updated-subject-schema"
    await db_session.flush()
    await db_session.refresh(subject)
    assert subject.slug == "updated-subject-schema"

    await db_session.delete(subject)
    await db_session.flush()

    result = await db_session.get(Subject, subject.id)
    assert result is None


@pytest.mark.asyncio
async def test_cascade_delete_conversation(db_session):
    """Test that deleting a Conversation cascades to Messages."""
    conversation = Conversation(
        pseudonym="schema-test-pseudo",
        system_prompt_snapshot="test prompt",
        total_cost_usd=0.0,
        model_used="gpt-4o",
    )
    db_session.add(conversation)
    await db_session.flush()
    await db_session.refresh(conversation)

    message1 = Message(conversation_id=conversation.id, role="user", content="Hello")
    message2 = Message(
        conversation_id=conversation.id,
        role="assistant",
        content="Hi there",
        cost_usd=0.1,
        tokens_input=10,
        tokens_output=20,
    )
    db_session.add_all([message1, message2])
    await db_session.flush()

    result = await db_session.execute(
        text("SELECT COUNT(*) FROM messages WHERE conversation_id = :conv_id").bindparams(conv_id=conversation.id)
    )
    assert result.scalar() == 2

    await db_session.delete(conversation)
    await db_session.flush()

    result = await db_session.execute(
        text("SELECT COUNT(*) FROM messages WHERE conversation_id = :conv_id").bindparams(conv_id=conversation.id)
    )
    assert result.scalar() == 0


@pytest.mark.asyncio
async def test_assistant_status_check_constraint(db_session):
    """Test CHECK constraint on assistants.status."""
    with pytest.raises((IntegrityError, Exception)):
        assistant = Assistant(
            subject_id=None,
            status="invalid_status",
            created_by="test-pseudo",
        )
        db_session.add(assistant)
        await db_session.flush()


@pytest.mark.asyncio
async def test_message_role_check_constraint(db_session):
    """Test CHECK constraint on messages.role."""
    conversation = Conversation(
        pseudonym="schema-test-pseudo-2",
        system_prompt_snapshot="test",
        total_cost_usd=0.0,
        model_used="gpt-4o",
    )
    db_session.add(conversation)
    await db_session.flush()
    await db_session.refresh(conversation)

    with pytest.raises((IntegrityError, Exception)):
        message = Message(
            conversation_id=conversation.id,
            role="invalid_role",
            content="test",
        )
        db_session.add(message)
        await db_session.flush()
