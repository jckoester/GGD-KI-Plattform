from pydantic import BaseModel, model_validator
from typing import Literal
from uuid import UUID
from typing import Optional


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


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
