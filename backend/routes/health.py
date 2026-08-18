"""
Health check endpoint.
"""

import time
from fastapi import APIRouter
from ..services.rag_engine import rag_engine, KNOWLEDGE_BASE
from ..services.llm_service import llm_service

router = APIRouter()


@router.get("/api/health")
def health_check():
    total_chunks = len(rag_engine.all_chunks)
    active_provider = (
        "gemini" if llm_service.gemini_api_key else
        "openai" if llm_service.openai_api_key else
        "local_rag_engine"
    )
    return {
        "status": "online",
        "service": "Cognivue AI/ML Engine",
        "version": "1.0.0",
        "indexed_chunks": total_chunks,
        "topics_indexed": list(KNOWLEDGE_BASE.keys()),
        "active_ai_provider": active_provider,
        "timestamp": time.time()
    }
