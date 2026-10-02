"""
AI configuration settings endpoint.
"""

from fastapi import APIRouter, HTTPException
from ..models import AIConfigRequest
from ml import llm_service, rag_engine
from ml.residency import residency

router = APIRouter()


@router.post("/api/settings/ai-config")
def set_ai_config(req: AIConfigRequest):
    """Updates runtime AI Provider & API keys."""
    try:
        with rag_engine._lock:
            llm_service.configure(provider=req.provider, api_key=req.api_key or "", model=req.model or "")
            with residency.lock:
                residency.set_chat_model(llm_service.model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "status": "success",
        "active_provider": req.provider,
        "model": llm_service.model,
        "has_key": False
    }
