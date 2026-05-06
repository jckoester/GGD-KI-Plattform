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
from app.chat.schemas import AttachmentMeta, ChatMessage, ChatRequest, TextPart, ImageUrlPart
from app.db.models import Conversation, Message, PseudonymAudit, Assistant, Subject, Group, GroupMembership
from app.db.session import get_db, AsyncSessionLocal
from app.api.assistants import _is_visible_for_user
from app.litellm.client import LiteLLMClient
from app.litellm.teams import STUDENT_TEAM_PREFIX, TEACHER_TEAM_ID


class ConversationItem(BaseModel):
    id: UUID
    title: Optional[str]
    last_message_at: Optional[datetime]
    model_used: str
    assistant_name: Optional[str] = None
    subject_id: Optional[int] = None
    group_id: Optional[int] = None
    is_test: bool = False


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
    attachments: list[AttachmentMeta] = []


class ConversationDetailResponse(BaseModel):
    id: UUID
    title: Optional[str]
    model_used: str
    assistant_id: Optional[int] = None
    assistant_name: Optional[str] = None
    subject_id: Optional[int] = None
    group_id: Optional[int] = None
    last_message_at: Optional[datetime]
    total_cost_usd: Optional[float] = None
    is_test: bool = False
    messages: list[MessageItem]


class ConversationCountsResponse(BaseModel):
    by_subject: dict[str, int]
    by_group: dict[str, int]


class ModelItem(BaseModel):
    id: str


class ModelListResponse(BaseModel):
    models: list[ModelItem]
    default_model: str

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_LITELLM_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=None, pool=10.0)
_TITLE_TIMEOUT = httpx.Timeout(5.0)
_SPEND_LOG_DELAY: float = settings.spend_log_delay


def _team_id_for_user(payload: JwtPayload) -> str | None:
    """
    Leitet die Team-ID aus dem JWT-Payload ab.
    Admin: TEACHER_TEAM_ID, Teacher: TEACHER_TEAM_ID, Student: jahrgang-{grade}
    """
    if "admin" in payload.roles:
        return TEACHER_TEAM_ID
    if "teacher" in payload.roles:
        return TEACHER_TEAM_ID
    if "student" in payload.roles:
        return f"{STUDENT_TEAM_PREFIX}{payload.grade}"
    return None  # Fallback: kein Team


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


def _user_text(msg: ChatMessage) -> str:
    """Gibt nur den vom Nutzer eingetippten Text zurück (ohne Datei-Inhalte)."""
    content = msg.content
    if isinstance(content, str):
        return content
    text_parts = [part.text for part in content if isinstance(part, TextPart)]
    if msg.attachments:
        # buildUserContent hängt den Nutzertext als letztes TextPart an
        return text_parts[-1] if text_parts else ""
    return " ".join(text_parts)


def _serialize_content(content: str | list) -> str | list:
    """Serialisiert Content für den LiteLLM-Payload (Pydantic-Modelle → dicts)."""
    if isinstance(content, str):
        return content
    return [part.model_dump() for part in content]


def _parse_stored_content(content: str) -> tuple[str, list[AttachmentMeta]]:
    """Parst ggf. strukturierten DB-Inhalt. Gibt (Anzeigetext, Anhänge) zurück."""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict) and parsed.get("v") == 1:
            text = parsed.get("text", "")
            files = [
                AttachmentMeta(name=f["name"], type=f["type"])
                for f in parsed.get("files", [])
                if isinstance(f, dict) and f.get("name") and f.get("type") in ("text", "image")
            ]
            return text, files
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        pass
    return content, []


