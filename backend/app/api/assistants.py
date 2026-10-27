import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

import jsonschema
import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select, func, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assistants import ausloeser

from app.auth.dependencies import get_current_user, require_any_role
from app.config import settings
from app.core.paths import aufloesen
from app.auth.jwt import JwtPayload
from app.config import settings
from app.db.models import Assistant, Subject, AssistantDocument, AssistantVisibility
from app.db.session import get_db
from app.upload.extractor import extract_pdf, extract_plaintext

logger = logging.getLogger(__name__)

# ── Schema Caching ───────────────────────────────────────────────────────────

_assistant_schema: Optional[dict] = None


def _get_assistant_schema() -> dict:
    """Laedt und cached das JSON Schema fuer Assistenten-Import."""
    global _assistant_schema
    if _assistant_schema is None:
        with open(aufloesen(settings.assistant_schema_path), encoding="utf-8") as f:
            _assistant_schema = json.load(f)
    return _assistant_schema


# ── Visibility Check ─────────────────────────────────────────────────────────
#
# ⚠️ **Die Regel steht in `app/assistants/sichtbarkeit.py`**, nicht mehr hier. Bis zum
# 27.09.2026 gab es sie zweimal: als Funktion für den Chat (nur Zielgruppe und
# Zeitfenster) und als SQL-Bedingung für diese Liste (zusätzlich `private`). Die
# Scopes kannte keine von beiden — eine Freigabe „für diese Unterrichtsgruppe" war
# deshalb keine Einschränkung.


# ── Common Schemas ───────────────────────────────────────────────────────────

class AssistantSummary(BaseModel):
    id: int
    name: str
    description: Optional[str]
    subject_id: Optional[int]
    audience: str
    scope: str
    visibility: str
    icon: Optional[str]
    tags: Optional[list[str]]
    min_grade: Optional[int]
    max_grade: Optional[int]
    created_by: Optional[str]
    tool_groups: list[str] = []
    model_config = ConfigDict(from_attributes=True)


class AssistantListResponse(BaseModel):
    items: list[AssistantSummary]


# ── Dokument-Schemas ────────────────────────────────────────────────────────

class AssistantDocumentOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    size_bytes: int
    token_estimate: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentUploadResponse(BaseModel):
    id: int
    filename: str
    size_bytes: int
    token_estimate: int
    total_tokens: int
    document_count: int


# ── Hilfsfunktion für Dokument-Konvertierung ────────────────────────────────

def _doc_to_out(doc: AssistantDocument) -> AssistantDocumentOut:
    return AssistantDocumentOut(
        id=doc.id,
        filename=doc.filename,
        mime_type=doc.mime_type,
        size_bytes=doc.size_bytes,
        token_estimate=len(doc.content) // 4,
        created_at=doc.created_at,
    )


# Ein Satz im Vorschlagsdialog (C2) — kein Absatz.
SUGGESTION_TEXT_MAX = 300

# ── Konsolidierte Schemas (ersetzt TeacherAssistant* und Admin Assistant*) ───

class AssistantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    subject_id: Optional[int] = None
    system_prompt: str = Field(min_length=1)
    # Leer/weggelassen = schulweiter Standard (CHAT_DEFAULT_MODEL). Ein gesetzter Wert
    # bindet den Assistenten an dieses Modell — dann folgt er einem Modellwechsel nicht.
    model: str = Field(default="")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    audience: str = Field(default="student")
    scope: str = Field(default="private")
    visibility: str = Field(default="public")
    scope_group_id: Optional[int] = None
    min_grade: Optional[int] = Field(default=None, ge=1, le=13)
    max_grade: Optional[int] = Field(default=None, ge=1, le=13)
    tags: Optional[list[str]] = None
    icon: Optional[str] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    sort_order: int = 0  # nur Admin wertet das aus; Lehrkraefte senden 0 oder nichts
    tool_groups: list[str] = []
    disabled_augmentations: list[str] = []
    # Leer = alle konfigurierten Bildarten (siehe config/image_models.yaml).
    image_kinds: list[str] = []
    # Päckchen AF: Fach-Slugs für den Abschnitt „Operator dieser Aufgabe“; leer = aus.
    operator_faecher: list[str] = []
    # Vorschlag im Chat (Päckchen C1, F4/F5) — ausgewertet erst mit C2.
    suggest: str = "never"
    suggestion_text: Optional[str] = Field(default=None, max_length=SUGGESTION_TEXT_MAX)
    fallbacks: list[int] = []
    trigger_examples: list[str] = []
    trigger_counterexamples: list[str] = []


class AssistantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    subject_id: Optional[int] = None
    system_prompt: Optional[str] = Field(default=None, min_length=1)
    # Ohne `min_length`, damit ein gebundener Assistent per leerem String wieder auf den
    # schulweiten Standard zurückgestellt werden kann. `None` = Feld nicht gesendet
    # (unverändert) und wird unten herausgefiltert — die Spalte ist NOT NULL.
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    audience: Optional[str] = None
    scope: Optional[str] = None
    visibility: Optional[str] = None
    scope_group_id: Optional[int] = None
    min_grade: Optional[int] = Field(default=None, ge=1, le=13)
    max_grade: Optional[int] = Field(default=None, ge=1, le=13)
    tags: Optional[list[str]] = None
    icon: Optional[str] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    sort_order: Optional[int] = None
    tool_groups: Optional[list[str]] = None
    disabled_augmentations: Optional[list[str]] = None
    image_kinds: Optional[list[str]] = None
    operator_faecher: Optional[list[str]] = None
    suggest: Optional[str] = None
    suggestion_text: Optional[str] = Field(default=None, max_length=SUGGESTION_TEXT_MAX)
    fallbacks: Optional[list[int]] = None
    # Ganze Liste; ein Text, der bleibt, behält seinen Vektor (`ausloeser.setze`).
    trigger_examples: Optional[list[str]] = None
    trigger_counterexamples: Optional[list[str]] = None


class AssistantResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    subject_id: Optional[int]
    system_prompt: str
    model: str
    temperature: Optional[float]
    max_tokens: Optional[int]
    status: str
    audience: str
    scope: str
    visibility: str
    scope_group_id: Optional[int]
    scope_pending: Optional[str]
    min_grade: Optional[int]
    max_grade: Optional[int]
    tags: Optional[list[str]]
    icon: Optional[str]
    available_from: Optional[datetime]
    available_until: Optional[datetime]
    sort_order: int
    created_by: Optional[str]
    creator_role: str
    reject_reason: Optional[str]
    # Löschantrag (Alembic 0076) — nur schulweit belegt; siehe `request_deletion`.
    deletion_requested_at: Optional[datetime] = None
    deletion_reason: Optional[str] = None
    updated_by_pseudonym: Optional[str]
    created_at: datetime
    updated_at: datetime
    tool_groups: list[str] = []
    disabled_augmentations: list[str] = []
    image_kinds: list[str] = []
    operator_faecher: list[str] = []
    documents: list[AssistantDocumentOut] = []
    suggest: str = "never"
    suggestion_text: Optional[str] = None
    fallbacks: list[int] = []
    # **`None` heißt „nicht geladen“**, nicht „keine“: Wie die Dokumente füllt nur die
    # Einzelansicht (und Anlegen, Ändern, Import) die Listen — in Übersichten kosteten sie
    # eine Abfrage je Zeile und würden nicht gebraucht.
    trigger_examples: Optional[list[str]] = None
    trigger_counterexamples: Optional[list[str]] = None

    model_config = ConfigDict(from_attributes=True)


