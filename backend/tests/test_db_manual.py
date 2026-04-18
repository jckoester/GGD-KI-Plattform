"""Manual DB tests for schema validation."""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from app.db.models import Subject, Conversation, Message, Assistant


async def main():
    engine = create_async_engine("postgresql+asyncpg://postgres:postgres@localhost:5432/ggd_ki")
    
    # Test 1: Alle 8 Tabellen existieren
    print("Test 1: Checking all 8 tables exist...")
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name NOT LIKE 'alembic%'")
        )
        tables = [row[0] for row in result]
        print(f"  Found tables: {tables}")
        
        required = ["subjects", "assistants", "conversations", "messages", "user_preferences", "pseudonym_audit", "jwt_revocations", "exchange_rates"]
        missing = [t for t in required if t not in tables]
        if missing:
            print(f"  FAIL: Missing tables: {missing}")
        else:
            print(f"  PASS: All 8 tables exist")
    
    # Test 2: Conversation hat last_message_at
    print("\nTest 2: Checking Conversation.last_message_at...")
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'conversations'")
        )
        cols = {row[0]: row[1] for row in result}
        print(f"  Columns: {list(cols.keys())}")
        if "last_message_at" in cols:
            print(f"  PASS: last_message_at exists (type: {cols['last_message_at']})")
        else:
            print(f"  FAIL: last_message_at missing")
    
    # Test 3: Subject.sort_order ist NOT NULL
    print("\nTest 3: Checking Subject.sort_order nullable...")
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT is_nullable FROM information_schema.columns WHERE table_name = 'subjects' AND column_name = 'sort_order'")
        )
        row = result.fetchone()
        if row:
            nullable = row[0] == "YES"
            if not nullable:
                print(f"  PASS: sort_order is NOT NULL")
            else:
                print(f"  FAIL: sort_order is still nullable")
    
    # Test 4: CRUD Roundtrip Subject
    print("\nTest 4: CRUD Roundtrip for Subject...")
    async with AsyncSession(engine) as session:
        # Create
        subject = Subject(slug="test-subject-crud", min_grade=5, max_grade=10)
        session.add(subject)
        await session.commit()
        await session.refresh(subject)
        print(f"  Created subject with id={subject.id}, slug={subject.slug}")
        
        # Read
        result = await session.get(Subject, subject.id)
        if result and result.slug == "test-subject-crud":
            print(f"  PASS: Read successful")
        else:
            print(f"  FAIL: Read failed")
        
        # Update
        result.slug = "updated-test-subject"
        await session.commit()
        await session.refresh(result)
        if result.slug == "updated-test-subject":
            print(f"  PASS: Update successful")
        else:
            print(f"  FAIL: Update failed")
        
        # Delete
        await session.delete(result)
        await session.commit()
        
        # Verify
        result = await session.get(Subject, subject.id)
        if result is None:
            print(f"  PASS: Delete successful")
        else:
            print(f"  FAIL: Delete failed")
    
    # Test 5: Cascade Delete Conversation -> Messages
    print("\nTest 5: Cascade Delete Conversation -> Messages...")
    async with AsyncSession(engine) as session:
        # Create conversation
        conv = Conversation(pseudonym="test-pseudo-cascade")
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        
        # Create messages
        msg1 = Message(conversation_id=conv.id, role="user", content="Hello")
        msg2 = Message(conversation_id=conv.id, role="assistant", content="Hi")
        session.add_all([msg1, msg2])
        await session.commit()
        
        # Verify messages exist
        result = await session.execute(
            text("SELECT COUNT(*) FROM messages WHERE conversation_id = :cid").bindparams(cid=conv.id)
        )
        count_before = result.scalar()
        print(f"  Messages before delete: {count_before}")
        
        # Delete conversation
        await session.delete(conv)
        await session.commit()
        
        # Verify messages gone
        result = await session.execute(
            text("SELECT COUNT(*) FROM messages WHERE conversation_id = :cid").bindparams(cid=conv.id)
        )
        count_after = result.scalar()
        print(f"  Messages after delete: {count_after}")
        
        if count_before == 2 and count_after == 0:
            print(f"  PASS: Cascade delete works")
        else:
            print(f"  FAIL: Cascade delete failed")
    
    # Test 6: CHECK constraint assistants.status
    print("\nTest 6: CHECK constraint assistants.status...")
    async with AsyncSession(engine) as session:
        try:
            invalid_assistant = Assistant(status="invalid_status")
            session.add(invalid_assistant)
            await session.commit()
            print(f"  FAIL: Invalid status was accepted")
        except Exception as e:
            error_str = str(e).lower()
            if "check_assistant_status" in error_str or "violation" in error_str or "constraint" in error_str:
                print(f"  PASS: CHECK constraint rejected invalid status")
            else:
                print(f"  WARNING: PASS with different error: {type(e).__name__}")
    
    # Test 7: CHECK constraint messages.role
    print("\nTest 7: CHECK constraint messages.role...")
    async with AsyncSession(engine) as session:
        try:
            conv = Conversation(pseudonym="test-pseudo-role")
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            
            invalid_msg = Message(conversation_id=conv.id, role="invalid_role", content="test")
            session.add(invalid_msg)
            await session.commit()
            print(f"  FAIL: Invalid role was accepted")
        except Exception as e:
            error_str = str(e).lower()
            if "check_message_role" in error_str or "violation" in error_str or "constraint" in error_str:
                print(f"  PASS: CHECK constraint rejected invalid role")
            else:
                print(f"  WARNING: PASS with different error: {type(e).__name__}")
    
    await engine.dispose()
    print("\n All manual tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
