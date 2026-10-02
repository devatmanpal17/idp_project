# ChaiGaram

ChaiGaram is a local AI-powered learning assistant. It captures educational webpages, course lessons, selected text, and watched video captions; indexes that material; answers questions from it; generates grounded quizzes; tracks performance; and builds a mastery dashboard, study plan, and mistake review notebook.

## Technology stack

- React 19, TanStack Start, TanStack Router, React Query, and Tailwind CSS
- Chrome/Edge Manifest V3 browser extension
- FastAPI and Pydantic
- Ollama `embeddinggemma` for embeddings
- Ollama `llama3.2:3b` for generation
- ChromaDB for persistent semantic search
- SQLite locally or PostgreSQL in production for quiz analytics
- Optional Firebase Authentication and Firestore for user profiles

> The current implementation uses Ollama and ChromaDB. Older references to Gemini, OpenAI, or TF-IDF do not describe the active pipeline.

## Architecture

```text
Educational webpage or video
            |
            v
Chrome/Edge extension
  - extracts useful page text
  - captures captions already watched
  - provides tutor and quiz UI
            |
            v
FastAPI backend (:8000)
  |         |                   |
  |         |                   +--> SQLite/PostgreSQL
  |         |                        quiz sessions and attempts
  |         |
  |         +--> Ollama llama3.2:3b
  |              answers, summaries, and quizzes
  |
  +--> Ollama embeddinggemma --> ChromaDB
       document/query vectors      indexed lesson chunks
            |
            v
React dashboard (:8080)
  - courses and topics
  - mastery and quiz history
  - study plan and recommendations
```

The extension and React dashboard are separate clients of the same FastAPI backend.

## Repository structure

```text
chaigaram/
|-- backend/
|   |-- app.py                 FastAPI application and route registration
|   |-- models.py              Pydantic request validation models
|   |-- run.py                 Backend runner
|   `-- routes/
|       |-- health.py          Service diagnostics
|       |-- rag.py             Ingestion, retrieval, tutor, and quiz APIs
|       |-- jobs.py            Pollable background AI jobs
|       |-- learning_data.py   Dashboard data and history deletion
|       |-- recommendations.py Assessment-based recommendations
|       `-- settings.py        Runtime Ollama configuration
|-- ml/
|   |-- rag_engine.py          Chunking, embeddings, and ChromaDB
|   |-- llm_service.py         Grounded generation and validation
|   |-- analytics.py           SQLite/PostgreSQL quiz persistence
|   |-- calibration.py         Difficulty and mastery formulas
|   `-- graph_generator.py     Chart payload generation
|-- frontend/
|   |-- src/routes/            Dashboard screens
|   |-- src/components/        Shared UI and quiz components
|   `-- src/lib/               API clients, queries, types, and Firebase
|-- extension/
|   |-- manifest.json          Extension definition
|   |-- background.js          Backend API bridge
|   |-- content.js             Capture logic and page overlay
|   |-- popup.*                Extension popup
|   `-- options.*              Connection settings
|-- tests/                     Backend and AI guardrail tests
`-- start_all.bat              Windows setup and launcher
```

## How it works

### 1. Capture content

The extension's `content.js` runs on normal HTTP and HTTPS pages.

For documents it locates the main article/content container and removes navigation, forms, sidebars, comments, recommendations, advertisements, scripts, and decorative content. It keeps useful headings, paragraphs, lists, code, quotations, and captions.

For videos it collects timestamped captions from native text tracks, YouTube caption data, or visible caption elements. Available tracks, including future captions, can be stored and embedded in a sealed SQL store. Only caption chunks fully covered by observed playback intervals are promoted to the searchable Chroma index; forward seeking does not unlock skipped content.

The YouTube F1 path scopes vectors by learner and video and keeps separate micro
and macro chunks. Interval uploads include the caption `revision` returned by
sealing, so delayed uploads cannot unlock a replacement track. Transcript changes
revoke dependent transferred evidence. Cross-video transfer requires observation
of the complete matching source cues; it does not infer word-level timing or a
uniform timing scale. Embedding-model changes require resealing with the current
model, while retaining direct observation for an unchanged track.

Captured context is limited to 48,000 characters. Video quizzes require at least 50 caption words.

### 2. Index content

`ml/rag_engine.py` splits text into approximately 220-word chunks with a 40-word overlap. It sends each chunk to Ollama's `/api/embed` endpoint using `embeddinggemma` and stores the vectors and metadata in ChromaDB.

The default local vector database is:

```text
data/chroma
```

Stored metadata includes topic, course, source, URL, timestamp, video position, dwell time, and ingestion time.

### 3. Retrieve evidence

When a learner asks a question or requests a quiz, the query is embedded with the same model. ChromaDB returns the closest chunks using cosine distance.

When active page content is supplied, retrieval is restricted to that exact document. This prevents unrelated saved material from leaking into a page-specific answer or quiz.

### 4. Generate an answer, lesson, or quiz

`ml/llm_service.py` sends the retrieved evidence to the configured Ollama model. The model must use only supplied evidence, cite chunk IDs, treat source content as untrusted data, report insufficient context, and produce English text.