class AssistantFullListResponse(BaseModel):
    items: list[AssistantResponse]
    total: int


class AssistantImportResponse(AssistantResponse):
    """Wie ``AssistantResponse``, plus was beim Import nicht übernommen wurde.

    Eigenes Modell statt eines Zusatzfeldes an ``AssistantResponse``: Der Hinweis gehört
    zum Vorgang, nicht zum Assistenten — in jeder Liste mitgeführt wäre er sinnlos.
    """

    hinweise: list[str] = []


# ── Import/Export Mapping ────────────────────────────────────────────────────


def _grades_list(min_grade: Optional[int], max_grade: Optional[int]) -> Optional[list[int]]:
    """Erzeugt eine Liste der Jahrgaenge."""
    if min_grade is None and max_grade is None:
        return None
    if min_grade == max_grade:
        return [min_grade]
    return list(range(min_grade or 0, (max_grade or 0) + 1))


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parsed ISO-8601 string to aware datetime (UTC). Returns None on error."""
    if not value or not value.strip():
        return None
    try:
        # Replace 'T' with space for compatibility
        normalized = value.replace('T', ' ')
        # Try parsing with timezone
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _assistant_to_yaml(
    assistant: Assistant,
    subject_slug: Optional[str],
    ausloeser_listen: Optional[dict[str, list[str]]] = None,
    fallback_namen: Optional[list[str]] = None,
) -> str:
    """Serialisiert Assistent in YAML-Format.

    Rückfälle stehen **mit Namen** im YAML, nicht mit ID: Eine ID gilt nur in dieser
    Datenbank, der Export soll aber auch in einer anderen Installation tragen.
    """
    listen = ausloeser_listen or {}
    data = {
        "metadata": {
            "name": assistant.name,
            "description": assistant.description,
            "subject": subject_slug,
            "grades": _grades_list(assistant.min_grade, assistant.max_grade),
            "tags": assistant.tags or [],
            "audience": assistant.audience,
            "visibility": assistant.visibility,
            "available_from": assistant.available_from.isoformat() if assistant.available_from else None,
            "available_until": assistant.available_until.isoformat() if assistant.available_until else None,
            "updated": assistant.updated_at.date().isoformat(),
            # Vorschlag (C1) — nur, was vom Vorgabewert abweicht.
            "suggest": assistant.suggest if assistant.suggest != "never" else None,
            "suggestion_text": assistant.suggestion_text,
            "trigger_examples": listen.get(ausloeser.BEISPIEL) or None,
            "trigger_counterexamples": listen.get(ausloeser.GEGENBEISPIEL) or None,
            "fallbacks": fallback_namen or None,
        },
        "config": {
            # Leer = schulweiter Standard. Weglassen statt `""`: Das Schema verlangt
            # `minLength: 1`, ein solcher Export ließ sich sonst nicht wieder einspielen.
            "model": assistant.model or None,
            "temperature": float(assistant.temperature) if assistant.temperature is not None else None,
            "max_tokens": assistant.max_tokens,
            "system_prompt": assistant.system_prompt,
            # Fähigkeiten und Bildarten gehören zu `config`, nicht zu `metadata`: Sie
            # beschreiben, was der Assistent kann, nicht woher er kommt. Ohne sie verlor
            # ein Export-Import-Durchlauf still Unterrichtsplanung, Bildgenerierung und
            # die Bildart-Auswahl — der Assistent sah identisch aus und konnte weniger.
            "tool_groups": list(assistant.tool_groups or []) or None,
            "image_kinds": list(assistant.image_kinds or []) or None,
            "operator_faecher": list(assistant.operator_faecher or []) or None,
        },
    }
    # None-Werte aus config entfernen
    data["config"] = {k: v for k, v in data["config"].items() if v is not None}
    data["metadata"] = {k: v for k, v in data["metadata"].items() if v is not None}
    
    # Marktplatz-Felder aus import_metadata uebernehmen
    if assistant.import_metadata:
        for k in {"author", "license", "version", "created"}:
            if k in assistant.import_metadata:
                data["metadata"][k] = assistant.import_metadata[k]
    
    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


def bekannte_faehigkeiten() -> set[str]:
    """Fähigkeiten, die es gibt (`app.chat.tools.FAEHIGKEITEN`).

    Bewusst **nicht** aus `TOOL_REGISTRY` abgeleitet: Die füllt sich erst beim Import der
    Module mit den `register_tool`-Aufrufen. Hier gelesen käme je nach Importreihenfolge
    eine leere Menge heraus — und dann verwürfe der Import jede Fähigkeit als unbekannt.
    """
    from app.chat.tools import FAEHIGKEITEN

    return set(FAEHIGKEITEN)


def bekannte_bildarten() -> set[str]:
    """Bildart-IDs aus `config/image_models.yaml` dieser Installation."""
    from app.chat.image_models import alle_bildarten

    return {bildart.id for bildart in alle_bildarten()}


def _uebernimm_bekannte(
    werte: Any, bekannt: set[str], bezeichnung: str, hinweise: list[str]
) -> list[str]:
    """Behält, was hier existiert; nennt den Rest im Ergebnis.

    Unbekanntes still zu schlucken wäre die schlechtere Wahl: Der Assistent erschiene
    vollständig und wäre es nicht — genau der Fehler, den dieser Import gerade behebt.
    Abzuweisen wäre die andere: Ein Assistent aus einer Schule mit einer Bildart „Comic"
    ließe sich dann hier gar nicht importieren, obwohl alles Übrige passt.
    """
    if not isinstance(werte, list):
        return []
    behalten = [w for w in werte if w in bekannt]
    verworfen = [str(w) for w in werte if w not in bekannt]
    if verworfen:
        hinweise.append(
            f"{bezeichnung} übergangen (hier nicht vorhanden): {', '.join(sorted(verworfen))}"
        )
    return behalten


def _yaml_to_assistant_fields(
    data: dict, subject_id: Optional[int], hinweise: Optional[list[str]] = None
) -> dict:
    """Mappt YAML-Daten auf Assistenten-Felder.

    ``hinweise`` sammelt, was übergangen wurde (unbekannte Fähigkeiten oder Bildarten).
    """
    meta = data["metadata"]
    config = data["config"]
    grades = meta.get("grades") or []
    gesammelt = hinweise if hinweise is not None else []
    return {
        "tool_groups": _uebernimm_bekannte(
            config.get("tool_groups") or [], bekannte_faehigkeiten(), "Fähigkeiten", gesammelt
        ),
        "image_kinds": _uebernimm_bekannte(
            config.get("image_kinds") or [], bekannte_bildarten(), "Bildarten", gesammelt
        ),
        "name": meta["name"].strip(),
        "description": meta.get("description"),
        "subject_id": subject_id,
        "system_prompt": config["system_prompt"].strip(),
        "model": (config.get("model") or "").strip(),
        "temperature": config.get("temperature"),
        "max_tokens": config.get("max_tokens"),
        "audience": meta["audience"],
        "scope": "private",
        "visibility": meta.get("visibility", "public"),
        "suggest": meta.get("suggest") or "never",
        "suggestion_text": (meta.get("suggestion_text") or "").strip() or None,
        "min_grade": min(grades) if grades else None,
        "max_grade": max(grades) if grades else None,
        "tags": meta.get("tags"),
        "available_from": _parse_iso(meta.get("available_from")),
        "available_until": _parse_iso(meta.get("available_until")),
        "import_metadata": {
            k: meta.get(k)
            for k in ("author", "license", "version", "created")
            if meta.get(k) is not None
        } or None,
    }


# ── Validation ──────────────────────────────────────────────────────────────

VALID_AUDIENCES = {"student", "teacher", "all"}
VALID_SCOPES = {
    "private", "subject_department", "teachers", "activity_group",
    "teaching_group", "grade", "all_students", "all",
}
VALID_VISIBILITIES = {"public", "private", "hidden"}
VALID_SUGGEST = {"specific", "fallback", "never"}
# Der Dialog in C2 zeigt höchstens zwei Rückfälle; drei lassen einem Gelöschten Ersatz.
MAX_FALLBACKS = 3
GROUP_SCOPES = {"subject_department", "activity_group", "teaching_group"}
# ⚠️ **`teachers` gehört dazu** (Entscheidung Jan, 25.09.2026). Der Scope „Alle
# Lehrkräfte" erreicht das ganze Kollegium; er stand bis dahin weder in dieser Menge noch
# in `GROUP_SCOPES` und entstand deshalb ohne Freigabe und ohne Bearbeitungsschutz.
#
# ⚠️ **Diese Menge gibt es ein zweites Mal im Frontend** (`$lib/assistant_lebenszyklus.js`),
# wo sie über Bearbeitbarkeit und Löschen entscheidet. Laufen die beiden auseinander, bietet die
# Oberfläche ein Feld an, das der Server ablehnt — genau der Fall, der bis zum 25.09.2026
# bestand. Ein Wächter hält sie zusammen (`tests/unit/test_assistant_lebenszyklus.py`).
SCHOOLWIDE_SCOPES = {"teachers", "grade", "all_students", "all"}


def _is_student_visible_image_assistant(
    audience: Optional[str], tool_groups: Optional[list[str]]
) -> bool:
    """True, wenn der Assistent Bilder erzeugt UND Schüler:innen erreicht.

    Jugendschutz-Prüfpunkt (Phase 16 Schritt 9): solche Assistenten sind sensibler
    als reine Text-Assistenten und brauchen eine bewusste Admin-Freigabe.
    """
    return (
        "image_generation" in (tool_groups or [])
        and audience in {"student", "all"}
    )


def _initial_status(
    scope: str,
    creator_role: str,
    audience: Optional[str] = None,
    tool_groups: Optional[list[str]] = None,
) -> str:
    """Bestimmt den initialen Status eines Assistenten bei Erstellung.

    Admins starten immer im Draft. Lehrkraefte erhalten sofort 'active' fuer
    private und gruppen-beschraenkte Scopes; schulweite Scopes koennen eine
    Admin-Freigabe erfordern (abhaengig von teacher_schoolwide_sharing_requires_admin).

    Ausnahme (Jugendschutz-Prüfpunkt, Phase 16 Schritt 9): schulweite Bild-Assistenten,
    die Schüler:innen erreichen, gehen IMMER in 'pending_review' — unabhaengig vom
    teacher_schoolwide_sharing_requires_admin-Schalter. Gruppen-/private Bild-Assistenten
    bleiben selbst-freigebbar (die Lehrkraft verantwortet ihre eigene Gruppe).
    """
    if creator_role == "admin":
        return "draft"
    if scope in SCHOOLWIDE_SCOPES:
        if _is_student_visible_image_assistant(audience, tool_groups):
            return "pending_review"
        return "pending_review" if settings.teacher_schoolwide_sharing_requires_admin else "active"
    return "active"


def validate_assistant_fields(
    name: Optional[str] = None,
    system_prompt: Optional[str] = None,
    audience: Optional[str] = None,
    scope: Optional[str] = None,
    visibility: Optional[str] = None,
    scope_group_id: Optional[int] = None,
    min_grade: Optional[int] = None,
    max_grade: Optional[int] = None,
    available_from: Optional[datetime] = None,
    available_until: Optional[datetime] = None,
    suggest: Optional[str] = None,
) -> None:
    """Validiert Business-Regeln fuer Assistenten. Wirft HTTPException(422)."""
    if name is not None and not name.strip():
        raise HTTPException(status_code=422, detail="name darf nicht leer sein")
    if system_prompt is not None and not system_prompt.strip():
        raise HTTPException(status_code=422, detail="system_prompt darf nicht leer sein")
    if audience is not None and audience not in VALID_AUDIENCES:
        raise HTTPException(status_code=422, detail="Ungültiger audience-Wert")
    if scope is not None and scope not in VALID_SCOPES:
        raise HTTPException(status_code=422, detail="Ungültiger scope-Wert")
    if visibility is not None and visibility not in VALID_VISIBILITIES:
        raise HTTPException(status_code=422, detail="Ungültiger visibility-Wert")
    if suggest is not None and suggest not in VALID_SUGGEST:
        raise HTTPException(status_code=422, detail="Ungültiger suggest-Wert")
    if scope is not None and scope in GROUP_SCOPES and scope_group_id is None:
        raise HTTPException(
            status_code=422, detail="Gruppen-Scope erfordert eine scope_group_id"
        )
    if scope is not None and scope not in GROUP_SCOPES and scope_group_id is not None:
        raise HTTPException(
            status_code=422, detail="scope_group_id darf nur bei Gruppen-Scopes gesetzt sein"
        )
    if audience == "teacher" and scope in {"all_students", "all"}:
        raise HTTPException(
            status_code=422,
            detail="teacher-Assistenten dürfen nicht für Schüler:innen sichtbar sein",
        )
    if available_from is not None and available_until is not None:
        if available_from >= available_until:
            raise HTTPException(
                status_code=422, detail="available_from muss vor available_until liegen"
            )
    if min_grade is not None and max_grade is not None:
        if min_grade > max_grade:
            raise HTTPException(
                status_code=422, detail="min_grade darf nicht größer als max_grade sein"
            )


# ── Vorschlag: Auslöser-Beispiele und Rückfälle (Päckchen C1, Schritt 3) ─────


def _bereinigte_ausloeser(beispiele, gegenbeispiele) -> dict[str, Optional[list[str]]]:
    """Beide Listen bereinigt; ``None`` bleibt ``None`` (= nicht geändert)."""
    try:
        return {
            ausloeser.BEISPIEL: (
                None if beispiele is None else ausloeser.bereinige(beispiele, ausloeser.BEISPIEL)
            ),
            ausloeser.GEGENBEISPIEL: (
                None if gegenbeispiele is None
                else ausloeser.bereinige(gegenbeispiele, ausloeser.GEGENBEISPIEL)
            ),
        }
    except ausloeser.AusloeserFehler as fehler:
        raise HTTPException(status_code=422, detail=str(fehler))


async def _gepruefte_fallbacks(
    db: AsyncSession, ids: list[int], eigene_id: Optional[int]
) -> list[int]:
    """Dubletten weg; jede ID muss ein anderer, vorhandener Assistent sein."""
    eindeutig = list(dict.fromkeys(ids))
    if eigene_id is not None and eigene_id in eindeutig:
        raise HTTPException(
            status_code=422, detail="Ein Assistent kann nicht sein eigener Rückfall sein"
        )
    if len(eindeutig) > MAX_FALLBACKS:
        raise HTTPException(
            status_code=422, detail=f"Höchstens {MAX_FALLBACKS} Rückfall-Assistenten"
        )
    if eindeutig:
        vorhanden = set(
            (await db.execute(select(Assistant.id).where(Assistant.id.in_(eindeutig)))).scalars()
        )
        fehlen = [i for i in eindeutig if i not in vorhanden]
        if fehlen:
            raise HTTPException(
                status_code=422,
                detail=f"Rückfall-Assistent nicht gefunden: {', '.join(map(str, fehlen))}",
            )
    return eindeutig


async def _gepruefte_operator_faecher(db: AsyncSession, slugs: list[str]) -> list[str]:
    """Klein geschrieben, ohne Dubletten; jedes Fach muss es hier geben."""
    eindeutig = list(dict.fromkeys(s.strip().lower() for s in slugs if s and s.strip()))
    if eindeutig:
        vorhanden = set(
            (await db.execute(select(Subject.slug).where(Subject.slug.in_(eindeutig)))).scalars()
        )
        fehlen = [s for s in eindeutig if s not in vorhanden]
        if fehlen:
            raise HTTPException(
                status_code=422, detail=f"Fach nicht gefunden: {', '.join(fehlen)}"
            )
    return eindeutig


async def _speichere_ausloeser(
    db: AsyncSession, assistant_id: int, listen: dict[str, Optional[list[str]]]
) -> int:
    """Gleicht die gesendeten Listen ab; gibt die Zahl neu einzubettender Texte zurück."""
    neu = 0
    for art, texte in listen.items():
        if texte is not None:
            neu += await ausloeser.setze(db, assistant_id, art, texte)
    return neu


def _einbetten_nach_speichern(
    hintergrund: BackgroundTasks, db: AsyncSession, assistant_id: int
) -> None:
    """Gleich einbetten statt erst nachts — eigene Sitzung am selben Engine (wie 0.14)."""
    hintergrund.add_task(
        ausloeser.einbetten_im_hintergrund,
        assistant_id,
        async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False),
    )


async def _mit_ausloesern(
    db: AsyncSession, antwort: AssistantResponse
) -> AssistantResponse:
    listen = await ausloeser.lade(db, antwort.id)
    return antwort.model_copy(update={
        "trigger_examples": listen[ausloeser.BEISPIEL],
        "trigger_counterexamples": listen[ausloeser.GEGENBEISPIEL],
    })


async def _fallbacks_nach_namen(
    db: AsyncSession, namen: list, hinweise: list[str]
) -> list[int]:
    """Rückfälle eines YAML-Imports: Name → ID, nur bei genau einem Treffer.

    Was sich nicht eindeutig zuordnen lässt, wird übergangen und genannt — wie eine
    unbekannte Fähigkeit (`_uebernimm_bekannte`): Der Import soll nicht daran scheitern,
    dass es den Rückfall hier (noch) nicht gibt.
    """
    ids: list[int] = []
    for name in dict.fromkeys(str(n).strip() for n in namen if str(n).strip()):
        treffer = list(
            (await db.execute(select(Assistant.id).where(Assistant.name == name))).scalars()
        )
        if len(treffer) == 1:
            ids.append(treffer[0])
        else:
            grund = "nicht vorhanden" if not treffer else "Name mehrfach vergeben"
            hinweise.append(f"Rückfall-Assistent übergangen ({grund}): {name}")
    return ids[:MAX_FALLBACKS]


# ── Permission Helpers ───────────────────────────────────────────────────────

async def _load_and_authorize_assistant(assistant_id: int, current_user: JwtPayload, db: AsyncSession) -> Assistant:
    """Lädt einen Assistenten und prüft die Berechtigung. Wirft 404 oder 403."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    
    is_admin = "admin" in current_user.roles
    if not is_admin and assistant.created_by != current_user.sub:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    return assistant


