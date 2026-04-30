from pydantic import BaseModel, Field, model_validator
from typing import Annotated, Literal, Union
from uuid import UUID
from typing import Optional


# ── Content-Part-Typen ──────────────────────────────────────────────────────

class TextPart(BaseModel):
    type: Literal["text"]
    text: str


class ImageUrlContent(BaseModel):
    url: str  # "data:image/png;base64,..." oder https://...


class ImageUrlPart(BaseModel):
    type: Literal["image_url"]
    image_url: ImageUrlContent


ContentPart = Annotated[
    Union[TextPart, ImageUrlPart],
    Field(discriminator="type"),
]


# ── Chat-Schemas ────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, list[ContentPart]]


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    conversation_id: Optional[UUID] = None
    model_id: Optional[str] = None

    @model_validator(mode="after")
    def at_least_one_message(self):
        if not self.messages:
            raise ValueError("messages darf nicht leer sein")
        if self.model_id is not None:
            normalized = self.model_id.strip()
            self.model_id = normalized or None
        return self
