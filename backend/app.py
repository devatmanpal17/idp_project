"""
Cognivue AI Engine — FastAPI Application Factory
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.health import router as health_router
from .routes.rag import router as rag_router
from .routes.recommendations import router as recommendations_router
from .routes.settings import router as settings_router

app = FastAPI(
    title="Cognivue AI Engine",
    description="RAG vector search, LLM quiz generator, and learner signal intelligence.",
    version="1.0.0",
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(health_router)
app.include_router(rag_router)
app.include_router(recommendations_router)
app.include_router(settings_router)