Quiz output must match a Pydantic JSON schema. The backend checks that:

- every question has exactly four distinct choices
- the answer exactly matches one choice
- citations belong to retrieved chunks
- the evidence quote appears verbatim in cited material
- questions and answers overlap with their evidence
- questions are not duplicates
- output is in English using Latin script

Validated questions are retained. Only missing or invalid slots are regenerated,
with at most three model calls before rejection. Evidence quotations must occur
inside one cited chunk.

### 5. Evaluate and store quizzes

Complete generated quizzes, including correct answers, are stored on the server. The browser receives public questions and a `quiz_id`, not the answers.

On submission, the backend loads the stored quiz, evaluates answers, updates mastery, and saves the attempt. The default local database is:

```text
data/analytics.sqlite3
```

### 6. Build the dashboard

`GET /api/learning/data` derives courses, topics, history, activity, recommendations, and study events from ChromaDB metadata and persisted quiz attempts. React Query refreshes this data every 15 seconds.

## Adaptive scoring

### Quiz difficulty

```text
difficulty = clamp(mastery / 100 + 0.15 - error_penalty, 0.25, 0.85)
```

Each recent error contributes a `0.03` penalty, up to `0.15`.

- Below `0.50`: foundational recall
- `0.50` to `0.69`: intermediate comprehension
- `0.70` and above: advanced application and synthesis

### Mastery update after a quiz

```text
mastery_delta = (quiz_score - current_mastery) * 0.22
new_mastery = current_mastery + mastery_delta
```

### Dashboard mastery

```text
mastery = quiz performance * 0.40
        + time on section * 0.35
        + revisit frequency * 0.25
```

Time is capped at 100% after 15 tracked minutes. Revisit frequency is capped at 100% after five indexed documents for a topic.

## API reference

### Diagnostics and settings

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Ollama, model, ChromaDB, and analytics status |
| `POST` | `/api/settings/ai-config` | Change the active Ollama chat model |

### RAG and assessments

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/rag/topics` | List indexed topics |
| `POST` | `/api/rag/ingest` | Index pasted lesson material |
| `POST` | `/api/rag/retrieve` | Retrieve relevant chunks |
| `POST` | `/api/rag/ask` | Answer from active-source evidence |
| `POST` | `/api/rag/summarize` | Teach and summarize a source |
| `POST` | `/api/rag/generate-quiz` | Generate and store a grounded quiz |
| `POST` | `/api/rag/evaluate-quiz` | Score answers and persist mastery |
| `POST` | `/api/rag/stream-transcript` | Index a caption or selected-text segment |

### Dashboard and jobs

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/learning/data` | Return the complete dashboard dataset |
| `GET` | `/api/learning/topic-state` | Return one topic's state |
| `DELETE` | `/api/learning/history/{id}` | Delete a source and orphaned assessments |
| `GET` | `/api/recommendations/smart` | Return assessment-based recommendations |
| `POST` | `/api/jobs` | Start a slow AI operation |
| `GET` | `/api/jobs/{job_id}` | Poll job status and result |
| `POST` | `/api/f1/seal` | Seal learner/video caption vectors and return their revision |
| `POST` | `/api/f1/intervals` | Validate revision-bound observation batches and promote covered vectors |
| `GET` | `/api/f1/status` | Inspect scoped vectors, leases, answer cache, transfer, and residency |
| `POST` | `/api/runtime/player-state` | Apply playback state to the local residency policy |
| `POST` | `/api/rag/abandon-quiz/{quiz_id}` | Close a quiz's evidence lease |

Interactive API documentation is available at `http://127.0.0.1:8000/docs` while the backend is running.

## Dashboard screens

- **Overview**: courses, average mastery, quiz count, study events, recommendations, and activity
- **Courses**: captured course/source catalogue and topic telemetry
- **Mastery**: sortable topic scores, radar visualization, and signal breakdown
- **Practice**: manual note ingestion, quiz generation, and assessment history
- **Plan**: generated review events, retention chart, and `.ics` export
- **Next up**: impact-ranked recommendations
- **History**: captured pages/videos and deletion controls
- **Extension**: installation instructions and service status
- **Profile**: optional Google sign-in and Firestore profile editing
- **Settings**: Ollama model selection and pipeline health

## Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer
- npm
- Ollama
- Chrome or Microsoft Edge for the extension

## Installation and startup

### 1. Install Ollama models

```powershell
ollama pull embeddinggemma
ollama pull llama3.2:3b
```

Ensure Ollama is running at `http://127.0.0.1:11434`.

### 2. Install and start the backend

```powershell
cd chaigaram
pip install -r backend/requirements.txt
python -m uvicorn backend.app:app --port 8000 --reload
```

### 3. Install and start the frontend

In a second terminal:

```powershell
cd chaigaram/frontend
npm install
npm run dev
```

Open `http://localhost:8080`.

### Windows launcher

You can also run:

```powershell
cd chaigaram
.\start_all.bat
```

The launcher installs dependencies, builds the frontend, and starts both servers. It does not install or start Ollama.

