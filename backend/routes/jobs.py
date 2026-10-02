"""Durable HTTP jobs independent of extension service-worker lifetime."""
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError
from ..models import AIJobRequest, AskRequest, GenerateQuizRequest, SummarizeRequest
from .rag import ask_lesson, generate_quiz, summarize_page
from .vectors import SealRequest, seal_scoped
from ml import rag_engine
from ml.scheduler import controller
from ml.publication import capture, validate_records

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chaigaram-ai")
_speculation_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chaigaram-speculation")
store = rag_engine.jobs
MODELS = {"ask": AskRequest, "quiz": GenerateQuizRequest, "summarize": SummarizeRequest, "seal": SealRequest}
HANDLERS = {"ask": ask_lesson, "quiz": generate_quiz, "summarize": summarize_page, "seal": seal_scoped}


def run_job(job_id):
    if not store.claim(job_id):
        return
    job = store.get(job_id, private=True)
    try:
        payload = job['payload']
        if job['stage'] == 'VALIDATING' and 'result' in job['checkpoint']:
            with rag_engine._lock:
                if payload.get('source_type') == 'video' and 'evidence' not in job['checkpoint']:
                    raise ValueError('This older video output has no evidence proof; create a fresh request.')
                validate_records(rag_engine, job['checkpoint'].get('evidence', []),
                                 quiz_id=job['checkpoint']['result'].get('quiz_id') if job['operation'] == 'quiz' else None)
                store.finish(job_id, result=job['checkpoint']['result'])
            return
        if job['operation'] == 'speculate':
            started = time.perf_counter()
            for chunk_id in payload['chunk_ids']:
                if store.get(job_id)['status'] != 'running':
                    return
                if controller.interactive or (time.perf_counter()-started)*1000 >= payload['budget_ms']:
                    break
                tick = time.perf_counter()
                store.checkpoint(job_id, 'EMBEDDING', {'current_chunk': chunk_id})
                # Recheck admission after waiting for an in-flight vector mutation.
                with rag_engine._lock:
                    if controller.interactive or store.get(job_id)['status'] != 'running':
                        break
                    embedded = rag_engine.vectors.embed_chunk(payload['document_id'], chunk_id)
                if embedded:
                    controller.measured((time.perf_counter()-tick)*1000)
                store.checkpoint(job_id, 'SEALED', {'last_completed_chunk': chunk_id})
            result = rag_engine.vectors.status(payload['document_id'])
        else:
            with controller.interactive_work(), capture() as evidence:
                store.checkpoint(job_id, 'GENERATING', job['checkpoint'])
                result = HANDLERS[job['operation']](MODELS[job['operation']].model_validate(payload))
                with rag_engine._lock:
                    validate_records(rag_engine, evidence,
                                     quiz_id=result.get('quiz_id') if job['operation'] == 'quiz' else None)
                    store.checkpoint(job_id, 'VALIDATING', {'result': result, 'evidence': evidence})
                    store.finish(job_id, result=result)
                return
        store.finish(job_id, result=result)
    except Exception as exc:
        store.finish(job_id, error=str(exc.detail) if isinstance(exc, HTTPException) else str(exc) or 'The AI job failed.')


def submit(operation, payload, request_id=None):
    job_id, created = store.create(operation, payload, request_id)
    if created:
        executor = _speculation_executor if operation == 'speculate' else _executor
        executor.submit(run_job, job_id)
    return {'job_id': job_id, 'status': store.get(job_id)['status']}


def resume_jobs():
    for job_id in store.recover():
        executor = _speculation_executor if store.get(job_id)['operation'] == 'speculate' else _executor
        executor.submit(run_job, job_id)


@router.post('/api/jobs', status_code=202)
def create_job(request: AIJobRequest):
    try:
        payload = MODELS[request.operation].model_validate(request.payload).model_dump()
        return submit(request.operation, payload, request.request_id)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get('/api/jobs/{job_id}')
def job_status(job_id: str):
    with rag_engine._lock:
        private = store.get(job_id, private=True)
        if not private:
            raise HTTPException(status_code=404, detail='Job was not found.')
        if 'result' in private:
            try:
                if private['payload'].get('source_type') == 'video' and 'evidence' not in private['checkpoint']:
                    raise ValueError('This older video output has no evidence proof; create a fresh request.')
                validate_records(rag_engine, private['checkpoint'].get('evidence', []),
                                 quiz_id=private['result'].get('quiz_id') if private['operation'] == 'quiz' else None)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return store.get(job_id)
