"""Tool-Registry für den Chat-Router.

ChatTool bündelt OpenAI-Function-Schema und async Handler.
tools_for() filtert die aktiven Tools pro Konversations-Kontext.

Freischaltungslogik:
  context_search — immer aktiv (sofern Modell Function-Calling unterstützt)
  planning       — nur wenn (a) 'planning' in assistant.tool_groups,
                            (b) conversation.group_id ist gesetzt,
                            (c) Nutzer ist Lehrkraft der Gruppe
  lesson_planning — Stundenentwurf (0.15): nur wenn 'lesson_planning' in
                            assistant.tool_groups und die Person die Lehrkraft-Rolle
                            hat — **ohne** Gruppenbezug, damit sich eine Stunde auch
                            im freien Chat finden lässt. Den Zugang zur einzelnen
                            Stunde prüft deshalb jedes Werkzeug selbst
                            (`zugang_zur_stunde`), nicht die Freischaltung.
  student_planning — read-only (z. B. get_exam_scope): nur wenn
                            'student_planning' in assistant.tool_groups und
                            conversation.group_id gesetzt (auch für Schüler).
  image_generation — nur wenn 'image_generation' in assistant.tool_groups.
                            Die Bild-Modell-Freigabe je Team greift zusätzlich am
                            LiteLLM-Proxy (Team-Allowlist), die Function-Calling-
                            Fähigkeit des Chat-Modells prüft der Router global.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Awaitable, Callable, Iterable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    db: AsyncSession
    user: JwtPayload
    group_id: int | None
    conversation_id: UUID | None
    # Virtual Key des Users (für Tools, die selbst den LiteLLM-Proxy aufrufen —
    # z. B. Bildgenerierung — damit Spend/Budget dem User zugerechnet werden).
    litellm_key: str | None = None
    # Der aktive Assistent (oder None). Nötig, damit ein Handler dieselbe Einschränkung
    # durchsetzen kann, die schon im Schema steckt: Das Schema bietet nur die Bildarten
    # dieses Assistenten an — ohne den Assistenten im Kontext könnte ein Modell trotzdem
    # eine andere nennen und die Auswahl des Admins umgehen.
    assistant: Any = None
    # Modell-Allowlist der Nutzer:in (None = unbekannt, dann nicht filtern). Derselbe
    # Grund wie oben: Was das Schema verbirgt, muss der Handler auch ablehnen.
    erlaubte_modelle: set[str] | None = None
    # Sammler für die Zeile „Kontext" unter der Antwort (0.14): Die Suchwerkzeuge hängen
    # an, was sie dem Modell geliefert haben. **Eine Liste je Anfrage**, nicht je Aufruf —
    # der Router legt sie einmal an und reicht sie jedem `ToolContext` durch, denn der
    # entsteht je Werkzeugaufruf neu. `None` = niemand sammelt.
    bausteine: list | None = None
    # Stundenbezug der Konversation (0.15): Vorgabe für `node_id` der Stundenwerkzeuge.
    # Eine Vorgabe, keine Erlaubnis — den Zugang prüft das Werkzeug wie bei jeder Kennung.
    stunde_node_id: UUID | None = None


@dataclass
class SchemaContext:
    """Was ein Schema-Callable über den Chat wissen darf.

    Bewusst **Daten statt Abhängigkeiten**: Die Modell-Freigaben werden vom Aufrufer
    vorab geladen (das ist asynchron) und hier nur durchgereicht, damit der Schema-Bau
    synchron und ohne Netz bleibt.
    """

    assistant: Any = None
    # Für die Nutzer:in freigeschaltete LiteLLM-Modelle, oder None = **unbekannt**.
    # None heißt „nicht filtern", nicht „nichts erlaubt" (vgl. app.litellm.team_models).
    erlaubte_modelle: set[str] | None = None


@dataclass
class ChatTool:
    name: str
    # Die Fähigkeiten (`FAEHIGKEITEN`), zu denen das Werkzeug gehört. Meist genau eine;
    # `get_unit_detail` brauchen Jahres- und Stundenplanung beide. Aktiv ist das Werkzeug,
    # sobald **eine** davon in der Konversation greift.
    groups: frozenset[str]
    # OpenAI-Function-Schema für LiteLLM — entweder fest oder als Funktion des Kontexts.
    #
    # Ein Callable ist nötig, sobald das Schema von der Konfiguration abhängt: Die
    # Bildgenerierung bietet nur die Bildarten an, die dieser Assistent führen darf und
    # deren Modell für diese Nutzer:in freigeschaltet ist. Ein festes Dict könnte das
    # nicht — es entsteht einmal beim Import, lange bevor bekannt ist, in welchem Chat es
    # landet.
    #
    # `tools_for()` löst auf; alles danach sieht ausschließlich fertige Dicts.
    definition: dict | Callable[[SchemaContext], dict]
    handler: Callable[..., Awaitable[Any]]  # async (args: dict, ctx: ToolContext) -> JSON-serialisierbar
    writes: bool = False


# Die Fähigkeiten, die es gibt. Erklärt statt aus der Registry abgeleitet: Die füllt sich
# erst, wenn die Module mit den `register_tool`-Aufrufen importiert wurden (`chat.router`,
# `planning.assistant_tools`). Wer sie ohne diesen Import ausliest — etwa der
# YAML-Import in `api/assistants.py` — bekäme eine leere Menge und verwürfe jede
# Fähigkeit als unbekannt.
#
# `test_registrierte_gruppen_sind_erklaert` hält beides zusammen: Eine neue Gruppe ohne
# Eintrag hier fällt im Test auf, nicht im Betrieb.
FAEHIGKEITEN: frozenset[str] = frozenset({
    "context_search",      # Wissensgraph — immer an, nicht am Assistenten schaltbar
    "planning",            # Unterrichtsplanung (schreibend, nur Lehrkraft der Gruppe)
    "lesson_planning",     # Stundenentwurf (Lehrkraft-Rolle, auch ohne Gruppenbezug)
    "student_planning",   # Planungsdaten lesen (Schüler:innen, mit Gruppenbezug)
    "image_generation",    # Bildgenerierung
})

TOOL_REGISTRY: dict[str, ChatTool] = {}


def register_tool(tool: ChatTool) -> None:
    TOOL_REGISTRY[tool.name] = tool


def _mit_aufgeloestem_schema(tool: ChatTool, ctx: SchemaContext) -> ChatTool:
    """Ersetzt ein Schema-Callable durch das fertige Dict für diesen Kontext.

    Kopiert den Eintrag, statt die Registry zu verändern — die ist prozessweit geteilt und
    darf nicht vom letzten Chat abhängen, der zufällig durchlief.
    """
    if callable(tool.definition):
        return replace(tool, definition=tool.definition(ctx))
    return tool


def tools_for(
    assistant: Any,
    group_id: int | None,
    is_group_teacher: bool,
    erlaubte_modelle: set[str] | None = None,
    *,
    rollen: Iterable[str] = (),
) -> list[ChatTool]:
    """Gibt die für diese Konversation freigeschalteten Tools zurück.

    Schema-Callables sind in der Rückgabe bereits aufgelöst (siehe ``ChatTool.definition``).

    ``assistant`` kann None sein (kein Assistent aktiv). ``erlaubte_modelle`` ist die
    Modell-Allowlist der Nutzer:in oder None (unbekannt → es wird nicht gefiltert).
    ``rollen`` sind die Rollen der Person (``JwtPayload.roles``). Die Stundenplanung hängt
    an der **Rolle**, nicht an der Mitgliedschaft in der Gruppe der Konversation (das ist
    ``is_group_teacher``). Ohne Angabe bleibt sie aus.
    """
    asst_tool_groups: list[str] = getattr(assistant, "tool_groups", None) or []

    # Welche Fähigkeiten in dieser Konversation greifen.
    greifen: set[str] = {"context_search"}
    if "planning" in asst_tool_groups and group_id is not None and is_group_teacher:
        greifen.add("planning")
    if "lesson_planning" in asst_tool_groups and "teacher" in rollen:
        # Ohne Gruppenbezug: Die Stunde kann erst im Chat gefunden werden. Wer sie lesen
        # oder schreiben darf, entscheidet das Werkzeug an der Stunde selbst.
        greifen.add("lesson_planning")
    if "student_planning" in asst_tool_groups and group_id is not None:
        # Read-only Planungsdaten — kein Lehrkraft-Recht nötig, nur Gruppenbezug.
        greifen.add("student_planning")
    if "image_generation" in asst_tool_groups:
        # Bildgenerierung — freigeschaltet, wenn der Assistent die Tool-Gruppe
        # führt. Kein Gruppen-/Lehrkraft-Bezug nötig; die Bild-Modell-Freigabe je
        # Team greift zusätzlich am LiteLLM-Proxy (Schritt 8).
        greifen.add("image_generation")

    # Messschalter (nur development): ausgeblendete Werkzeuge, etwa `get_operatoren` für die
    # Werkzeugwahl-Messung vor seiner Entfernung.
    aus = settings.werkzeuge_aus_menge
    result = [tool for tool in TOOL_REGISTRY.values()
              if tool.groups & greifen and tool.name not in aus]

    schema_ctx = SchemaContext(assistant=assistant, erlaubte_modelle=erlaubte_modelle)
    return [_mit_aufgeloestem_schema(t, schema_ctx) for t in result]