def _check_assistant_access(assistant: Assistant, current_user: JwtPayload, is_admin: bool) -> None:
    """Prueft Zugriffsrechte auf einen Assistenten."""
    if not is_admin and assistant.created_by != current_user.sub:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")


def _check_assistant_update_permission(assistant: Assistant, current_user: JwtPayload, is_admin: bool) -> None:
    """Prueft Berechtigung fuer PATCH-Operationen.

    ⚠️ **Die Reichweite entscheidet, nicht der Status** (seit 25.09.2026). Vorher galt
    „Bearbeiten nur im Entwurf" — und in `draft` kam der Assistent einer Lehrkraft
    **nie**: Private, Gruppen- und Fachschafts-Assistenten entstehen sofort als `active`
    (`_initial_status`, so gewollt, keine Freigabe). Sie waren damit für ihre Urheberin
    eingefroren: kein Ändern, kein Abschalten, kein Löschen, nur über einen Admin.

    Aufgefallen ist es lange nicht, weil die **Oberfläche die Regel schon richtig kannte**
    (`AssistantEditor.svelte`: `active` außerhalb der schulweiten Scopes ist editierbar) —
    die Felder waren bedienbar, erst das Speichern antwortete mit 409. Wer beim Testen
    zugleich Admin ist, trifft die Sperre nie.

    Schulweit bleibt es beim Entwurf: Dort hat jemand den Prompt geprüft, und eine
    stille Änderung danach machte die Prüfung wertlos.
    """
    if not is_admin:
        if assistant.created_by != current_user.sub:
            raise HTTPException(status_code=403, detail="Keine Berechtigung")
        if assistant.scope in SCHOOLWIDE_SCOPES and assistant.status != "draft":
            raise HTTPException(
                status_code=409,
                detail="Schulweite Assistenten lassen sich nur im Entwurf bearbeiten. "
                       "Ziehen Sie die Einreichung zurueck oder beantragen Sie die "
                       "Loeschung.",
            )


