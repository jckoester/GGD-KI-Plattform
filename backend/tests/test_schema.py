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


# List of all 8 table models
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
    """Test that all 8 tables exist after migration."""
    for model in TABLE_MODELS:
        table_name = model.__tablename__
        result = await db_session.execute(
            text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')")
        )
        exists = result.scalar()
        assert exists, f"Table {table_name} does not exist"


@pytest.mark.asyncio
async def test_subject_crud(db_session):
    """Test CRUD roundtrip for Subject."""
    # Create
    subject = Subject(slug="test-subject", min_grade=5, max_grade=10, sort_order=1)
    db_session.add(subject)
    await db_session.commit()
    await db_session.refresh(subject)
    
    # Read
    result = await db_session.get(Subject, subject.id)
    assert result is not None
    assert result.slug == "test-subject"
    assert result.min_grade == 5
    assert result.max_grade == 10
    
    # Update
    result.slug = "updated-subject"
    await db_session.commit()
    await db_session.refresh(result)
    assert result.slug == "updated-subject"
    
    # Delete
    await db_session.delete(result)
    await db_session.commit()
    
    # Verify deletion
    result = await db_session.get(Subject, subject.id)
    assert result is None


@pytest.mark.asyncio
async def test_cascade_delete_conversation(db_session):
    """Test that deleting a Conversation cascades to Messages."""
    # Create conversation
    conversation = Conversation(
        pseudonym="test-pseudo",
        system_prompt_snapshot="test prompt",
        total_cost_usd=0.0,
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    
    # Create messages
    message1 = Message(
        conversation_id=conversation.id,
        role="user",
        content="Hello",
    )
    message2 = Message(
        conversation_id=conversation.id,
        role="assistant",
        content="Hi there",
        cost_usd=0.1,
        input_tokens=10,
        output_tokens=20,
    )
    db_session.add_all([message1, message2])
    await db_session.commit()
    
    # Verify messages exist
    result = await db_session.execute(
        text("SELECT COUNT(*) FROM messages WHERE conversation_id = :conv_id")
        .bindparams(conv_id=conversation.id)
    )
    count = result.scalar()
    assert count == 2
    
    # Delete conversation (should cascade to messages)
    await db_session.delete(conversation)
    await db_session.commit()
    
    # Verify messages are gone
    result = await db_session.execute(
        text("SELECT COUNT(*) FROM messages WHERE conversation_id = :conv_id")
        .bindparams(conv_id=conversation.id)
    )
    count = result.scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_assistant_status_check_constraint(db_session):
    """Test CHECK constraint on assistants.status."""
    # Try to create assistant with invalid status
    with pytest.raises(IntegrityError):
        assistant = Assistant(
            subject_id=None,
            status="invalid_status",
            created_by_pseudonym="test-pseudo",
        )
        db_session.add(assistant)
        await db_session.commit()


@pytest.mark.asyncio
async def test_message_role_check_constraint(db_session):
    """Test CHECK constraint on messages.role."""
    # First create a conversation to reference
    conversation = Conversation(
        pseudonym="test-pseudo",
        system_prompt_snapshot="test",
        total_cost_usd=0.0,
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    
    # Try to create message with invalid role
    with pytest.raises(IntegrityError):
        message = Message(
            conversation_id=conversation.id,
            role="invalid_role",
            content="test",
        )
        db_session.add(message)
        await db_session.commit()
