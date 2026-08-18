"""
AI configuration settings endpoint.
"""

from fastapi import APIRouter
from ..models import AIConfigRequest
from ml import llm_service

router = APIRouter()


@router.post("/api/settings/ai-config")
def set_ai_config(req: AIConfigRequest):
    """Updates runtime AI Provider & API keys."""
    llm_service.configure(provider=req.provider, api_key=req.api_key or "")
    return {
        "status": "success",
        "active_provider": req.provider,
        "has_key": bool(req.api_key)
    }