## Browser-extension installation

1. Keep FastAPI running on port 8000.
2. Open `chrome://extensions` or `edge://extensions`.
3. Enable **Developer mode**.
4. Select **Load unpacked**.
5. Choose the `chaigaram/extension` directory.
6. Open an educational webpage or video with English captions.
7. Use the popup to open the assistant, learn the page, or save a selection.

The options page allows changing the backend and dashboard URLs.

## Configuration

Backend variables can be placed in `chaigaram/.env`:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBED_MODEL=embeddinggemma
OLLAMA_CHAT_MODEL=llama3.2:3b

# Optional remote ChromaDB
CHROMA_HOST=
CHROMA_PORT=8000
CHROMA_SSL=false
CHROMA_COLLECTION=chaigaram_lessons

# Optional PostgreSQL; SQLite is used when omitted
DATABASE_URL=
```

The frontend API URL can be configured in `frontend/.env.local`:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

## Mistake Notebook

Open **Mistakes** in the dashboard, or **Review missed questions** on the Practice
screen. Missed quiz questions are saved automatically with their original
assessment feedback. Older complete missed-question records are imported once.
Recall your answer, reveal the feedback, and choose **Again** or **Remembered**.

- Again schedules another review in 10 minutes and resets the spacing streak.
- Remembered schedules reviews after 1, 3, 7, 14, then 30 days, capped at 30 days.
- Due now and All cards include persistent progress and pagination.
- Self-review does not change assessment mastery. It needs no additional model
  or embedding calls; schedules are a simple practice heuristic.
- Cards whose cited evidence is held by an open quiz hide their question and
  feedback until the hold closes. History deletion removes cards when it removes
  the topic's remaining sources and assessments.

See [notebook and app verification](docs/MISTAKE_NOTEBOOK_VERIFICATION_2026-10-02.md)
for the behavior, tests, and evidence limits.

## Optional Firebase login

Firebase is used only for Google authentication and profile documents. Add these values to `frontend/.env.local`:

```dotenv
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_APP_ID=
```

Enable Google authentication, create Firestore, and publish `frontend/firestore.rules`. See `frontend/FIREBASE_SETUP.md` for details.

## Tests and verification

Run backend tests:

```powershell
cd chaigaram
python -m unittest discover -s tests -v
```

Run extension behavior checks:

```powershell
node --test tests/observation.test.cjs tests/extension_jobs.test.cjs tests/connection.test.cjs
```

Type-check, lint, and build the frontend:

```powershell
cd chaigaram/frontend
npx tsc --noEmit
npm run lint
npm run build
```

Tests cover observation gating, restart recovery, grounded quiz validation and selective repair, history deletion, recall-prioritized byte-bounded result and query-vector caches, recall forecasts, recommendations, and the HTTP routes. For a disposable live model and Chrome run, see [feature verification](patent/03_FEATURE_VERIFICATION.md) and its reproduction commands in [architecture and security](patent/02_ARCHITECTURE_AND_SECURITY.md). The [feature matrix](patent/04_PRIOR_ART_FEATURE_MATRIX.md) maps the patent comparison language to implementation and tests.

The [deep feature interaction audit](patent/06_DEEP_FEATURE_INTERACTION_AUDIT_2026-10-02.md)
records concurrency, replay, fault-recovery, transfer, and residency
fixes and verification. The [first patent-feature audit](patent/05_PATENT_FEATURE_AUDIT_2026-10-02.md)
retains its earlier results. Run `python scripts/check_patent_features.py` for real local embedding,
cache, transfer, lease, and restart checks on disposable caption data. Run live
browser/model checks separately from large benchmarks to reduce resource contention.

The [Mistake Notebook verification](docs/MISTAKE_NOTEBOOK_VERIFICATION_2026-10-02.md)
records the current full app checks, including the new review workflow and its
interaction with quiz evidence holds.

## Current limitations

- FastAPI endpoints do not currently require authentication.
- Learning data is global to one backend instance and is not separated by Firebase user ID.
- CORS defaults to local dashboard origins and Chrome extension origins. Configure `CORS_ORIGINS` for a different dashboard; CORS does not provide authentication.
- Background AI jobs persist in SQL and resume after restart. Run one backend process: cross-process worker leases are not implemented. Interrupted model calls may repeat if their output was not yet checkpointed.
- Study events are generated dynamically rather than persisted as editable tasks.
- The active generator and its calibration metadata support MCQs only.
- Difficulty currently uses mastery and recent errors; other signals are displayed but do not directly change difficulty.
- Firebase protects profile documents only, not ChromaDB or quiz analytics.
- `start_all.bat` does not verify or start Ollama.

## Privacy

With the default configuration, lesson content, embeddings, and quiz analytics remain on the local machine. The extension sends captured page text, selections, and available timestamped caption tracks to the configured backend. Tracks may include future captions; these remain outside the searchable index until the corresponding playback intervals have been observed.

If the backend, ChromaDB, PostgreSQL, or Ollama URL is changed to a remote service, captured content will be sent to that service and should be protected with authentication and transport security.
