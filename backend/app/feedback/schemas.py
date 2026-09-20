"""Was der Client schickt und was zurückkommt (ADR-020).

**Zwei Sorten Felder, zwei Umgangsweisen.** Was ein Mensch tippt — Text und Kontakt —
wird geprüft und bei Verstoß abgewiesen: Eine zu kurze Meldung ist eine Aussage über
die Meldung, und ein 422 sagt das. Was der Client **automatisch** beilegt — Version,
Route, Browserkennung, Fenstergröße — wird dagegen gekürzt statt abgewiesen. Ein
Browser, der eine 900 Zeichen lange Kennung sendet, darf keinen Fehlerbericht
verhindern; der Bericht ist das Wertvolle, der Kontext die Zugabe.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# Die Grenzen aus ADR-020: kurz genug, dass „test" nicht durchkommt, lang genug für
# eine ausführliche Fehlerbeschreibung.
MIN_LAENGE = 20
MAX_LAENGE = 4_000
MAX_KONTAKT = 200

# Kürzungsgrenzen der automatisch erfassten Felder.
MAX_VERSION = 50
MAX_ROUTE = 200
MAX_USER_AGENT = 500
MAX_VIEWPORT = 20

KATEGORIEN = ("bug", "suggestion", "other")


def _gekuerzt(wert, laenge: int):
    if isinstance(wert, str):
        wert = wert.strip()[:laenge]
        return wert or None
    return wert


class FeedbackCreate(BaseModel):
    """Eine neue Meldung."""

    category: Literal["bug", "suggestion", "other"]
    content: str = Field(..., min_length=MIN_LAENGE, max_length=MAX_LAENGE)
    contact: Optional[str] = Field(None, max_length=MAX_KONTAKT)
    attach_conversation_id: Optional[UUID] = None
    app_version: str = Field(..., min_length=1)
    route: Optional[str] = None
    assistant_id: Optional[int] = None
    user_agent: Optional[str] = None
    viewport: Optional[str] = None

    @field_validator("content", mode="before")
    @classmethod
    def _text_entranden(cls, wert):
        """Erst trimmen, dann messen — sonst genügten 20 Leerzeichen der Mindestlänge."""
        return wert.strip() if isinstance(wert, str) else wert

    @field_validator("contact", mode="before")
    @classmethod
    def _kontakt_entranden(cls, wert):
        """Ein leer gelassenes Feld ist `NULL`, nicht `""` — sonst sähe die Sichtung
        einen Kontakt, wo keiner steht."""
        if isinstance(wert, str):
            return wert.strip() or None
        return wert

    @field_validator("route", mode="before")
    @classmethod
    def _route_ohne_query(cls, wert):
        """Nur der Pfad. Eine Query trägt hier nichts bei und kann tragen, was in einer
        Meldung nichts zu suchen hat — eine Suchanfrage etwa."""
        if isinstance(wert, str):
            wert = wert.split("?", 1)[0].split("#", 1)[0]
        return _gekuerzt(wert, MAX_ROUTE)

    @field_validator("app_version", mode="before")
    @classmethod
    def _version_kuerzen(cls, wert):
        return _gekuerzt(wert, MAX_VERSION)

    @field_validator("user_agent", mode="before")
    @classmethod
    def _kennung_kuerzen(cls, wert):
        return _gekuerzt(wert, MAX_USER_AGENT)

    @field_validator("viewport", mode="before")
    @classmethod
    def _viewport_kuerzen(cls, wert):
        return _gekuerzt(wert, MAX_VIEWPORT)


class FeedbackOut(BaseModel):
    """Die eigene Meldung, wie die meldende Person sie sieht.

    **Ohne `issue_ref`**: Die Referenz auf ein Issue im Entwicklungs-Tracker ist eine
    interne Arbeitsnotiz der Sichtung. **Ohne den Snapshot selbst**: Wer ihn angehängt
    hat, kennt ihn; `has_snapshot` beantwortet die einzige Frage, die offen ist —
    hängt er noch dran oder ist er beim Abschluss gefallen?
    """

    id: UUID
    category: str
    content: str
    contact: Optional[str] = None
    app_version: str
    route: Optional[str] = None
    assistant_id: Optional[int] = None
    status: str
    admin_reply: Optional[str] = None
    resolved_in_version: Optional[str] = None
    has_snapshot: bool
    created_at: datetime
    status_changed_at: Optional[datetime] = None
