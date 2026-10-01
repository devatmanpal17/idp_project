"""Player state input to the local Ollama residency controller."""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from ..models import LearnerKey, VideoKey

from ml.residency import residency

router = APIRouter()


class PlayerState(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra='forbid')
    learner_key: LearnerKey
    video_key: VideoKey
    state: Literal['PLAYING', 'PAUSED', 'SEEKING', 'HIDDEN', 'ENDED']
    media_time: float = Field(ge=0)
    ts: float


@router.post('/api/runtime/player-state')
def player_state(req: PlayerState):
    return residency.transition(req.state)
