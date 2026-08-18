"""
Cognivue AI Engine — FastAPI Application Factory
Loads .env from root, initializes CORS, registers route modules.
"""

import os
from pathlib import Path

# Load .env from project root (cognivue-insight/.env)
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    print(f"[ENV] Loaded environment from {_env_path}")
    # Print key availability (not the values!)
    print(f"[ENV] OPENAI_API_KEY: {'[OK] configured' if os.environ.get('OPENAI_API_KEY') else '[NOT SET]'}")
    print(f"[ENV] GEMINI_API_KEY: {'[OK] configured' if os.environ.get('GEMINI_API_KEY') else '[NOT SET]'}")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.health import router as health_router
from .routes.rag import router as rag_router
from .routes.recommendations import router as recommendations_router
from .routes.settings import router as settings_router

app = FastAPI(
    title="Cognivue AI Engine",
    description="RAG vector search, LLM quiz generator, and learner signal intelligence.",
    version="2.0.0",
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
