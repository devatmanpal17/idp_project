"""Read-only responses while hosted models install; never imports ML or opens SQL."""
import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get('/api/live')
async def live():
    return {'status': 'ok'}


@app.get('/api/health')
async def health():
    return {'status': 'setup_required', 'service': 'ChaiGaram AI/ML Engine',
            'detail': 'AI models are being installed. Learning will be available when setup completes.',
            'active_ai_provider': 'ollama',
            'embedding_service': {'embedding_model': os.getenv('OLLAMA_EMBED_MODEL', 'embeddinggemma'),
                                  'embedding_model_ready': False},
            'llm_service': {'model': os.getenv('OLLAMA_CHAT_MODEL', 'llama3.2:3b'), 'model_ready': False}}


@app.api_route('/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'])
async def unavailable(path: str):
    return JSONResponse(status_code=503, headers={'Retry-After': '30'},
                        content={'detail': 'AI models are being installed. Please retry when the engine is ready.'})
