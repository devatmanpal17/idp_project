# Cognivue Backend Server

The `backend/` folder contains the FastAPI REST API layer for CogniVue.

## Structure

- **`app.py`**: FastAPI application instance and CORS middleware configuration.
- **`models.py`**: Pydantic request and response schemas.
- **`routes/`**:
  - `health.py`: Health checks (`/api/health`).
  - `rag.py`: RAG context retrieval, question generation, and quiz scoring endpoints (`/api/rag/*`).
  - `recommendations.py`: Spaced repetition study recommendations (`/api/recommendations/smart`).
  - `settings.py`: AI provider configuration (`/api/settings/ai-config`).
- **`run.py`**: Direct executable runner (`python backend/run.py`).

## Running the Backend

```bash
# Option 1: Using uvicorn
python -m uvicorn backend.app:app --port 8000 --reload

# Option 2: Using the runner script
python -m backend.run
```
