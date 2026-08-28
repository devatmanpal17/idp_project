"""
Health check endpoint — reports real AI provider status.
"""

import time
from fastapi import APIRouter
from ml import rag_engine, llm_service
from ml.analytics import quiz_analytics

router = APIRouter()


@router.get("/api/health")
def health_check():
    rag_status = rag_engine.status()
    llm_status = llm_service.status()
    ready = (
        rag_status["embedding_service"]["embedding_model_ready"]
        and llm_status["model_ready"]
    )
    return {
        "status": "ready" if ready else "setup_required",
        "service": "ChaiGaram AI/ML Engine",
        "version": "3.0.0",
        **rag_status,
        "active_ai_provider": llm_service.active_provider,
        "llm_service": llm_status,
        "last_provider_used": llm_service._last_provider_used,
        "analytics_database": quiz_analytics.storage_backend,
        "timestamp": time.time()
    }
