import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

import sqlalchemy as sa

import httpx

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.config import settings
from app.chat.schemas import AttachmentMeta, ChatMessage, ChatRequest, TextPart, ImageUrlPart
from app.chat.tools import ChatTool, ToolContext, register_tool, tools_for
from app.chat.image_moderation import image_prompt_block_reason
from app.chat.image_store import (
    collect_conversation_image_paths,
    get_image_record,
    link_images_to_message,
    list_message_images,
    read_image_bytes,
    save_generated_image,
    unlink_paths,
)
from app.db.models import Conversation, Message, ConversationFlag, PseudonymAudit, Assistant, Subject, Group, GroupMembership, AssistantDocument, SiteConfig, ContextNode
from app.db.session import get_db, AsyncSessionLocal
from app.api.assistants import _is_visible_for_user
from app.context.service import get_context_for_query
from app.context.embedding import generate_embedding
from app.crisis.detector import CrisisHit, scan
from app.crisis.config import resolve_help_topic
from app.pedagogy.config import load_pedagogy
from app.pedagogy.compose import compose_system_content, is_student_treatment
from app.litellm.client import LiteLLMClient
from app.litellm.teams import STUDENT_TEAM_PREFIX, TEACHER_TEAM_ID
import app.planning.assistant_tools  # noqa: F401 — registriert Planungs-Tools in TOOL_REGISTRY


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


class GeneratedImageRef(BaseModel):
    image_id: str
    size: Optional[str] = None


class MessageItem(BaseModel):
    role: str
    content: str
    created_at: datetime
    cost_usd: Optional[float] = None
    attachments: list[AttachmentMeta] = []
    model: Optional[str] = None
    assistant_id: Optional[int] = None
    assistant_name: Optional[str] = None
    images: list[GeneratedImageRef] = []


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
    supports_function_calling: bool | None = None


class ModelListResponse(BaseModel):
    models: list[ModelItem]
    default_model: str

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_LITELLM_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=None, pool=10.0)
_TITLE_TIMEOUT = httpx.Timeout(5.0)
_SPEND_LOG_DELAY: float = settings.spend_log_delay
_MAX_TOOL_ROUNDS: int = 6

# Guardrail-Prompt-Cache
_GUARDRAIL_TTL = 60.0  # Sekunden
_guardrail_prompt_cache: tuple[str | None, float] | None = None

# Model-Info-Cache (supports_function_calling pro Modell)
_MODEL_INFO_TTL = 60.0  # Sekunden
_model_info_cache: tuple[dict[str, bool | None], float] | None = None

_SEARCH_CONTEXT_NODES_TOOL = {
    "type": "function",
    "function": {
        "name": "search_context_nodes",
        "description": (
            "Sucht Wissensknoten im Kontextspeicher der Plattform anhand einer "
            "Suchanfrage. Nutze dieses Tool, wenn du gezielt thematisch passende "
            "Inhalte finden sollst."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Suchbegriff oder kurze Suchanfrage",
                }
            },
            "required": ["query"],
        },
    },
}


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


async def _get_guardrail_prompt(db: AsyncSession) -> str | None:
    """Liest den schulweiten Guardrail-Prompt aus site_config (mit 60-s-Cache)."""
    global _guardrail_prompt_cache
    now = asyncio.get_event_loop().time()
    if _guardrail_prompt_cache is not None and now < _guardrail_prompt_cache[1]:
        return _guardrail_prompt_cache[0]
    result = await db.execute(
        select(SiteConfig.value).where(SiteConfig.key == "guardrail_prompt")
    )
    prompt = result.scalar_one_or_none()
    _guardrail_prompt_cache = (prompt, now + _GUARDRAIL_TTL)
    return prompt


async def _get_model_info() -> dict[str, bool | None]:
    """Gibt eine Map model_id → supports_function_calling zurück (60-s-Cache)."""
    global _model_info_cache
    now = asyncio.get_event_loop().time()
    if _model_info_cache is not None and now < _model_info_cache[1]:
        return _model_info_cache[0]
    litellm_client = LiteLLMClient()
    try:
        info = await litellm_client.get_model_info()
    except Exception:
        info = {}
    finally:
        await litellm_client.close()
    _model_info_cache = (info, now + _MODEL_INFO_TTL)
    return info


