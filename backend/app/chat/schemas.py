from pydantic import BaseModel, model_validator
from typing import Literal


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]

    @model_validator(mode="after")
    def at_least_one_message(self):
        if not self.messages:
            raise ValueError("messages darf nicht leer sein")
        return self
