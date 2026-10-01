"""Player state input to the local Ollama residency controller."""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ml.residency import residency

router = APIRouter()


class PlayerState(BaseModel):
    learner_key: str = Field(min_length=1, max_length=100)
    video_key: str = Field(min_length=1, max_length=200)
    state: Literal['PLAYING', 'PAUSED', 'SEEKING', 'HIDDEN', 'ENDED']
    media_time: float = Field(ge=0)
    ts: float


@router.post('/api/runtime/player-state')
def player_state(req: PlayerState):
    return residency.transition(req.state)
