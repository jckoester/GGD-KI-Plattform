"""Simple DB tests."""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


async def main():
    engine = create_async_engine("postgresql+asyncpg://postgres:postgres@localhost:5432/ggd_ki")
    
    print("=" * 60)
    print("DATABASE SCHEMA VALIDATION TEST")
    print("=" * 60)
    
    # Test 1: Alle 8 Tabellen existieren
    print("\n[Test 1] Alle 8 Tabellen existieren")
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name NOT LIKE 'alembic%'")
        )
        tables = [row[0] for row in result]
        required = ["subjects", "assistants", "conversations", "messages", "user_preferences", "pseudonym_audit", "jwt_revocations", "exchange_rates"]
        missing = [t for t in required if t not in tables]
        if missing:
            print(f"  FAIL: Fehlende Tabellen: {missing}")
        else:
            print(f"  PASS: Alle 8 Tabellen existieren: {tables}")
    
    # Test 2: Conversation.last_message_at
    print("\n[Test 2] Conversation.last_message_at Spalte")
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'conversations'")
        )
        cols = [row[0] for row in result]
        if "last_message_at" in cols:
            print(f"  PASS: last_message_at existiert")
        else:
            print(f"  FAIL: last_message_at fehlt")
    
    # Test 3: Subject.sort_order NOT NULL
    print("\n[Test 3] Subject.sort_order ist NOT NULL")
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT is_nullable FROM information_schema.columns WHERE table_name = 'subjects' AND column_name = 'sort_order'")
        )
        row = result.fetchone()
        if row and row[0] == "NO":
            print(f"  PASS: sort_order ist NOT NULL")
        else:
            print(f"  FAIL: sort_order ist nullable")
    
    # Test 4: Indizes
    print("\n[Test 4] Indizes existieren")
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename NOT LIKE 'alembic%'")
        )
        indexes = [row[0] for row in result]
        required_indexes = ["idx_conversations_pseudonym", "idx_conversations_last_message_at", 
                           "idx_messages_conversation_id", "idx_jwt_revocations_pseudonym", 
                           "idx_jwt_revocations_expires_at", "idx_exchange_rates_effective_from"]
        missing_idx = [i for i in required_indexes if i not in indexes]
        if missing_idx:
            print(f"  FAIL: Fehlende Indizes: {missing_idx}")
            print(f"  Vorhandene Indizes: {indexes}")
        else:
            print(f"  PASS: Alle Indizes existieren")
    
    # Test 5: CHECK Constraints
    print("\n[Test 5] CHECK Constraints")
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT conname FROM pg_constraint WHERE conrelid = 'subjects'::regclass")
        )
        # Actually better way:
        result = await conn.execute(
            text("""SELECT tc.table_name, tc.constraint_name 
                   FROM information_schema.table_constraints tc 
                   JOIN information_schema.check_constraints cc ON tc.constraint_name = cc.constraint_name
                   WHERE tc.constraint_type = 'CHECK'""")
        )
        constraints = {row[0]: row[1] for row in result}
        print(f"  Vorhandene CHECK Constraints: {constraints}")
    
    await engine.dispose()
    print("\n" + "=" * 60)
    print("TESTS ABGESCHLOSSEN")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
