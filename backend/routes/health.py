"""
Health check endpoint — reports real AI provider status.
"""

import time
from fastapi import APIRouter
from ml import rag_engine, KNOWLEDGE_BASE, llm_service

router = APIRouter()


@router.get("/api/health")
def health_check():
    total_chunks = len(rag_engine.all_chunks)
    return {
        "status": "online",
        "service": "Cognivue AI/ML Engine",
        "version": "2.0.0",
        "indexed_chunks": total_chunks,
        "topics_indexed": list(KNOWLEDGE_BASE.keys()),
        "active_ai_provider": llm_service.active_provider,
        "has_openai_key": bool(llm_service.openai_api_key),
        "has_gemini_key": bool(llm_service.gemini_api_key),
        "last_provider_used": llm_service._last_provider_used,
        "timestamp": time.time()
    }
