from pydantic import BaseModel, Field
from typing import Optional, Literal

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    edition: str = "No especificada"
    game_version: str = ""
    history: list[dict] = Field(default_factory=list)
    session_id: Optional[str] = None

class VoteRequest(BaseModel):
    voter_id: str = Field(min_length=1, max_length=120)
    vote: Literal["like", "dislike"]
