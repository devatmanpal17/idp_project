# ChaiGaram Backend Server

The `backend/` folder contains the FastAPI REST API layer for ChaiGaram.

## Structure

- **`app.py`**: FastAPI application instance and CORS middleware configuration.
- **`models.py`**: Pydantic request and response schemas.
- **`routes/`**:
  - `health.py`: Health checks (`/api/health`).
  - `rag.py`: RAG context retrieval, question generation, and quiz scoring endpoints (`/api/rag/*`).
  - `jobs.py`: asynchronous tutor/summary/quiz jobs (`POST /api/jobs`, `GET /api/jobs/{job_id}`) for browser-extension-safe polling.
  - `learning_data.py`: Courses, mastery, study plan, recommendations, visit history, and indexed-source deletion (`/api/learning/*`).
  - `mistakes.py`: Persistent missed-question queue (`GET /api/learning/mistakes`) and review scheduling (`POST /api/learning/mistakes/{item_id}/review`).
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

Mistake review writes accept `outcome` (`again` or `remembered`) and the current
card `version`. A stale version or a current evidence hold returns 409. Listing
supports `include_scheduled`, `limit` (1-100), and `offset`; held cards return
scheduling metadata without question/answer/explanation fields. Assessment
capture and card creation share one SQL transaction. Review progress does not
change quiz mastery or invoke Ollama.
