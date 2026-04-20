from pydantic import BaseModel


class Preferences(BaseModel):
    theme: str | None = None  # 'light' | 'dark' | 'system'
    show_cost: bool | None = None
    cost_granularity: str | None = None  # 'message' | 'conversation' | 'both'