def _check_assistant_delete_permission(assistant: Assistant, current_user: JwtPayload, is_admin: bool) -> None:
    """Prueft Berechtigung fuer DELETE-Operationen.

    ⚠️ **Eigene nicht schulweite löscht auch ein Admin jederzeit** (0.15). Die Statusregel
    unten gehört zur Verwaltung; in „Meine Assistenten" ist ein Admin eine Lehrkraft
    (Rollenmodell) — sonst verweigerte der Server ihm den eigenen privaten Assistenten, den
    jede Lehrkraft löschen darf.
    """
    if is_admin:
        if assistant.created_by == current_user.sub and assistant.scope not in SCHOOLWIDE_SCOPES:
            return
        if assistant.status not in ("draft", "disabled", "archived"):
            raise HTTPException(
                status_code=409,
                detail="Nur Assistenten im Status 'draft', 'disabled' oder 'archived' koennen geloescht werden.",
            )
    else:
        if assistant.created_by != current_user.sub:
            raise HTTPException(status_code=403, detail="Keine Berechtigung")
        # Eigene, nicht schulweite Assistenten: jederzeit. Die Konversationen bleiben —
        # `conversations.assistant_id` und `messages.assistant_id` stehen auf
        # `ON DELETE SET NULL`.
        if assistant.scope in SCHOOLWIDE_SCOPES and assistant.status not in (
            "draft", "pending_review",
        ):
            raise HTTPException(
                status_code=409,
                detail="Ein freigegebener schulweiter Assistent wird nicht selbst "
                       "geloescht - beantragen Sie die Loeschung.",
            )


