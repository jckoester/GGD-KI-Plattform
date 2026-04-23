import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

import httpx

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.config import settings
from app.chat.schemas import ChatRequest
from app.db.models import Conversation, Message, PseudonymAudit
from app.db.session import get_db, AsyncSessionLocal
from app.litellm.client import LiteLLMClient


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
    cost_usd: Optional[float] = None


class ConversationDetailResponse(BaseModel):
    id: UUID
    title: Optional[str]
    model_used: str
    last_message_at: Optional[datetime]
    total_cost_usd: Optional[float] = None
    messages: list[MessageItem]


class ModelItem(BaseModel):
    id: str


class ModelListResponse(BaseModel):
    models: list[ModelItem]
    default_model: str

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_LITELLM_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
_TITLE_TIMEOUT = httpx.Timeout(5.0)


def make_title(text: str) -> str:
    return text[:40].rsplit(" ", 1)[0] if len(text) > 40 else text


async def _generate_title(conversation_id: UUID, prompt: str) -> str | None:
    logger.debug("Titelgenerierung gestartet für %s (model=%s)", conversation_id, settings.title_model)
    litellm_payload = {
        "model": settings.title_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Du generierst kurze, prägnante Titel für Lernkonversationen. "
                    "Antworte nur mit dem Titel selbst — keine Anführungszeichen, kein Punkt am Ende. "
                    "Maximal 6 Wörter."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "user": "titlegen",
    }

    client = httpx.AsyncClient(timeout=_TITLE_TIMEOUT, verify=settings.litellm_verify_ssl)
    try:
        req = client.build_request(
            "POST",
            f"{settings.litellm_proxy_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json=litellm_payload,
        )
        response = await client.send(req)
        response.raise_for_status()
        data = response.json()
        title = data["choices"][0]["message"]["content"].strip()[:60]
        logger.debug("Titelgenerierung: LLM antwortete mit %r", title)

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(title=title)
            )
            await db.commit()
        logger.debug("Titelgenerierung: DB aktualisiert für %s", conversation_id)
        return title
    except Exception as exc:
        logger.warning("Titelgenerierung fehlgeschlagen (%s): %s", type(exc).__name__, exc)
        return None
    finally:
        await client.aclose()


async def _persist(
    db: AsyncSession,
    conversation_id: UUID,
    user_message: str,
    assistant_content: str,
    usage: dict,
    model_used: str,
    cost_usd: Optional[float] = None,
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
        cost_usd=cost_usd,
    ))

    update_values: dict = {"last_message_at": func.now()}
    if cost_usd is not None:
        update_values["total_cost_usd"] = Conversation.total_cost_usd + cost_usd

    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(**update_values)
    )
    await db.commit()