async def _exec_search_context_nodes(
    query: str, pseudonym: str, db: AsyncSession, *, limit: int = 8
) -> list[dict]:
    """Semantische Suche über alle sichtbaren ContextNodes, max. limit Treffer.

    Fällt auf ILIKE zurück wenn kein Embedding generiert werden kann oder
    kein Knoten ein Embedding hat.
    """
    try:
        query_embedding = await generate_embedding(query)
        embedding_str = "[" + ",".join(f"{v:.10f}" for v in query_embedding) + "]"

        sql = sa.text("""
            SELECT id, category, content_type, title
            FROM context_nodes
            WHERE status = 'active'
              AND embedding IS NOT NULL
              AND (
                  read_scope IN ('global', 'school', 'subject', 'group')
                  OR owner_pseudonym = :pseudonym
              )
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)
        result = await db.execute(
            sql,
            {"pseudonym": pseudonym, "embedding": embedding_str, "limit": limit},
        )
        rows = result.mappings().all()
        if rows:
            return [
                {
                    "node_id": str(row["id"]),
                    "title": row["title"],
                    "category": row["category"],
                    "content_type": row["content_type"],
                }
                for row in rows
            ]
        # Kein Knoten hat ein Embedding → Fallback
    except Exception:
        logger.warning("Embedding-Suche fehlgeschlagen, Fallback auf ILIKE")

    # Fallback: ILIKE-Suche auf Titel und Inhalt
    result = await db.execute(
        select(ContextNode)
        .where(
            or_(
                ContextNode.read_scope.in_(["global", "school", "subject", "group"]),
                ContextNode.owner_pseudonym == pseudonym,
            )
        )
        .where(ContextNode.status == "active")
        .where(
            or_(
                ContextNode.title.ilike(f"%{query}%"),
                ContextNode.content.ilike(f"%{query}%"),
            )
        )
        .limit(limit)
    )
    return [
        {
            "node_id": str(n.id),
            "title": n.title,
            "category": n.category,
            "content_type": n.content_type,
        }
        for n in result.scalars().all()
    ]


async def _search_context_nodes_handler(args: dict, ctx: ToolContext) -> list[dict]:
    return await _exec_search_context_nodes(args.get("query", ""), ctx.user.sub, ctx.db)


register_tool(ChatTool(
    name="search_context_nodes",
    group="context_search",
    writes=False,
    definition=_SEARCH_CONTEXT_NODES_TOOL,
    handler=_search_context_nodes_handler,
))


_GET_OPERATOREN_TOOL = {
    "type": "function",
    "function": {
        "name": "get_operatoren",
        "description": (
            "Gibt die offiziellen Operatoren (handlungsleitende Verben) des Fachs "
            "dieser Konversation laut Bildungsplan zurück — je Operator mit Definition "
            "und Anforderungsbereich (AFB I–III). Nutze dieses Tool, um Aufgaben­"
            "stellungen mit den korrekten fachspezifischen Operatoren zu formulieren "
            "oder um die korrekte Verwendung von Operatoren in einer Schülerlösung zu "
            "prüfen. Ohne Fachbezug der Konversation liefert es eine leere Liste."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


async def _resolve_conversation_subject_id(ctx: ToolContext) -> Optional[int]:
    """Leitet das Fach (subject_id) der Konversation ab: Gruppe → Fach, sonst
    conversation.subject_id (bzw. deren Gruppe). None wenn kein Fachbezug."""
    if ctx.group_id is not None:
        grp = await ctx.db.get(Group, ctx.group_id)
        if grp and grp.subject_id is not None:
            return grp.subject_id
    if ctx.conversation_id is not None:
        conv = await ctx.db.get(Conversation, ctx.conversation_id)
        if conv is not None:
            if conv.subject_id is not None:
                return conv.subject_id
            if conv.group_id is not None:
                grp = await ctx.db.get(Group, conv.group_id)
                if grp:
                    return grp.subject_id
    return None


async def _exec_get_operatoren(ctx: ToolContext) -> list[dict]:
    """Operatoren des Konversations-Fachs (aktuelle Edition) für den Assistenten.

    Deterministisch (keine Top-k-Suche): liefert die vollständige Operatorenliste
    der neuesten importierten Edition (`bp_version`) des Fachs, alphabetisch.
    """
    subject_id = await _resolve_conversation_subject_id(ctx)
    if subject_id is None:
        return []
    rows = (await ctx.db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "operator",
            ContextNode.subject_id == subject_id,
            ContextNode.status == "active",
        )
    )).scalars().all()
    if not rows:
        return []
    # Aktuelle Edition = neuestes bp_version (V1/V2/V3 koexistieren als Knoten).
    newest = max((n.metadata_ or {}).get("bp_version", "") for n in rows)
    current = [n for n in rows if (n.metadata_ or {}).get("bp_version", "") == newest]
    current.sort(key=lambda n: (n.title or "").lower())
    out: list[dict] = []
    for n in current:
        md = n.metadata_ or {}
        afb = md.get("afb") or []
        entry = {
            "operator": n.title,
            "afb": ", ".join(afb) if isinstance(afb, list) else str(afb),
            "bedeutung": n.content or "",
        }
        if md.get("aliase"):
            entry["synonyme"] = md["aliase"]
        out.append(entry)
    return out


async def _get_operatoren_handler(args: dict, ctx: ToolContext) -> list[dict]:
    return await _exec_get_operatoren(ctx)


register_tool(ChatTool(
    name="get_operatoren",
    group="context_search",
    writes=False,
    definition=_GET_OPERATOREN_TOOL,
    handler=_get_operatoren_handler,
))


# ── Bildgenerierung (Phase 16) ────────────────────────────────────────────────

_GENERATE_IMAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": (
            "Erzeugt ein Bild aus einer natürlichsprachlichen Beschreibung "
            "(Text-zu-Bild). Nutze dieses Tool, wenn die Nutzerin oder der Nutzer ein "
            "Bild, eine Illustration, eine Skizze oder eine Grafik erzeugt haben "
            "möchte. Formuliere einen klaren, beschreibenden Bild-Prompt. Verwende "
            "keine echten Personennamen oder personenbezogenen Daten im Prompt."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Beschreibung des gewünschten Bildes.",
                },
                "size": {
                    "type": "string",
                    "enum": ["1024x1024", "1024x1536", "1536x1024"],
                    "description": (
                        "Bildformat: quadratisch (1024x1024), hoch (1024x1536) oder "
                        "quer (1536x1024). Standard: quadratisch."
                    ),
                },
            },
            "required": ["prompt"],
        },
    },
}

# Nur abgerechnete Standardgrößen zulassen (sonst Spend=0-Risiko bei LiteLLM).
_ALLOWED_IMAGE_SIZES = {"1024x1024", "1024x1536", "1536x1024"}


def _image_prompt_block_reason(prompt: str) -> Optional[str]:
    """Moderation des (LLM-gebildeten) Bild-Prompts vor dem Call.

    Delegiert an ``app.chat.image_moderation``: Krisen-Scan (blockierend für Bilder)
    + kuratierte Bild-Blockliste. Gibt einen Ablehnungsgrund (für den LLM) zurück
    oder None (= erlaubt). Bleibt als Modul-Symbol bestehen (Test-Seam).
    """
    return image_prompt_block_reason(prompt)


async def _exec_generate_image(args: dict, ctx: ToolContext) -> dict:
    """Erzeugt ein Bild über den LiteLLM-Bild-Endpoint (Schritt 2: roh, ohne Persistenz).

    Moderiert den Bild-Prompt (Stub), generiert dann über den **User-Virtual-Key**
    (Spend/Budget beim User). Die Bytes werden hier noch nicht persistiert/angezeigt
    (→ Schritt 4/5/6); der LLM erhält eine knappe Bestätigung.
    """
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return {"status": "error", "error": "Kein Bild-Prompt angegeben."}

    reason = _image_prompt_block_reason(prompt)
    if reason:
        return {"status": "blocked", "error": reason}

    if ctx.litellm_key is None:
        logger.error(
            "generate_image: kein LiteLLM-Key im ToolContext (pseudonym=%s)",
            getattr(ctx.user, "sub", None),
        )
        return {"status": "error", "error": "Bildgenerierung nicht verfügbar."}

    if ctx.conversation_id is None:
        # Ohne Konversation kein Persistenzziel → gar nicht erst generieren (spart Budget).
        logger.error("generate_image: keine conversation_id im ToolContext")
        return {"status": "error", "error": "Bildgenerierung nicht verfügbar."}

    size = args.get("size")
    if size not in _ALLOWED_IMAGE_SIZES:
        size = settings.image_default_size

    client = LiteLLMClient()
    try:
        image_bytes = await client.generate_image(
            prompt,
            model=settings.image_default_model,
            api_key=ctx.litellm_key,
            user=ctx.user.sub,
            size=size,
            response_format=None,  # gpt-image-1 liefert immer Base64 und lehnt den Param ab
        )
    except Exception:
        logger.exception("Bildgenerierung fehlgeschlagen")
        return {"status": "error", "error": "Bildgenerierung fehlgeschlagen."}
    finally:
        await client.close()

    try:
        image_id = await save_generated_image(
            ctx.db,
            pseudonym=ctx.user.sub,
            conversation_id=ctx.conversation_id,
            image_bytes=image_bytes,
            model=settings.image_default_model,
            size=size,
            mime_type="image/png",
        )
    except Exception:
        logger.exception("Bild konnte nicht gespeichert werden")
        return {"status": "error", "error": "Bildgenerierung fehlgeschlagen."}

    # SSE-image-Event + Frontend-Anzeige (Bild an der Nachricht) folgen in Schritt 5/6.
    return {
        "status": "ok",
        "image_id": str(image_id),
        "size": size,
        "note": "Bild wurde erzeugt und gespeichert.",
    }


async def _generate_image_handler(args: dict, ctx: ToolContext) -> dict:
    return await _exec_generate_image(args, ctx)


register_tool(ChatTool(
    name="generate_image",
    group="image_generation",
    writes=False,
    definition=_GENERATE_IMAGE_TOOL,
    handler=_generate_image_handler,
))


def _serialize_user_message(user_message: str, attachments: list[AttachmentMeta]) -> str:
    """Serialisiert die User-Nachricht für die DB (mit Anhang-Metadaten, falls vorhanden)."""
    if attachments:
        return json.dumps({
            "v": 1,
            "text": user_message,
            "files": [{"name": a.name, "type": a.type} for a in attachments],
        }, ensure_ascii=False)
    return user_message


async def _persist(
    db: AsyncSession,
    conversation_id: UUID,
    user_message: str,
    user_attachments: list[AttachmentMeta],
    assistant_content: str,
    usage: dict,
    model_used: str,
    cost_usd: Optional[float] = None,
    assistant_id: Optional[int] = None,
    conv_assistant_update: Optional[tuple[int, Optional[str]]] = None,
    skip_user_message: bool = False,
    generated_image_ids: Optional[list] = None,
) -> None:
    tokens_input = usage.get("prompt_tokens")
    tokens_output = usage.get("completion_tokens")

    # Die User-Nachricht kann bereits früh persistiert worden sein (Krisen-Erkennung).
    if not skip_user_message:
        db.add(Message(
            conversation_id=conversation_id,
            role="user",
            content=_serialize_user_message(user_message, user_attachments),
        ))
    assistant_msg = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        model=model_used,
        assistant_id=assistant_id,    # 2-3
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
    )
    db.add(assistant_msg)

    # Mid-Stream erzeugte Bilder an diese Assistant-Nachricht hängen (Phase 16, Schritt 5).
    # Flush macht die server-generierte message_id verfügbar.
    if generated_image_ids:
        await db.flush()
        await link_images_to_message(db, generated_image_ids, assistant_msg.id)

    update_values: dict = {"last_message_at": func.now()}
    if cost_usd is not None:
        update_values["total_cost_usd"] = Conversation.total_cost_usd + cost_usd
    # 2-4: Assistenten-Wechsel atomar mitspeichern
    if conv_assistant_update is not None:
        new_asst_id, new_snapshot = conv_assistant_update
        update_values["assistant_id"] = new_asst_id
        update_values["system_prompt_snapshot"] = new_snapshot

    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(**update_values)
    )
    await db.commit()


@dataclass
class _CrisisRecord:
    """Ergebnis der Krisen-Erkennung für eine Nachricht (Schritt 5: Banner-SSE)."""
    hit: CrisisHit
    show_banner: bool


async def _record_crisis(
    db: AsyncSession,
    conversation_id: UUID,
    user_message: str,
    attachments: list[AttachmentMeta],
    pseudonym: str,
) -> Optional[_CrisisRecord]:
    """Krisen-Erkennung (ADR-008 Teil 3) — OHNE Blockieren des Chats.

    Bei Treffer wird die auslösende User-Nachricht früh persistiert (für die
    message_id), ein Flag in conversation_flags angelegt und committet — unabhängig
    vom Ausgang des LLM-Streams. Das Banner wird nur beim ersten Treffer einer
    Kategorie je Konversation gezeigt; geflaggt wird jeder Treffer.

    Gibt None zurück, wenn nichts greift. Kommt ein Record zurück, wurde die
    User-Nachricht bereits geschrieben — der Aufrufer setzt _persist(skip_user_message=True).
    """
    hit = scan(user_message)
    if hit is None:
        return None

    logger.info(
        "Krisen-Erkennung: Regel '%s' ausgelöst (kategorie=%s, severity=%s, conv=%s)",
        hit.trigger_rule, hit.category, hit.severity, conversation_id,
    )

    prior = await db.scalar(
        select(ConversationFlag.id)
        .where(
            ConversationFlag.conversation_id == conversation_id,
            ConversationFlag.flag_category == hit.category,
        )
        .limit(1)
    )
    show_banner = prior is None

    user_row = Message(
        conversation_id=conversation_id,
        role="user",
        content=_serialize_user_message(user_message, attachments),
    )
    db.add(user_row)
    await db.flush()
    db.add(ConversationFlag(
        conversation_id=conversation_id,
        message_id=user_row.id,
        flag_source="auto_crisis",
        flag_category=hit.category,
        severity=hit.severity,
        trigger_rule=hit.trigger_rule,
        coreviewer_role=hit.coreviewer_role,
    ))
    await db.commit()
    logger.warning(
        "Krisen-Flag angelegt: kategorie=%s severity=%s pseudonym=%s conv=%s",
        hit.category, hit.severity, pseudonym, conversation_id,
    )
    return _CrisisRecord(hit=hit, show_banner=show_banner)


def _crisis_sse_event(record: Optional[_CrisisRecord]) -> Optional[str]:
    """SSE-Event-String für das Hilfe-Banner — None, wenn kein Banner gezeigt wird.

    Löst den help_topic serverseitig aus help_resources.yaml auf; das Frontend
    erhält fertige Kontaktdaten und kennt die YAML nicht.
    """
    if record is None or not record.show_banner:
        return None
    payload = resolve_help_topic(record.hit.help_topic)
    if payload is None:
        return None
    return f"event: crisis\ndata: {json.dumps(payload)}\n\n"


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
    conversation_is_test = request.is_test
    title_prompt: str | None = None

    # Für Assistentenwechsel mid-Chat
    active_assistant_id: Optional[int] = None
    conv_assistant_update: Optional[tuple[int, Optional[str]]] = None

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
                is_admin = "admin" in current_user.roles
                is_teacher = "teacher" in current_user.roles
                if not is_admin and not is_teacher:
                    await client.aclose()
                    raise HTTPException(status_code=403, detail="Testchat nicht erlaubt")
                # Nicht-aktive Assistenten: nur Ersteller oder Admin darf testen
                if assistant.status != "active" and not is_admin:
                    if assistant.created_by != current_user.sub:
                        await client.aclose()
                        raise HTTPException(status_code=403, detail="Nur der Ersteller kann diesen Assistenten testen")
            elif not _is_visible_for_user(assistant, current_user.roles):
                await client.aclose()
                raise HTTPException(status_code=403, detail="Assistent nicht verfügbar")
            system_prompt_snapshot = assistant.system_prompt
            if not request.model_id:
                model_used = assistant.model
        active_assistant = assistant

        first_user_msg = next((_user_text(m) for m in request.messages if m.role == "user"), "")

        # Kontext aus Request oder Assistent ableiten
        if request.group_id is not None:
            # group_id gesetzt: subject_id aus Gruppe ableiten
            grp_result = await db.execute(
                select(Group).where(Group.id == request.group_id)
            )
            grp = grp_result.scalar_one_or_none()
            subject_id = grp.subject_id if grp else None
            group_id = request.group_id
        elif request.subject_id is not None:
            # Nur subject_id gesetzt (Lehrkraft: Fach-Ebene ohne Gruppe)
            subject_id = request.subject_id
            group_id = None
        else:
            # Fallback: aus Assistent ableiten
            subject_id = assistant.subject_id if assistant is not None else None
            group_id = None
        conversation_group_id = group_id

        new_conv = Conversation(
            pseudonym=current_user.sub,
            model_used=model_used,
            title=make_title(first_user_msg) if first_user_msg else None,
            assistant_id=request.assistant_id,
            subject_id=subject_id,
            group_id=group_id,
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
        active_assistant_id = request.assistant_id
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

        # Startwerte aus bestehender Konversation
        model_used = existing.model_used
        system_prompt_snapshot = existing.system_prompt_snapshot
        active_assistant_id = existing.assistant_id
        conversation_group_id = existing.group_id
        conversation_is_test = existing.is_test
        active_assistant: Optional[Assistant] = None

        # 2-1: Assistentenwechsel mid-Chat
        if request.assistant_id is not None:
            asst_result = await db.execute(
                select(Assistant).where(Assistant.id == request.assistant_id)
            )
            new_assistant = asst_result.scalar_one_or_none()
            if new_assistant is None:
                await client.aclose()
                raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
            if not _is_visible_for_user(new_assistant, current_user.roles):
                await client.aclose()
                raise HTTPException(status_code=403, detail="Assistent nicht verfügbar")

            system_prompt_snapshot = new_assistant.system_prompt
            active_assistant_id = new_assistant.id
            active_assistant = new_assistant

            # Conversation-Update vormerken (atomar mit _persist geschrieben)
            conv_assistant_update = (new_assistant.id, new_assistant.system_prompt)

            # Assistentenmodell als Fallback wenn kein explizites model_id
            if not request.model_id and new_assistant.model:
                model_used = new_assistant.model

        if active_assistant is None and active_assistant_id is not None:
            asst_r = await db.execute(
                select(Assistant).where(Assistant.id == active_assistant_id)
            )
            active_assistant = asst_r.scalar_one_or_none()

        # 2-2: Modellwechsel mid-Chat (höchste Priorität, überschreibt Assistenten-Modell)
        if request.model_id:
            model_used = request.model_id

    # Krisen-Erkennung (ADR-008 Teil 3): lokal, parallel zum LLM-Call, OHNE Blockieren.
    # Test-Chats (Assistenten-Entwicklung) werden nicht geflaggt.
    crisis_record: Optional[_CrisisRecord] = None
    if not conversation_is_test:
        crisis_record = await _record_crisis(
            db,
            conversation_id,
            user_message,
            request.messages[-1].attachments if request.messages else [],
            current_user.sub,
        )

    # Dokumente für den Assistenten laden (falls vorhanden) - 2-5
    assistant_id_for_docs = active_assistant_id

    # Kontext aus Kontextspeicher laden — immer, auch ohne Assistenten (KS-Phase-5)
    context_str = await get_context_for_query(
        assistant_id=active_assistant_id,
        pseudonym=current_user.sub,
        query_text=user_message,
        chat_id=conversation_id,
        db=db,
    )

    llm_messages: list[dict] = []

    guardrail_prompt = await _get_guardrail_prompt(db)
    if guardrail_prompt:
        llm_messages.append({"role": "system", "content": guardrail_prompt})

    if assistant_id_for_docs is not None:
        docs_result = await db.execute(
            select(AssistantDocument)
            .where(AssistantDocument.assistant_id == assistant_id_for_docs)
            .order_by(AssistantDocument.created_at)
        )
        docs = docs_result.scalars().all()
        if docs:
            parts = [
                f"Hintergrunddokument \"{doc.filename}\":\n\n{doc.content}"
                for doc in docs
            ]
            llm_messages.append({
                "role": "system",
                "content": "\n\n---\n\n".join(parts),
            })

    # Pädagogische Leitplanken (ADR-008 Teil 2 + 1B): universelle Basis +
    # zielgruppenspezifische Erweiterung + Wissens-Kontext + Assistenten-Prompt +
    # (nur Schüler-Behandlung) Lernverhalten-Augmentierungen. Auswahl nach D1.
    pedagogy = load_pedagogy()
    user_is_student = "student" in current_user.roles
    audience = active_assistant.audience if active_assistant is not None else None
    disabled_aug = (
        active_assistant.disabled_augmentations if active_assistant is not None else None
    )
    student_treatment = is_student_treatment(audience, user_is_student)
    llm_messages.append({
        "role": "system",
        "content": compose_system_content(
            pedagogy,
            student_treatment=student_treatment,
            context_str=context_str,
            assistant_system_prompt=system_prompt_snapshot,
            disabled_augmentations=disabled_aug,
        ),
    })
    if pedagogy.output_format.strip():
        llm_messages.append(
            {"role": "system", "content": pedagogy.output_format.strip()}
        )
    llm_messages.extend(
        {"role": msg.role, "content": _serialize_content(msg.content)}
        for msg in request.messages
    )
    litellm_payload["model"] = model_used
    litellm_payload["messages"] = llm_messages

    # Tool-Calling: aktive Tools aus Registry ermitteln
    _capability_map = await _get_model_info()
    _is_group_teacher = False
    if conversation_group_id is not None:
        from app.planning.permissions import require_group_teacher
        import sqlalchemy as sa
        from app.db.models import GroupMembership as _GM
        _mbr = await db.execute(
            sa.select(_GM).where(
                _GM.group_id == conversation_group_id,
                _GM.pseudonym == current_user.sub,
                _GM.role_in_group == "teacher",
            )
        )
        _is_group_teacher = _mbr.scalar_one_or_none() is not None

    _active_tools = tools_for(active_assistant, conversation_group_id, _is_group_teacher)
    _tool_defs = [t.definition for t in _active_tools]
    _tool_map = {t.name: t for t in _active_tools}

    if _tool_defs and _capability_map.get(model_used) is not False:
        litellm_payload["tools"] = _tool_defs
        litellm_payload["tool_choice"] = "auto"

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

    _extra_responses: list = []  # zusätzliche HTTP-Responses aus Tool-Runden

    async def generate():
        full_content: list[str] = []
        usage: dict = {}
        chunk_id: str | None = None
        cost_usd: Optional[float] = None
        _generated_image_ids: list = []  # mid-Stream erzeugte Bilder (→ message_id in _persist)

        current_messages = list(llm_messages)
        current_response = response

        # Hilfe-Ressourcen-Banner (ADR-008 Teil 3) zuerst — erreicht die Schüler:in
        # auch dann, wenn der LLM-Stream später abbricht.
        _crisis_event = _crisis_sse_event(crisis_record)
        if _crisis_event:
            yield _crisis_event

        try:
            for _round in range(_MAX_TOOL_ROUNDS + 1):
                _tc_id: str | None = None
                _tc_name: str | None = None
                _tc_args: list[str] = []
                _finish_reason: str | None = None

                async for line in current_response.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        yield f"{line}\n\n"
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        choice = chunk.get("choices", [{}])[0]
                        delta = choice.get("delta", {})
                        fr = choice.get("finish_reason")
                        if fr:
                            _finish_reason = fr

                        if delta.get("tool_calls"):
                            for tc in delta["tool_calls"]:
                                if tc.get("id"):
                                    _tc_id = tc["id"]
                                fn = tc.get("function") or {}
                                if fn.get("name"):
                                    _tc_name = fn["name"]
                                if fn.get("arguments"):
                                    _tc_args.append(fn["arguments"])
                            if "usage" in chunk:
                                usage = chunk["usage"]
                                chunk_id = chunk.get("id")
                            continue

                        token = delta.get("content") or ""
                        if token:
                            full_content.append(token)
                            yield f"{line}\n\n"
                        if "usage" in chunk:
                            usage = chunk["usage"]
                            chunk_id = chunk.get("id")
                    except (json.JSONDecodeError, IndexError, KeyError):
                        yield f"{line}\n\n"

                # -- Tool-Call verarbeiten oder abbrechen --
                if _finish_reason != "tool_calls" or not _tc_name:
                    break

                if _round >= _MAX_TOOL_ROUNDS:
                    logger.warning("MAX_TOOL_ROUNDS (%d) erreicht — stoppe Tool-Loop", _MAX_TOOL_ROUNDS)
                    break

                tool = _tool_map.get(_tc_name)
                if tool is None:
                    logger.warning("Unbekanntes Tool '%s' — stoppe Tool-Loop", _tc_name)
                    break

                yield (
                    f"event: tool_status\n"
                    f"data: {json.dumps({'tool': _tc_name, 'round': _round + 1})}\n\n"
                )

                try:
                    args = json.loads("".join(_tc_args) or "{}")
                    tool_ctx = ToolContext(
                        db=db,
                        user=current_user,
                        group_id=conversation_group_id,
                        conversation_id=conversation_id,
                        litellm_key=litellm_key,
                    )
                    tool_result = await tool.handler(args, tool_ctx)
                except Exception:
                    logger.exception("Tool '%s' fehlgeschlagen", _tc_name)
                    tool_result = {"error": "Tool-Ausführung fehlgeschlagen"}

                # Rückwärtskompatibilität: context_suggestions SSE für context_search
                if tool.group == "context_search" and isinstance(tool_result, list):
                    yield (
                        f"event: context_suggestions\n"
                        f"data: {json.dumps({'nodes': tool_result})}\n\n"
                    )
                    tool_result_str = json.dumps({"nodes": [n["title"] for n in tool_result]})
                else:
                    tool_result_str = json.dumps(tool_result)

                # Bild-Tool (Phase 16, Schritt 5): Referenz ans Frontend senden + für die
                # message_id-Verknüpfung (in _persist) sammeln.
                if (
                    _tc_name == "generate_image"
                    and isinstance(tool_result, dict)
                    and tool_result.get("status") == "ok"
                    and tool_result.get("image_id")
                ):
                    _generated_image_ids.append(UUID(tool_result["image_id"]))
                    yield (
                        f"event: image\n"
                        f"data: {json.dumps({'image_id': tool_result['image_id'], 'size': tool_result.get('size')})}\n\n"
                    )

                current_messages = current_messages + [
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": _tc_id,
                            "type": "function",
                            "function": {
                                "name": _tc_name,
                                "arguments": "".join(_tc_args),
                            },
                        }],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": _tc_id,
                        "content": tool_result_str,
                    },
                ]

                # Nächste Runde: Request MIT Tools (damit weitere Tool-Calls möglich sind)
                next_payload = {**litellm_payload, "messages": current_messages}
                req_next = client.build_request(
                    "POST",
                    f"{settings.litellm_proxy_url}/chat/completions",
                    headers={"Authorization": f"Bearer {litellm_key}"},
                    json=next_payload,
                )
                current_response = await client.send(req_next, stream=True)
                _extra_responses.append(current_response)

            # -- Title-Task abwarten --
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

            # -- Kosten aus SpendLogs holen --
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

            yield "data: [DONE]\n\n"

        finally:
            await response.aclose()
            for _r in _extra_responses:
                try:
                    await _r.aclose()
                except Exception:
                    pass
            await client.aclose()

        try:
            await _persist(
                db, conversation_id, user_message, last_attachments,
                "".join(full_content), usage, model_used, cost_usd=cost_usd,
                assistant_id=active_assistant_id,
                conv_assistant_update=conv_assistant_update,
                skip_user_message=crisis_record is not None,
                generated_image_ids=_generated_image_ids,
            )
        except Exception:
            logger.exception("Fehler beim Persistieren der Konversation %s", conversation_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "X-Conversation-Id": str(conversation_id),
            "X-Model-Id": model_used or "",
            "X-Assistant-Id": str(active_assistant_id) if active_assistant_id else "",
        },
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
    is_admin = "admin" in current_user.roles
    if team_id is not None and not is_admin:
        try:
            info = await client.get_team_info(team_id)
        except Exception:
            logger.error("get_team_info fehlgeschlagen für %s — ungefilterte Modelle", team_id)
            filtered_models = all_models
        else:
            if info is None:
                filtered_models = all_models
            else:
                allowlist = info.get("models") or []
                if not allowlist or allowlist == ["no-default-models"]:
                    filtered_models = []
                else:
                    allowlist_set = set(allowlist)
                    filtered_models = [m for m in all_models if m in allowlist_set]
    else:
        filtered_models = all_models

    await client.close()

    capability_map = await _get_model_info()

    return ModelListResponse(
        models=[
            ModelItem(
                id=model_id,
                supports_function_calling=capability_map.get(model_id),
            )
            for model_id in filtered_models
        ],
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

    # ADR-008 Teil 7: Konversationen mit einem nicht verworfenen Flag werden nicht hart
    # gelöscht, sondern nur für die Nutzerin ausgeblendet (sonst würde der Flag per
    # Cascade mitgelöscht). Der Unterschied wird der Nutzerin bewusst nicht kommuniziert.
    open_flag = await db.scalar(
        select(ConversationFlag.id)
        .where(
            ConversationFlag.conversation_id == conversation_id,
            ConversationFlag.status != "dismissed",
        )
        .limit(1)
    )
    if open_flag is not None:
        conversation.hidden_by_user = True
        await db.commit()
        return None

    # Generierte Bilder dieser Konversation vor dem Löschen aufsammeln (die DB-Zeilen
    # gehen per FK-Cascade mit; die Dateien nach erfolgreichem Commit von Disk räumen).
    image_paths = await collect_conversation_image_paths(db, [conversation_id])

    # Löschen (cascading delete für Nachrichten + generated_images)
    await db.delete(conversation)
    await db.commit()
    unlink_paths(image_paths)

    return None


@router.get("/images/{image_id}")
async def get_generated_image(
    image_id: UUID,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Liefert ein generiertes Bild aus — nur an die Eigentümer:in (Pseudonym-Autorisierung)."""
    record = await get_image_record(db, image_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Bild nicht gefunden")
    if record.pseudonym != current_user.sub:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    data = read_image_bytes(record)
    if data is None:
        # Referenz existiert, Datei fehlt (bereits geräumt) — als nicht gefunden behandeln.
        raise HTTPException(status_code=404, detail="Bilddatei nicht gefunden")
    return Response(content=data, media_type=record.mime_type)


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_test: bool = Query(default=False),
    subject_id: Optional[int] = Query(None),
    group_id: Optional[int] = Query(None),
    exclude_groups: bool = Query(default=False),
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    # Filter für is_test
    is_test_filter = Conversation.is_test == False if not include_test else True

    # Build where conditions
    where_conditions = [
        Conversation.pseudonym == current_user.sub,
        is_test_filter,
        Conversation.hidden_by_user.is_(False),
    ]
    if subject_id is not None:
        where_conditions.append(Conversation.subject_id == subject_id)
    if group_id is not None:
        where_conditions.append(Conversation.group_id == group_id)
    if exclude_groups:
        where_conditions.append(Conversation.group_id.is_(None))

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
            Conversation.hidden_by_user.is_(False),
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

    # Nachrichten laden mit Assistenten-JOIN
    messages_result = await db.execute(
        select(Message, Assistant.name.label("assistant_name"))
        .outerjoin(Assistant, Assistant.id == Message.assistant_id)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    rows = messages_result.all()

    # Generierte Bilder je Nachricht (Phase 16, Schritt 6: History-Rehydrierung).
    img_map = await list_message_images(db, conversation_id)

    messages_list = []
    for row in rows:
        msg = row.Message
        asst_name = row.assistant_name
        if msg.role == "user":
            display_text, attachments = _parse_stored_content(msg.content)
            messages_list.append({
                "role": msg.role,
                "content": display_text,
                "created_at": msg.created_at,
                "cost_usd": None,
                "attachments": attachments,
                "model": None,
                "assistant_id": None,
                "assistant_name": None,
                "images": [],
            })
        else:
            messages_list.append({
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at,
                "cost_usd": float(msg.cost_usd) if msg.cost_usd is not None else None,
                "attachments": [],
                "model": msg.model,
                "assistant_id": msg.assistant_id,
                "assistant_name": asst_name,
                "images": img_map.get(msg.id, []),
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
