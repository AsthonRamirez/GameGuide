from pydantic import BaseModel, Field
from typing import Optional, Literal

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    edition: str = "No especificada"
    game_version: str = ""
    history: list[dict] = Field(default_factory=list)
    session_id: Optional[str] = None

class FeedbackRequest(BaseModel):
    interaction_id: str
    rating: Literal["si_me_ayudo", "no_entrego_justo", "nada_que_ver"]
    comment: str = Field(default="", max_length=1000)