@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    model_used = request.model_id or settings.chat_default_model
    litellm_payload = {
        "model": model_used,
        "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
        "stream": True,
        "stream_options": {"include_usage": True},
        "user": current_user.sub,
    }

    client = httpx.AsyncClient(timeout=_LITELLM_TIMEOUT, verify=settings.litellm_verify_ssl)
    user_message = request.messages[-1].content if request.messages else ""

    conversation_id = request.conversation_id
    is_new = conversation_id is None
    title_prompt: str | None = None

    if is_new:
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
        # Kein commit hier — verhindert leere Einträge wenn LiteLLM nicht erreichbar ist.
        if settings.title_model and len(first_user_msg) > 20:
            title_prompt = first_user_msg
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
        # Laufende Konversationen behalten ihr ursprüngliches Modell.
        model_used = existing.model_used
        litellm_payload["model"] = model_used

    # Key aus DB laden
    key_result = await db.execute(
        select(PseudonymAudit.litellm_key).where(PseudonymAudit.pseudonym == current_user.sub)
    )
    litellm_key = key_result.scalar_one_or_none()

    if litellm_key is None:
        await client.aclose()
        raise HTTPException(status_code=503, detail="LiteLLM-Key nicht verfügbar")

    try:
        req = client.build_request(
            "POST",
            f"{settings.litellm_proxy_url}/chat/completions",
            headers={"Authorization": f"Bearer {litellm_key}"},
            json=litellm_payload,
        )
        response = await client.send(req, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        logger.error("LiteLLM nicht erreichbar (%s): %s", type(exc).__name__, exc)
        raise HTTPException(status_code=502, detail="LiteLLM Proxy nicht erreichbar")

    if response.status_code != 200:
        error_body = await response.aread()
        await response.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=response.status_code,
            detail=f"LiteLLM Fehler: {error_body.decode()}" if error_body else "LiteLLM Fehler",
        )

    # LiteLLM hat geantwortet → neue Konversation jetzt committen (eigene Session in _generate_title
    # setzt danach ein UPDATE ab, die Konversation muss also committed sein).
    if is_new:
        await db.commit()

    # Titelgenerierung parallel zum Stream starten
    if title_prompt:
        logger.debug("Starte Titel-Task für Konversation %s", conversation_id)
    else:
        logger.debug("Keine Titelgenerierung (title_model=%r, prompt_len=%d, is_new=%s)",
                     settings.title_model, len(user_message), is_new)
    title_task: asyncio.Task[str | None] | None = (
        asyncio.create_task(_generate_title(conversation_id, title_prompt))
        if title_prompt else None
    )

    async def generate():
        full_content: list[str] = []
        usage: dict = {}
        cost_usd: Optional[float] = None
        try:
            async for line in response.aiter_lines():
                if not line:
                    continue
                if not line.startswith("data: "):
                    yield f"{line}\n\n"
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    # Titel-Task abwarten (max. 3 s)
                    if title_task:
                        try:
                            title = await asyncio.wait_for(asyncio.shield(title_task), timeout=3.0)
                            if title:
                                logger.debug("Sende title-SSE-Event: %r", title)
                                yield f"event: title\ndata: {json.dumps({'title': title})}\n\n"
                            else:
                                logger.debug("Titel-Task lieferte None — kein SSE-Event")
                        except asyncio.TimeoutError:
                            logger.warning("Titel-Task Timeout nach 3 s für %s", conversation_id)
                        except Exception:
                            logger.exception("Fehler beim Warten auf Titel-Task")
                    # Kosten aus Response-Header lesen (bei Streaming immer None/0.0 — strukturelle LiteLLM-Einschränkung)
                    cost_header = response.headers.get("x-litellm-response-cost")
                    if cost_header is not None:
                        try:
                            cost_usd = float(cost_header)
                        except (ValueError, TypeError):
                            logger.warning("Ungültiger x-litellm-response-cost Header: %s", cost_header)
                    if cost_usd is not None:
                        logger.debug("Sende cost-SSE-Event: cost_usd=%s", cost_usd)
                        yield f"event: cost\ndata: {json.dumps({'cost_usd': cost_usd})}\n\n"
                    yield f"{line}\n\n"
                    break
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
            await _persist(
                db, conversation_id, user_message, "".join(full_content),
                usage, model_used, cost_usd=cost_usd,
            )
        except Exception:
            logger.exception("Fehler beim Persistieren der Konversation %s", conversation_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"X-Conversation-Id": str(conversation_id)},
    )


@router.get("/models")
async def list_models(
    current_user: JwtPayload = Depends(get_current_user),
) -> ModelListResponse:
    _ = current_user
    client = LiteLLMClient()
    try:
        model_ids = await client.list_models()
    except Exception as exc:
        logger.error("LiteLLM /models nicht erreichbar (%s): %s", type(exc).__name__, exc)
        raise HTTPException(status_code=502, detail="LiteLLM Proxy nicht erreichbar")
    finally:
        await client.close()

    return ModelListResponse(
        models=[ModelItem(id=model_id) for model_id in model_ids],
        default_model=settings.chat_default_model,
    )


class ConversationUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)


@router.patch("/conversations/{conversation_id}")
async def update_conversation_title(
    conversation_id: UUID,
    request: ConversationUpdateRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationItem:
    # Konversation laden und Sicherheitscheck
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if conversation is None:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    if conversation.pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    # Titel aktualisieren
    conversation.title = request.title
    await db.commit()

    return ConversationItem(
        id=conversation.id,
        title=conversation.title,
        last_message_at=conversation.last_message_at,
        model_used=conversation.model_used,
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    # Konversation laden und Sicherheitscheck
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if conversation is None:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    if conversation.pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    # Löschen (cascading delete für Nachrichten)
    await db.delete(conversation)
    await db.commit()

    return None


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
            "cost_usd": float(msg.cost_usd) if msg.cost_usd is not None else None,
        }
        for msg in messages
    ]

    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        model_used=conversation.model_used,
        last_message_at=conversation.last_message_at,
        total_cost_usd=float(conversation.total_cost_usd) if conversation.total_cost_usd else None,
        messages=messages_list,
    )
