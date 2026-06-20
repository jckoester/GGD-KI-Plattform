"""Tool-Registry für den Chat-Router.

ChatTool bündelt OpenAI-Function-Schema und async Handler.
tools_for() filtert die aktiven Tools pro Konversations-Kontext.

Freischaltungslogik:
  context_search — immer aktiv (sofern Modell Function-Calling unterstützt)
  planning       — nur wenn (a) 'planning' in assistant.tool_groups,
                            (b) conversation.group_id ist gesetzt,
                            (c) Nutzer ist Lehrkraft der Gruppe
  student_planning — read-only (z. B. get_exam_scope): nur wenn
                            'student_planning' in assistant.tool_groups und
                            conversation.group_id gesetzt (auch für Schüler).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    db: AsyncSession
    user: JwtPayload
    group_id: int | None
    conversation_id: UUID | None


@dataclass
class ChatTool:
    name: str
    group: str                   # 'context_search' | 'planning'
    definition: dict             # OpenAI-Function-Schema für LiteLLM
    handler: Callable[..., Awaitable[Any]]  # async (args: dict, ctx: ToolContext) -> JSON-serialisierbar
    writes: bool = False


TOOL_REGISTRY: dict[str, ChatTool] = {}


def register_tool(tool: ChatTool) -> None:
    TOOL_REGISTRY[tool.name] = tool


def tools_for(
    assistant: Any,
    group_id: int | None,
    is_group_teacher: bool,
) -> list[ChatTool]:
    """Gibt die für diese Konversation freigeschalteten Tools zurück.

    assistant kann None sein (kein Assistent aktiv).
    """
    result: list[ChatTool] = []
    asst_tool_groups: list[str] = getattr(assistant, "tool_groups", None) or []

    for tool in TOOL_REGISTRY.values():
        if tool.group == "context_search":
            result.append(tool)
        elif tool.group == "planning":
            if (
                "planning" in asst_tool_groups
                and group_id is not None
                and is_group_teacher
            ):
                result.append(tool)
        elif tool.group == "student_planning":
            # Read-only Planungsdaten — kein Lehrkraft-Recht nötig, nur Gruppenbezug.
            if "student_planning" in asst_tool_groups and group_id is not None:
                result.append(tool)

    return result