router = APIRouter(prefix="/assistants", tags=["assistants"])


# ── Public Endpoints ─────────────────────────────────────────────────────────

@router.get("", response_model=AssistantListResponse)
async def list_assistants(
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssistantListResponse:
    from app.assistants.sichtbarkeit import lade_zugang, sichtbar_klausel

    zugang = await lade_zugang(db, current_user)
    stmt = (
        select(Assistant)
        .where(sichtbar_klausel(zugang))
        .order_by(Assistant.sort_order.asc(), Assistant.name.asc())
    )

    result = await db.execute(stmt)
    assistants = result.scalars().all()

    return AssistantListResponse(
        items=[AssistantSummary.model_validate(a) for a in assistants]
    )


# ── Eigene Assistenten ───────────────────────────────────────────────────────
# Muss VOR /{assistant_id} registriert werden, sonst matched FastAPI "mine" als int-ID.

@router.get("/mine", response_model=AssistantFullListResponse)
async def list_my_assistants(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantFullListResponse:
    """Gibt alle eigenen Assistenten zurueck (alle Status)."""
    stmt = select(Assistant).where(Assistant.created_by == current_user.sub)
    if status is not None:
        stmt = stmt.where(Assistant.status == status)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar()

    stmt = stmt.order_by(Assistant.updated_at.desc()).limit(limit).offset(offset)
    assistants = (await db.execute(stmt)).scalars().all()

    return AssistantFullListResponse(
        items=[AssistantResponse.model_validate(a) for a in assistants],
        total=total,
    )


# ── Eigener Stundenassistent (0.15) ──────────────────────────────────────────
#
# Vorlage ist der schulweite Stundenassistent selbst, keine Datei: Admins pflegen seinen
# Prompt im Editor, und die Kopie nimmt die Fassung von heute mit. Sie folgt späteren
# Änderungen nicht — sie gehört der Lehrkraft, die ihre Planungsgewohnheiten einträgt.

#: Name der Kopie; die laufende Nummer hängt `_naechster_name` an.
EIGENER_STUNDENASSISTENT = "Mein Stundenassistent"


async def _stundenassistent_vorlage(db: AsyncSession, current_user: JwtPayload) -> Optional[Assistant]:
    """Der erste schulweite Assistent mit Stundenplanung, den diese Person benutzen darf.

    „Erster" in der Reihenfolge der Assistentenliste. Gefiltert mit `sichtbar_klausel`: Kopiert
    wird nur, was die Person ohnehin benutzen darf — ein Entwurf oder ein abgelaufener
    Assistent gibt keine Vorlage ab.
    """
    from app.assistants.sichtbarkeit import lade_zugang, sichtbar_klausel

    zugang = await lade_zugang(db, current_user)
    return (await db.execute(
        select(Assistant)
        .where(
            sichtbar_klausel(zugang),
            Assistant.scope.in_(sorted(SCHOOLWIDE_SCOPES)),
            Assistant.tool_groups.contains(["lesson_planning"]),
        )
        .order_by(Assistant.sort_order.asc(), Assistant.name.asc(), Assistant.id.asc())
        .limit(1)
    )).scalar_one_or_none()


async def _naechster_name(db: AsyncSession, pseudonym: str) -> str:
    """„Mein Stundenassistent 2", wenn es die 1 schon gibt — umbenannte zählen nicht mehr."""
    namen = (await db.execute(
        select(Assistant.name).where(
            Assistant.created_by == pseudonym,
            Assistant.name.like(f"{EIGENER_STUNDENASSISTENT} %"),
        )
    )).scalars()
    muster = re.compile(rf"{re.escape(EIGENER_STUNDENASSISTENT)} (\d+)")
    nummern = [int(m.group(1)) for n in namen if (m := muster.fullmatch(n))]
    return f"{EIGENER_STUNDENASSISTENT} {max(nummern, default=0) + 1}"


class EigenerStundenassistentRequest(BaseModel):
    # Das Fach der Stunde, aus der heraus angelegt wird (Entwurfsansicht); ändern oder
    # entfernen lässt es sich im Editor.
    subject_id: Optional[int] = None


@router.post("/eigener-stundenassistent", response_model=AssistantResponse, status_code=201)
async def eigenen_stundenassistenten_anlegen(
    request: Optional[EigenerStundenassistentRequest] = None,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Legt einen privaten Stundenassistenten mit dem aktuellen Prompt des schulweiten an.

    Sofort aktiv, auch für Admins: Er ist privat, geprüft werden muss nichts. Die Fähigkeit
    setzt der Endpunkt — im Editor kann das nur ein Admin, und weil die Lehrkraft beim
    Speichern `tool_groups` nicht mitschickt, bleibt sie stehen. Mehrfaches Anlegen ist
    erlaubt (etwa einer je Fach).
    """
    subject_id = request.subject_id if request else None
    if subject_id is not None and await db.get(Subject, subject_id) is None:
        raise HTTPException(status_code=422, detail="Unbekanntes Fach")
    vorlage = await _stundenassistent_vorlage(db, current_user)
    if vorlage is None:
        raise HTTPException(
            status_code=404,
            detail="Es ist kein schulweiter Stundenassistent eingerichtet, der als Vorlage "
                   "dienen kann. Das übernimmt die Administration.",
        )

    jetzt = datetime.now(timezone.utc)
    assistant = Assistant(
        name=await _naechster_name(db, current_user.sub),
        description=f"Eigene Fassung von „{vorlage.name}“, angelegt am {date.today():%d.%m.%Y}.",
        subject_id=subject_id,
        system_prompt=vorlage.system_prompt,
        # Modell und Parameter gehören zur Vorlage: Ist sie bewusst an ein Modell gebunden,
        # plant die Kopie sonst mit einem anderen.
        model=vorlage.model,
        temperature=vorlage.temperature,
        max_tokens=vorlage.max_tokens,
        status="active",
        audience="teacher",
        scope="private",
        tool_groups=["lesson_planning"],
        creator_role="admin" if "admin" in current_user.roles else "teacher",
        created_by=current_user.sub,
        updated_by_pseudonym=current_user.sub,
        created_at=jetzt,
        updated_at=jetzt,
    )
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    return AssistantResponse.model_validate(assistant)


# ── Einzelabruf ─────────────────────────────────────────────────────────────

@router.get("/{assistant_id}", response_model=AssistantResponse)
async def get_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Gibt einen einzelnen Assistenten zurueck. Nur Eigentuemer oder Admin."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")

    is_admin = "admin" in current_user.roles
    _check_assistant_access(assistant, current_user, is_admin)

    # Dokumente für den Assistenten laden
    docs = (
        await db.execute(
            select(AssistantDocument)
            .where(AssistantDocument.assistant_id == assistant_id)
            .order_by(AssistantDocument.created_at)
        )
    ).scalars().all()

    response = await _mit_ausloesern(db, AssistantResponse.model_validate(assistant))
    return response.model_copy(update={"documents": [_doc_to_out(d) for d in docs]})


@router.post("", response_model=AssistantResponse, status_code=201)
async def create_assistant(
    request: AssistantCreate,
    hintergrund: BackgroundTasks,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Erstellt einen neuen Assistenten im Entwurfsstatus."""
    validate_assistant_fields(
        name=request.name,
        system_prompt=request.system_prompt,
        audience=request.audience,
        scope=request.scope,
        visibility=request.visibility,
        scope_group_id=request.scope_group_id,
        min_grade=request.min_grade,
        max_grade=request.max_grade,
        available_from=request.available_from,
        available_until=request.available_until,
        suggest=request.suggest,
    )
    listen = _bereinigte_ausloeser(request.trigger_examples, request.trigger_counterexamples)
    fallbacks = await _gepruefte_fallbacks(db, request.fallbacks, None)
    operator_faecher = await _gepruefte_operator_faecher(db, request.operator_faecher)

    creator_role = "admin" if "admin" in current_user.roles else "teacher"
    sort_order = request.sort_order if "admin" in current_user.roles else 0
    initial_status = _initial_status(
        request.scope, creator_role, request.audience, request.tool_groups
    )

    assistant = Assistant(
        name=request.name,
        description=request.description,
        subject_id=request.subject_id,
        system_prompt=request.system_prompt,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        status=initial_status,
        audience=request.audience,
        scope=request.scope,
        visibility=request.visibility,
        scope_group_id=request.scope_group_id,
        min_grade=request.min_grade,
        max_grade=request.max_grade,
        tags=request.tags,
        icon=request.icon,
        available_from=request.available_from,
        available_until=request.available_until,
        tool_groups=request.tool_groups,
        disabled_augmentations=request.disabled_augmentations,
        image_kinds=request.image_kinds,
        operator_faecher=operator_faecher,
        suggest=request.suggest,
        suggestion_text=(request.suggestion_text or "").strip() or None,
        fallbacks=fallbacks,
        sort_order=sort_order,
        creator_role=creator_role,
        created_by=current_user.sub,
        updated_by_pseudonym=current_user.sub,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(assistant)
    await db.flush()
    neu = await _speichere_ausloeser(db, assistant.id, listen)
    await db.commit()
    await db.refresh(assistant)
    if neu:
        _einbetten_nach_speichern(hintergrund, db, assistant.id)
    return await _mit_ausloesern(db, AssistantResponse.model_validate(assistant))


@router.patch("/{assistant_id}", response_model=AssistantResponse)
async def update_assistant(
    assistant_id: int,
    request: AssistantUpdate,
    hintergrund: BackgroundTasks,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Aktualisiert einen Assistenten."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    
    is_admin = "admin" in current_user.roles
    _check_assistant_update_permission(assistant, current_user, is_admin)
    
    update_data = request.model_dump(exclude_unset=True)
    validate_assistant_fields(**{k: update_data.get(k) for k in (
        "name", "system_prompt", "audience", "scope", "visibility", "scope_group_id",
        "min_grade", "max_grade", "available_from", "available_until", "suggest",
    )})
    # Die Listen sind keine Spalten — sie gehen in die eigene Tabelle.
    listen = _bereinigte_ausloeser(
        update_data.pop("trigger_examples", None),
        update_data.pop("trigger_counterexamples", None),
    )
    if "fallbacks" in update_data:
        update_data["fallbacks"] = await _gepruefte_fallbacks(
            db, update_data["fallbacks"] or [], assistant.id
        )
    if "operator_faecher" in update_data:
        update_data["operator_faecher"] = await _gepruefte_operator_faecher(
            db, update_data["operator_faecher"] or []
        )
    if "suggestion_text" in update_data:
        update_data["suggestion_text"] = (update_data["suggestion_text"] or "").strip() or None
    # `null` hieße hier „Spalte leeren“, und `suggest` ist NOT NULL.
    if update_data.get("suggest", "") is None:
        update_data.pop("suggest")
    
    # sort_order: nur Admin kann das aendern
    if not is_admin and "sort_order" in update_data:
        update_data["sort_order"] = assistant.sort_order

    # Scope-Aenderung durch Lehrkraft: Status automatisch anpassen
    if not is_admin and "scope" in update_data:
        new_scope = update_data["scope"]
        # Effektive audience/tool_groups (geaenderte oder bestehende) fuer den
        # Jugendschutz-Pruefpunkt bei Bild-Assistenten beruecksichtigen.
        eff_audience = update_data.get("audience", assistant.audience)
        eff_tool_groups = update_data.get("tool_groups", assistant.tool_groups)
        new_status = _initial_status(new_scope, "teacher", eff_audience, eff_tool_groups)
        # Nur umschalten wenn der Assistent nicht bereits im Ziel-Status ist
        if assistant.status in ("active", "pending_review") and new_status != assistant.status:
            update_data["status"] = new_status
        # Wechsel von schulweit → privat/gruppe: reject_reason loeschen
        if new_status == "active" and assistant.reject_reason:
            update_data["reject_reason"] = None

    # `model: null` würde die NOT-NULL-Spalte verletzen; zum Zurücksetzen auf den
    # schulweiten Standard ist der leere String vorgesehen.
    if update_data.get("model") is None:
        update_data.pop("model", None)

    for field, value in update_data.items():
        setattr(assistant, field, value)
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub
    neu = await _speichere_ausloeser(db, assistant.id, listen)

    await db.commit()
    await db.refresh(assistant)
    if neu:
        _einbetten_nach_speichern(hintergrund, db, assistant.id)
    return await _mit_ausloesern(db, AssistantResponse.model_validate(assistant))


@router.delete("/{assistant_id}", status_code=204)
async def delete_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Loescht einen Assistenten."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    
    is_admin = "admin" in current_user.roles
    _check_assistant_delete_permission(assistant, current_user, is_admin)

    # Aus den Rückfall-Listen der anderen nehmen — ein Array kennt keinen Fremdschlüssel.
    await db.execute(
        text(
            "UPDATE assistants SET fallbacks = array_remove(fallbacks, :id)"
            " WHERE :id = ANY(fallbacks)"
        ),
        {"id": assistant_id},
    )
    await db.delete(assistant)
    await db.commit()


@router.post("/{assistant_id}/submit", response_model=AssistantResponse)
async def submit_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Reicht einen Entwurf zur Admin-Freigabe ein."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    if assistant.created_by != current_user.sub:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    if assistant.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Nur Assistenten im Status 'draft' koennen eingereicht werden.",
        )

    assistant.status = "pending_review"
    assistant.reject_reason = None   # vorherige Ablehnung loeschen
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub

    await db.commit()
    await db.refresh(assistant)
    return AssistantResponse.model_validate(assistant)


async def _eigener(db: AsyncSession, assistant_id: int, pseudonym: str) -> Assistant:
    """Der eigene Assistent — oder 404/403. Grundlage der Lebenszyklus-Endpunkte."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    if assistant.created_by != pseudonym:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    return assistant


@router.post("/{assistant_id}/withdraw", response_model=AssistantResponse)
async def withdraw_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Zieht eine Einreichung zurueck: `pending_review` → `draft`.

    ⚠️ **Der Rueckweg fehlte.** Eingereicht werden konnte ein Entwurf immer, zurueck kam
    er nicht — die Lehrkraft hatte nur die teure Antwort: loeschen und neu schreiben. Der
    Text der Bearbeitungssperre verwies sogar auf ein Zurueckziehen, das es nicht gab.
    """
    assistant = await _eigener(db, assistant_id, current_user.sub)
    if assistant.status != "pending_review":
        raise HTTPException(
            status_code=409,
            detail="Nur eingereichte Assistenten koennen zurueckgezogen werden.",
        )
    assistant.status = "draft"
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub
    await db.commit()
    await db.refresh(assistant)
    return AssistantResponse.model_validate(assistant)


@router.post("/{assistant_id}/disable", response_model=AssistantResponse)
async def disable_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Schaltet einen eigenen, **nicht schulweiten** Assistenten ab: `active` → `disabled`.

    Das Gegenstueck zum Loeschen: Wer eine Unterrichtsreihe beendet, will den Assistenten
    oft nur aus dem Weg haben, nicht weg. Schulweit bleibt das dem Admin vorbehalten —
    dort haengen Kolleg:innen dran, die von der Abschaltung nichts wissen.
    """
    assistant = await _eigener(db, assistant_id, current_user.sub)
    if assistant.scope in SCHOOLWIDE_SCOPES:
        raise HTTPException(
            status_code=409,
            detail="Schulweite Assistenten schaltet die Administration ab.",
        )
    if assistant.status != "active":
        raise HTTPException(status_code=409, detail="Nur aktive Assistenten lassen sich abschalten.")
    assistant.status = "disabled"
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub
    await db.commit()
    await db.refresh(assistant)
    return AssistantResponse.model_validate(assistant)


@router.post("/{assistant_id}/enable", response_model=AssistantResponse)
async def enable_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Nimmt einen eigenen, nicht schulweiten Assistenten wieder in Betrieb.

    ⚠️ **Schulweit ausgeschlossen** — sonst waere die Freigabe umgehbar: abschalten
    lassen, aendern, selbst wieder einschalten.
    """
    assistant = await _eigener(db, assistant_id, current_user.sub)
    if assistant.scope in SCHOOLWIDE_SCOPES:
        raise HTTPException(
            status_code=409,
            detail="Schulweite Assistenten gibt die Administration wieder frei.",
        )
    if assistant.status != "disabled":
        raise HTTPException(
            status_code=409, detail="Nur abgeschaltete Assistenten lassen sich wieder freigeben."
        )
    assistant.status = "active"
    assistant.updated_at = datetime.now(timezone.utc)
    assistant.updated_by_pseudonym = current_user.sub
    await db.commit()
    await db.refresh(assistant)
    return AssistantResponse.model_validate(assistant)


class LoeschantragRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1000)


@router.post("/{assistant_id}/request-deletion", response_model=AssistantResponse)
async def request_deletion(
    assistant_id: int,
    request: LoeschantragRequest,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Beantragt die Loeschung eines freigegebenen **schulweiten** Assistenten.

    ⚠️ **Der Antrag schaltet nichts ab** (Entscheidung Jan, 25.09.2026). Ein Antrag ist
    eine Bitte, keine Handlung: Er sofort wirksam zu machen naehme dem Admin die
    Entscheidung ab und dem Unterricht ohne Vorwarnung ein Werkzeug. Deshalb ein Feld
    neben dem Status und kein eigener Status — `assistants.status` beantwortet weiterhin
    genau die eine Frage, ob der Assistent benutzbar ist.

    Nicht schulweite Assistenten loescht die Lehrkraft selbst; dort gibt es nichts zu
    beantragen.
    """
    assistant = await _eigener(db, assistant_id, current_user.sub)
    if assistant.scope not in SCHOOLWIDE_SCOPES:
        raise HTTPException(
            status_code=409,
            detail="Diesen Assistenten koennen Sie selbst loeschen - ein Antrag ist "
                   "nicht noetig.",
        )
    if assistant.status in ("draft", "pending_review"):
        raise HTTPException(
            status_code=409,
            detail="Ein Entwurf oder eine Einreichung laesst sich selbst loeschen.",
        )
    assistant.deletion_requested_at = datetime.now(timezone.utc)
    assistant.deletion_reason = (request.reason or "").strip() or None
    await db.commit()
    await db.refresh(assistant)
    return AssistantResponse.model_validate(assistant)


@router.delete("/{assistant_id}/request-deletion", response_model=AssistantResponse)
async def withdraw_deletion_request(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Nimmt den Loeschantrag zurueck — ein Fehlklick soll nicht endgueltig sein."""
    assistant = await _eigener(db, assistant_id, current_user.sub)
    assistant.deletion_requested_at = None
    assistant.deletion_reason = None
    await db.commit()
    await db.refresh(assistant)
    return AssistantResponse.model_validate(assistant)


# ── Dokument-Endpunkte ──────────────────────────────────────────────────────

MAX_DOCS = 3
MAX_TOTAL_TOKENS = 15_000
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB
ALLOWED_MIME = {"application/pdf", "text/plain", "text/markdown"}


@router.post("/{assistant_id}/documents", response_model=DocumentUploadResponse, status_code=201)
async def upload_assistant_document(
    assistant_id: int,
    file: UploadFile = File(...),
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    """Lädt ein Kontext-Dokument für einen Assistenten hoch."""
    # 1. Assistent laden + Besitzprüfung
    assistant = await _load_and_authorize_assistant(assistant_id, current_user, db)
    
    # 2. Datei-Validierung
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(422, "Datei überschreitet das Maximum von 2 MB.")
    mime = file.content_type or ""
    if mime not in ALLOWED_MIME:
        # Fallback: Endung prüfen
        name = (file.filename or "").lower()
        if name.endswith(".pdf"):
            mime = "application/pdf"
        elif name.endswith(".md"):
            mime = "text/markdown"
        elif name.endswith(".txt"):
            mime = "text/plain"
        else:
            raise HTTPException(422, "Nur PDF, TXT und Markdown (MD) sind erlaubt.")
    
    # 3. Klartext extrahieren
    try:
        if mime == "application/pdf":
            text = extract_pdf(data)
        else:
            text = extract_plaintext(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    
    # 4. Constraints prüfen
    existing_docs = (
        await db.execute(
            select(AssistantDocument).where(AssistantDocument.assistant_id == assistant_id)
        )
    ).scalars().all()
    
    if len(existing_docs) >= MAX_DOCS:
        raise HTTPException(422, f"Maximal {MAX_DOCS} Dokumente pro Assistent erlaubt.")
    
    existing_tokens = sum(len(d.content) // 4 for d in existing_docs)
    new_tokens = len(text) // 4
    if existing_tokens + new_tokens > MAX_TOTAL_TOKENS:
        raise HTTPException(
            422,
            f"Dieses Dokument würde das Token-Limit überschreiten "
            f"({existing_tokens + new_tokens} / {MAX_TOTAL_TOKENS}). "
            "Bitte entferne ein anderes Dokument oder verwende eine kürzere Datei."
        )
    
    # 5. Speichern
    doc = AssistantDocument(
        assistant_id=assistant_id,
        filename=file.filename or "dokument",
        mime_type=mime,
        size_bytes=len(data),
        content=text,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    
    total = existing_tokens + new_tokens
    return DocumentUploadResponse(
        id=doc.id,
        filename=doc.filename,
        size_bytes=doc.size_bytes,
        token_estimate=new_tokens,
        total_tokens=total,
        document_count=len(existing_docs) + 1,
    )


@router.get("/{assistant_id}/documents", response_model=list[AssistantDocumentOut])
async def list_assistant_documents(
    assistant_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[AssistantDocumentOut]:
    """Listet alle Kontext-Dokumente eines Assistenten auf."""
    await _load_and_authorize_assistant(assistant_id, current_user, db)
    docs = (
        await db.execute(
            select(AssistantDocument)
            .where(AssistantDocument.assistant_id == assistant_id)
            .order_by(AssistantDocument.created_at)
        )
    ).scalars().all()
    return [_doc_to_out(d) for d in docs]


@router.delete("/{assistant_id}/documents/{doc_id}", status_code=204)
async def delete_assistant_document(
    assistant_id: int,
    doc_id: int,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Löscht ein Kontext-Dokument eines Assistenten."""
    await _load_and_authorize_assistant(assistant_id, current_user, db)
    doc = (
        await db.execute(
            select(AssistantDocument).where(
                AssistantDocument.id == doc_id,
                AssistantDocument.assistant_id == assistant_id,
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Dokument nicht gefunden.")
    await db.delete(doc)
    await db.commit()


@router.post("/import", response_model=AssistantImportResponse, status_code=201)
async def import_assistant(
    hintergrund: BackgroundTasks,
    file: UploadFile = File(...),
    model_override: Optional[str] = None,
    current_user: JwtPayload = Depends(require_any_role(["teacher", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> AssistantImportResponse:
    """Importiert einen Assistenten aus einer YAML-Datei."""
    # YAML parsen
    try:
        content = await file.read()
        data = yaml.safe_load(content.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"YAML-Parsefehler: {exc}"
        )
    
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=422,
            detail="YAML muss ein Objekt (Dictionary) auf oberster Ebene enthalten"
        )
    
    # JSON-Schema-Validierung
    try:
        jsonschema.validate(instance=data, schema=_get_assistant_schema())
    except jsonschema.ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Schema-Validierungsfehler: {exc.message}"
        )
    
    # Subject-Lookup
    subject_id = None
    if "subject" in data.get("metadata", {}):
        subject_slug = data["metadata"]["subject"]
        if subject_slug:
            result = await db.execute(
                select(Subject.id).where(Subject.slug == subject_slug.lower())
            )
            subject_id = result.scalar_one_or_none()
    
    # Felder mappen
    hinweise: list[str] = []
    fields = _yaml_to_assistant_fields(data, subject_id, hinweise)
    
    # model_override anwenden
    if model_override:
        fields["model"] = model_override.strip()
    
    # Validierung der gemappten Felder
    validate_assistant_fields(
        name=fields.get("name"),
        system_prompt=fields.get("system_prompt"),
        audience=fields.get("audience"),
        scope=fields.get("scope"),
        visibility=fields.get("visibility"),
        scope_group_id=fields.get("scope_group_id"),
        min_grade=fields.get("min_grade"),
        max_grade=fields.get("max_grade"),
        available_from=fields.get("available_from"),
        available_until=fields.get("available_until"),
        suggest=fields.get("suggest"),
    )
    meta = data["metadata"]
    listen = _bereinigte_ausloeser(
        meta.get("trigger_examples") or [], meta.get("trigger_counterexamples") or []
    )
    fields["fallbacks"] = await _fallbacks_nach_namen(db, meta.get("fallbacks") or [], hinweise)
    wunsch = [str(s).strip().lower() for s in data["config"].get("operator_faecher") or []]
    fields["operator_faecher"] = _uebernimm_bekannte(
        list(dict.fromkeys(wunsch)),
        set((await db.execute(select(Subject.slug).where(Subject.slug.in_(wunsch)))).scalars())
        if wunsch else set(),
        "Fächer für Operatoren", hinweise,
    )

    creator_role = "admin" if "admin" in current_user.roles else "teacher"
    
    # Assistent erstellen
    assistant = Assistant(
        **fields,
        status="draft",
        creator_role=creator_role,
        created_by=current_user.sub,
        updated_by_pseudonym=current_user.sub,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        sort_order=0,  # Importierte Assistenten kommen als Draft, sort_order ist Admin-Sache
    )
    db.add(assistant)
    await db.flush()
    neu = await _speichere_ausloeser(db, assistant.id, listen)
    await db.commit()
    await db.refresh(assistant)
    if neu:
        _einbetten_nach_speichern(hintergrund, db, assistant.id)

    if hinweise:
        logger.info(
            "Assistenten-Import '%s': %s", assistant.name, " · ".join(hinweise)
        )
    antwort = await _mit_ausloesern(db, AssistantResponse.model_validate(assistant))
    return AssistantImportResponse(**antwort.model_dump(), hinweise=hinweise)


@router.get("/{assistant_id}/export")
async def export_assistant(
    assistant_id: int,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Exportiert einen Assistenten als YAML-Datei. Nur Eigentuemer oder Admin."""
    result = await db.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None:
        raise HTTPException(status_code=404, detail="Assistent nicht gefunden")
    
    is_admin = "admin" in current_user.roles
    _check_assistant_access(assistant, current_user, is_admin)
    
    # Subject-Slug fuer Export
    subject_slug = None
    if assistant.subject_id:
        subj_result = await db.execute(
            select(Subject.slug).where(Subject.id == assistant.subject_id)
        )
        subject_slug = subj_result.scalar_one_or_none()
    
    fallback_namen: list[str] = []
    if assistant.fallbacks:
        namen = dict(
            (await db.execute(
                select(Assistant.id, Assistant.name).where(Assistant.id.in_(assistant.fallbacks))
            )).all()
        )
        fallback_namen = [namen[i] for i in assistant.fallbacks if i in namen]
    yaml_content = _assistant_to_yaml(
        assistant, subject_slug, await ausloeser.lade(db, assistant.id), fallback_namen
    )
    
    # Dateiname: name kleingeschrieben, Leerzeichen -> Bindestrich
    slug = assistant.name.lower().replace(" ", "-")
    filename = f"{slug}.yaml"
    
    return Response(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
