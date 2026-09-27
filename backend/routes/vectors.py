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
    from .jobs import store
    from ml.scheduler import controller
    return {'documents': rag_engine.vectors.diagnostics(), 'metrics': metrics.snapshot(),
            'active_vectors': rag_engine.count, 'model_version': rag_engine.model_version,
            'jobs': store.diagnostics(), 'scheduler': getattr(controller, 'last_decision', {}),
            'cache': rag_engine.hot_cache.status(),
            'query_vector_cache': rag_engine.query_vector_cache.status()}


@router.delete('/api/vectors/documents/{document_id}')
def delete_document(document_id: str):
    return {'removed_active_vectors': rag_engine.delete_documents([document_id])}


class SpeculationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    document_id: str = Field(min_length=1, max_length=64)
    position_ms: int = Field(ge=0, le=MAX_MEDIA_MS)
    budget_ms: int = Field(default=2000, ge=1, le=10000)
    idle: bool = False
    observed_only: bool = False


class MigrationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    collection_name: str = Field(min_length=1, max_length=512)
    dry_run: bool = True


@router.post('/api/vectors/migrate')
def migrate(req: MigrationRequest):
    try:
        return rag_engine.migrate_legacy(req.collection_name, req.dry_run)
    except Exception as exc:
        raise _service_error(exc) from exc


@router.post('/api/vectors/speculate', status_code=202)
def speculate(req: SpeculationRequest):
    from .jobs import store, submit
    from ml.scheduler import controller
    try:
        pending = rag_engine.vectors.pending(req.document_id)
        cache_usage = [getattr(getattr(rag_engine, name, None), 'resident_bytes', 0)
                       for name in ('hot_cache', 'query_vector_cache')]
        decision = controller.decide(budget_ms=req.budget_ms, idle=req.idle,
                                     queue_depth=store.queue_depth(),
                                     occupancy=sum(value for value in cache_usage
                                                   if isinstance(value, (int, float))))
        # Prefer already observed chunks; future work stays within the horizon.
        intervals = rag_engine.vectors.intervals(req.document_id)
        from ml.temporal import covered
        eligible = [c for c in pending if covered(c['start_ms'], c['end_ms'], intervals)
                    or (not req.observed_only and c['start_ms'] <= req.position_ms + controller.horizon_ms)]
        eligible.sort(key=lambda c: (not covered(c['start_ms'], c['end_ms'], intervals), c['start_ms']))
        ids = [c['id'] for c in eligible[:decision['batch_size']]]
        if not ids:
            return {'job_id': None, 'decision': decision, 'pending_chunks': len(eligible)}
        return {**submit('speculate', {'document_id': req.document_id, 'chunk_ids': ids,
                                     'budget_ms': req.budget_ms}), 'decision': decision}
    except Exception as exc:
        raise _service_error(exc) from exc