async def _persist(
    db: AsyncSession,
    conversation_id: UUID,
    user_message: str,
    user_attachments: list[AttachmentMeta],
    assistant_content: str,
    usage: dict,
    model_used: str,
    cost_usd: Optional[float] = None,
) -> None:
    tokens_input = usage.get("prompt_tokens")
    tokens_output = usage.get("completion_tokens")

    if user_attachments:
        stored_content = json.dumps({
            "v": 1,
            "text": user_message,
            "files": [{"name": a.name, "type": a.type} for a in user_attachments],
        }, ensure_ascii=False)
    else:
        stored_content = user_message

    db.add(Message(
        conversation_id=conversation_id,
        role="user",
        content=stored_content,
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
    system_prompt_snapshot: Optional[str] = None
    litellm_payload = {
        "stream": True,
        "stream_options": {"include_usage": True},
        "user": current_user.sub,
    }

    client = httpx.AsyncClient(timeout=_LITELLM_TIMEOUT, verify=settings.litellm_verify_ssl)
    user_message = _user_text(request.messages[-1]) if request.messages else ""

    conversation_id = request.conversation_id
    is_new = conversation_id is None
    title_prompt: str | None = None

    if is_new:
        assistant: Optional[Assistant] = None
        if request.assistant_id is not None:
            asst_result = await db.execute(
                select(Assistant).where(Assistant.id == request.assistant_id)
            )
            assistant = asst_result.scalar_one_or_none()
            if assistant is None:
                await client.aclose()
                raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
            if request.is_test:
                # Testchat: nur Admins und Lehrkräfte dürfen inaktive Assistenten testen
                if "admin" not in current_user.roles and "teacher" not in current_user.roles:
                    await client.aclose()
                    raise HTTPException(status_code=403, detail="Testchat nicht erlaubt")
            elif not _is_visible_for_user(assistant, current_user.roles):
                await client.aclose()
                raise HTTPException(status_code=403, detail="Assistent nicht verfügbar")
            system_prompt_snapshot = assistant.system_prompt
            if not request.model_id:
                model_used = assistant.model

        first_user_msg = next((_user_text(m) for m in request.messages if m.role == "user"), "")
        new_conv = Conversation(
            pseudonym=current_user.sub,
            model_used=model_used,
            title=make_title(first_user_msg) if first_user_msg else None,
            assistant_id=request.assistant_id,
            subject_id=assistant.subject_id if assistant is not None else None,
            system_prompt_snapshot=system_prompt_snapshot,
            is_test=request.is_test,
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
        # Laufende Konversationen behalten ihr ursprüngliches Modell und Snapshot.
        model_used = existing.model_used
        system_prompt_snapshot = existing.system_prompt_snapshot

    llm_messages: list[dict] = []
    if system_prompt_snapshot:
        llm_messages.append({"role": "system", "content": system_prompt_snapshot})
    llm_messages.extend(
        {"role": msg.role, "content": _serialize_content(msg.content)}
        for msg in request.messages
    )
    litellm_payload["model"] = model_used
    litellm_payload["messages"] = llm_messages

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
        if isinstance(exc, httpx.ReadError) and any(
            isinstance(msg.content, list) and any(isinstance(p, ImageUrlPart) for p in msg.content)
            for msg in request.messages
        ):
            raise HTTPException(
                status_code=422,
                detail="Das ausgewählte Modell unterstützt keine Bilddateien. Bitte wähle ein Modell mit Vision-Support (z. B. GPT-4o).",
            )
        raise HTTPException(status_code=502, detail="LiteLLM Proxy nicht erreichbar")

    if response.status_code != 200:
        error_body = await response.aread()
        await response.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=response.status_code,
            detail=f"LiteLLM Fehler: {error_body.decode()}" if error_body else "LiteLLM Fehler",
        )

    # Anhänge der letzten Nachricht für Persistierung merken
    last_attachments = request.messages[-1].attachments if request.messages else []

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
        chunk_id: str | None = None
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
                    # Kosten aus SpendLogs holen (Retry, weil LiteLLM asynchron schreibt)
                    if chunk_id:
                        litellm_client = LiteLLMClient()
                        try:
                            for attempt in range(3):
                                await asyncio.sleep(_SPEND_LOG_DELAY)
                                cost_usd = await litellm_client.get_spend_log(chunk_id)
                                if cost_usd is not None:
                                    break
                        finally:
                            await litellm_client.close()

                    if cost_usd is not None:
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
                        chunk_id = chunk.get("id")
                except (json.JSONDecodeError, IndexError, KeyError):
                    yield f"{line}\n\n"
        finally:
            await response.aclose()
            await client.aclose()

        try:
            await _persist(
                db, conversation_id, user_message, last_attachments, "".join(full_content),
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
    client = LiteLLMClient()
    try:
        all_models = await client.list_models()
    except Exception as exc:
        logger.error("LiteLLM /models nicht erreichbar (%s): %s", type(exc).__name__, exc)
        raise HTTPException(status_code=502, detail="LiteLLM Proxy nicht erreichbar")

    team_id = _team_id_for_user(current_user)
    if team_id is not None:
        # Team-basierte Filterung für nicht-Admin-Nutzer
        try:
            info = await client.get_team_info(team_id)
        except Exception:
            logger.error("get_team_info fehlgeschlagen für %s — ungefilterte Modelle", team_id)
            # Fallback: alle Modelle zurückgeben, kein Hard-Fail
            filtered_models = all_models
        else:
            if info is None:
                # Team existiert nicht in LiteLLM → alle Modelle zurückgeben
                filtered_models = all_models
            else:
                allowlist = info.get("models") or []

                if not allowlist or allowlist == ["no-default-models"]:
                    # Kein Modell erlaubt oder explizit gesperrt
                    filtered_models = []
                else:
                    # Nur Modelle in der Allowlist zurückgeben
                    allowlist_set = set(allowlist)
                    filtered_models = [m for m in all_models if m in allowlist_set]
    else:
        # Admin: alle Modelle
        filtered_models = all_models

    await client.close()

    return ModelListResponse(
        models=[ModelItem(id=model_id) for model_id in filtered_models],
        default_model=settings.chat_default_model,
    )


class ConversationUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=100)
    subject_id: Optional[int] = None
    group_id: Optional[int] = None


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: UUID,
    request: ConversationUpdateRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationItem:
    # Mindestens ein Feld muss gesetzt sein
    if not request.model_fields_set:
        raise HTTPException(status_code=422, detail="Keine Felder angegeben")

    # Konversation laden und Sicherheitscheck
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if conversation is None:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    if conversation.pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    if 'title' in request.model_fields_set and request.title is not None:
        conversation.title = request.title

    if 'group_id' in request.model_fields_set:
        if request.group_id is not None:
            # Gruppe laden, Typ prüfen, Mitgliedschaft prüfen
            grp_result = await db.execute(
                select(Group)
                .join(GroupMembership, GroupMembership.group_id == Group.id)
                .where(
                    Group.id == request.group_id,
                    Group.type == 'teaching_group',
                    GroupMembership.pseudonym == current_user.sub,
                )
            )
            grp = grp_result.scalar_one_or_none()
            if grp is None:
                raise HTTPException(
                    status_code=404,
                    detail="Gruppe nicht gefunden oder keine Mitgliedschaft"
                )
            conversation.group_id = grp.id
            conversation.subject_id = grp.subject_id  # immer ableiten
        else:
            # group_id explizit auf null setzen
            conversation.group_id = None
            # subject_id nur löschen, wenn auch subject_id null gesendet wurde
            if 'subject_id' in request.model_fields_set and request.subject_id is None:
                conversation.subject_id = None

    elif 'subject_id' in request.model_fields_set:
        # Nur subject_id ändern (Lehrkraft: Fach-Ebene ohne Gruppe)
        if request.subject_id is not None:
            subj = await db.execute(
                select(Subject).where(Subject.id == request.subject_id)
            )
            if subj.scalar_one_or_none() is None:
                raise HTTPException(status_code=404, detail="Fach nicht gefunden")
        conversation.subject_id = request.subject_id
        conversation.group_id = None  # Fach-Ebene impliziert kein group_id

    await db.commit()
    await db.refresh(conversation)

    return ConversationItem(
        id=conversation.id,
        title=conversation.title,
        last_message_at=conversation.last_message_at,
        model_used=conversation.model_used,
        assistant_name=None,
        subject_id=conversation.subject_id,
        group_id=conversation.group_id,
        is_test=conversation.is_test,
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
    include_test: bool = Query(default=False),
    subject_id: Optional[int] = Query(None),
    group_id: Optional[int] = Query(None),
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    # Filter für is_test
    is_test_filter = Conversation.is_test == False if not include_test else True

    # Build where conditions
    where_conditions = [
        Conversation.pseudonym == current_user.sub,
        is_test_filter,
    ]
    if subject_id is not None:
        where_conditions.append(Conversation.subject_id == subject_id)
    if group_id is not None:
        where_conditions.append(Conversation.group_id == group_id)

    # Gesamtzahl aller eigenen Konversationen (mit Filter)
    total_stmt = select(func.count()).select_from(Conversation).where(*where_conditions)
    total_result = await db.execute(total_stmt)
    total = total_result.scalar()

    # Paginierte Liste mit Outer Join für Assistenten
    stmt = (
        select(Conversation, Assistant.name.label("assistant_name"))
        .outerjoin(Assistant, Conversation.assistant_id == Assistant.id)
        .where(*where_conditions)
        .order_by(Conversation.last_message_at.desc().nulls_last())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    rows = result.all()

    items = [
        ConversationItem(
            id=conv.id,
            title=conv.title,
            last_message_at=conv.last_message_at,
            model_used=conv.model_used,
            assistant_name=asst_name,
            subject_id=conv.subject_id,
            group_id=conv.group_id,
            is_test=conv.is_test,
        )
        for conv, asst_name in rows
    ]

    return ConversationListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/counts", response_model=ConversationCountsResponse)
async def get_conversation_counts(
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationCountsResponse:
    result = await db.execute(
        select(
            Conversation.subject_id,
            Conversation.group_id,
            func.count().label("cnt"),
        )
        .where(
            Conversation.pseudonym == current_user.sub,
            Conversation.is_test.is_(False),
        )
        .group_by(Conversation.subject_id, Conversation.group_id)
    )
    rows = result.all()

    by_subject: dict[str, int] = {}
    by_group: dict[str, int] = {}
    for subject_id, group_id, cnt in rows:
        if subject_id is not None:
            key = str(subject_id)
            by_subject[key] = by_subject.get(key, 0) + cnt
        if group_id is not None:
            key = str(group_id)
            by_group[key] = by_group.get(key, 0) + cnt

    return ConversationCountsResponse(by_subject=by_subject, by_group=by_group)


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

    messages_list = []
    for msg in messages:
        if msg.role == "user":
            display_text, attachments = _parse_stored_content(msg.content)
            messages_list.append({
                "role": msg.role,
                "content": display_text,
                "created_at": msg.created_at,
                "cost_usd": None,
                "attachments": attachments,
            })
        else:
            messages_list.append({
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at,
                "cost_usd": float(msg.cost_usd) if msg.cost_usd is not None else None,
                "attachments": [],
            })

    assistant_name: Optional[str] = None
    if conversation.assistant_id is not None:
        asst_result = await db.execute(
            select(Assistant).where(Assistant.id == conversation.assistant_id)
        )
        asst = asst_result.scalar_one_or_none()
        if asst:
            assistant_name = asst.name

    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        model_used=conversation.model_used,
        assistant_id=conversation.assistant_id,
        assistant_name=assistant_name,
        subject_id=conversation.subject_id,
        group_id=conversation.group_id,
        last_message_at=conversation.last_message_at,
        total_cost_usd=float(conversation.total_cost_usd) if conversation.total_cost_usd else None,
        is_test=conversation.is_test,
        messages=messages_list,
    )
