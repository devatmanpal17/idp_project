"""
ChaiGaram Machine Learning & RAG Engine Package
"""

from .rag_engine import rag_engine, RAGEngine
from .llm_service import llm_service, LLMService
from .calibration import calibrate_difficulty, compute_mastery_update
from .knowledge_base import KNOWLEDGE_BASE, GENERIC_CHUNKS
from .graph_generator import (
    generate_similarity_distribution_chart,
    generate_irt_curve,
    generate_cognitive_breakdown,
    generate_mastery_shift_chart,
    generate_concept_graph,
)

__all__ = [
    "rag_engine",
    "RAGEngine",
    "llm_service",
    "LLMService",
    "calibrate_difficulty",
    "compute_mastery_update",
    "KNOWLEDGE_BASE",
    "GENERIC_CHUNKS",
    "generate_similarity_distribution_chart",
    "generate_irt_curve",
    "generate_cognitive_breakdown",
    "generate_mastery_shift_chart",
    "generate_concept_graph",
]
