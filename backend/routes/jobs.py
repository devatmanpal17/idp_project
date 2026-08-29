"""Short-lived HTTP job API for LLM work that outlives MV3 message channels."""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..models import AIJobRequest, AskRequest, GenerateQuizRequest, SummarizeRequest
from .rag import ask_lesson, generate_quiz, summarize_page

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chaigaram-ai")
_lock = RLock()
_jobs: Dict[str, Dict[str, Any]] = {}


def _run_job(job_id: str, request: AIJobRequest) -> None:
    with _lock:
        _jobs[job_id].update(status="running", updated_at=time.time())
    try:
        if request.operation == "ask":
            result = ask_lesson(AskRequest.model_validate(request.payload))
        elif request.operation == "summarize":
            result = summarize_page(SummarizeRequest.model_validate(request.payload))
        else:
            result = generate_quiz(GenerateQuizRequest.model_validate(request.payload))
    except HTTPException as exc:
        error = str(exc.detail)
        with _lock:
            _jobs[job_id].update(status="failed", error=error, updated_at=time.time())
    except Exception as exc:
        with _lock:
            _jobs[job_id].update(
                status="failed", error=str(exc) or "The AI job failed.", updated_at=time.time()
            )
    else:
        with _lock:
            _jobs[job_id].update(status="succeeded", result=result, updated_at=time.time())


def _prune_jobs() -> None:
    with _lock:
        if len(_jobs) <= 100:
            return
        completed = sorted(
            (
                (job_id, job["updated_at"])
                for job_id, job in _jobs.items()
                if job["status"] in {"succeeded", "failed"}
            ),
            key=lambda item: item[1],
        )
        for job_id, _ in completed[: len(_jobs) - 100]:
            _jobs.pop(job_id, None)


@router.post("/api/jobs", status_code=202)
def create_job(request: AIJobRequest) -> Dict[str, Any]:
    _prune_jobs()
    job_id = uuid.uuid4().hex
    now = time.time()
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "operation": request.operation,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
        }
    _executor.submit(_run_job, job_id, request)
    return {"job_id": job_id, "status": "queued"}


@router.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> Dict[str, Any]:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="AI job was not found. Please retry.")
        return dict(job)
