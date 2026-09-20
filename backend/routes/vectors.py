"""Observation and speculative-vector API. Never return sealed text or vectors."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from fastapi import APIRouter
from ml import rag_engine
from ml.temporal import Caption, Interval, MAX_MEDIA_MS
from ml.metrics import metrics
from .rag import _service_error

router = APIRouter()


class TranscriptRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_url: str = Field(min_length=1, max_length=4000)
    topic: str = Field(min_length=1, max_length=300)
    captions: list[Caption] = Field(min_length=1, max_length=20000)


class ObservationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_id: str = Field(min_length=1, max_length=64)
    media_session_id: str = Field(min_length=8, max_length=100)
    event_sequence: int = Field(ge=0, strict=True)
    observed_intervals: list[Interval] = Field(max_length=10000)
    evidence: Literal['rendered-frame', 'decoded-frame']


@router.post('/api/vectors/transcript')
def register_transcript(req: TranscriptRequest):
    try:
        return rag_engine.vectors.register(req.source_url, req.topic, req.captions)
    except Exception as exc:
        raise _service_error(exc) from exc


@router.post('/api/observation/intervals')
def observe(req: ObservationRequest):
    try:
        return rag_engine.vectors.observe(req.document_id, req.media_session_id, req.event_sequence,
                                          req.observed_intervals, req.evidence)
    except Exception as exc:
        raise _service_error(exc) from exc


@router.get('/api/vectors/diagnostics')
def diagnostics():
    return {'documents': rag_engine.vectors.diagnostics(), 'metrics': metrics.snapshot(),
            'active_vectors': rag_engine.count, 'model_version': rag_engine.model_version}


@router.delete('/api/vectors/documents/{document_id}')
def delete_document(document_id: str):
    return {'removed_active_vectors': rag_engine.delete_documents([document_id])}
