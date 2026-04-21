import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

import httpx

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.config import settings
from app.chat.schemas import ChatRequest
from app.db.models import Conversation, Message
from app.db.session import get_db


class ConversationItem(BaseModel):
    id: UUID
    title: Optional[str]
    last_message_at: Optional[datetime]
    model_used: str


class ConversationListResponse(BaseModel):
    items: list[ConversationItem]
    total: int
    limit: int
    offset: int


class MessageItem(BaseModel):
    role: str
    content: str
    created_at: datetime


class ConversationDetailResponse(BaseModel):
    id: UUID
    title: Optional[str]
    model_used: str
    last_message_at: Optional[datetime]
    messages: list[MessageItem]

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_LITELLM_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)


def make_title(text: str) -> str:
    return text[:40].rsplit(" ", 1)[0] if len(text) > 40 else text


async def _persist(
    db: AsyncSession,
    conversation_id: UUID,
    user_message: str,
    assistant_content: str,
    usage: dict,
    model_used: str,
) -> None:
    tokens_input = usage.get("prompt_tokens")
    tokens_output = usage.get("completion_tokens")

    db.add(Message(
        conversation_id=conversation_id,
        role="user",
        content=user_message,
    ))
    db.add(Message(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        model=model_used,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=None,
    ))
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(last_message_at=func.now())
    )
    await db.commit()


@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    model_used = settings.chat_default_model
    litellm_payload = {
        "model": model_used,
        "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
        "stream": True,
        "stream_options": {"include_usage": True},
        "user": current_user.sub,
    }

    client = httpx.AsyncClient(timeout=_LITELLM_TIMEOUT)
    user_message = request.messages[-1].content if request.messages else ""

    # Conversation anlegen oder laden — eigene Transaktion, direkt committet
    conversation_id = request.conversation_id

    if conversation_id is None:
        first_user_msg = next((m.content for m in request.messages if m.role == "user"), "")
        new_conv = Conversation(
            pseudonym=current_user.sub,
            model_used=model_used,
            title=make_title(first_user_msg) if first_user_msg else None,
        )
        db.add(new_conv)
        await db.flush()
        await db.refresh(new_conv)
        conversation_id = new_conv.id
        await db.commit()
    else:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.pseudonym == current_user.sub,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            await client.aclose()
            raise HTTPException(status_code=404, detail="Konversation nicht gefunden")
        model_used = existing.model_used
        litellm_payload["model"] = model_used

    try:
        req = client.build_request(
            "POST",
            f"{settings.litellm_proxy_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json=litellm_payload,
        )
        response = await client.send(req, stream=True)
    except httpx.ConnectError:
        await client.aclose()
        raise HTTPException(status_code=502, detail="LiteLLM Proxy nicht erreichbar")

    if response.status_code != 200:
        error_body = await response.aread()
        await response.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=response.status_code,
            detail=f"LiteLLM Fehler: {error_body.decode()}" if error_body else "LiteLLM Fehler",
        )

    async def generate():
        full_content: list[str] = []
        usage: dict = {}
        try:
            async for line in response.aiter_lines():
                if not line:
                    continue
                if not line.startswith("data: "):
                    yield f"{line}\n\n"
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    yield f"{line}\n\n"
                    return
                try:
                    chunk = json.loads(payload)
                    token = chunk.get("choices", [{}])[0].get("delta", {}).get("content") or ""
                    if token:
                        full_content.append(token)
                        yield f"{line}\n\n"
                    if "usage" in chunk:
                        usage = chunk["usage"]
                except (json.JSONDecodeError, IndexError, KeyError):
                    yield f"{line}\n\n"
        finally:
            await response.aclose()
            await client.aclose()
            try:
                await _persist(db, conversation_id, user_message, "".join(full_content), usage, model_used)
            except Exception:
                logger.exception("Fehler beim Persistieren der Konversation %s", conversation_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"X-Conversation-Id": str(conversation_id)},
    )


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    # Gesamtzahl aller eigenen Konversationen
    total_stmt = select(func.count()).select_from(Conversation).where(
        Conversation.pseudonym == current_user.sub
    )
    total_result = await db.execute(total_stmt)
    total = total_result.scalar()

    # Paginierte Liste
    stmt = (
        select(Conversation)
        .where(Conversation.pseudonym == current_user.sub)
        .order_by(Conversation.last_message_at.desc().nulls_last())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    conversations = result.scalars().all()

    items = [
        ConversationItem(
            id=conv.id,
            title=conv.title,
            last_message_at=conv.last_message_at,
            model_used=conv.model_used,
        )
        for conv in conversations
    ]

    return ConversationListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailResponse:
    # Erst prüfen ob die Konversation existiert
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()

    if conversation is None:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    # Sicherheitscheck: Pseudonym muss übereinstimmen
    if conversation.pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    # Nachrichten laden
    messages_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = messages_result.scalars().all()

    messages_list = [
        {
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at,
        }
        for msg in messages
    ]

    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        model_used=conversation.model_used,
        last_message_at=conversation.last_message_at,
        messages=messages_list,
    )
