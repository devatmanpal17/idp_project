# Implementation audit — 2026-09-21

## Repository and preservation

Active repository: `C:/Users/Maan/Desktop/idp/chaigaram`, baseline `80925e7`.
The parent directory is not a Git repository; its README describes the older
TF-IDF application. No AGENTS.md or nested application repository was found.
Working branch: `patent/observation-gated-vector-system`.
Pre-existing uncommitted changes: `ml/llm_service.py` (180-second timeout and
connection/timeout error distinctions), `tests/test_chat_assistant.py` (two tests
for those distinctions). Preserve these changes; do not include them in our commits.

## Architecture and data flow

The MV3 content script extracts page text, native text tracks, YouTube JSON3
captions, and visible caption text. background.js bridges requests to FastAPI.
React/TanStack is a separate HTTP client, with optional Firebase profile support.
`ml/rag_engine.py` chunks at 220 words with 40-word overlap, calls Ollama
`/api/embed`, and upserts into one persistent cosine Chroma collection.
`backend/routes/rag.py` ingests caller context before ask/summary/quiz retrieval.
`ml/llm_service.py` uses local Ollama generation. SQLAlchemy persists quizzes and
attempts in `data/analytics.sqlite3`, or configured PostgreSQL. Chroma stores text,
vectors and source metadata separately in `data/chroma` or configured server.

## Existing real features

Document capture, semantic search, local model requests, persisted quiz answer
keys, server-side grading, learning history deletion, and dashboard aggregation
are implemented. Quiz public responses withhold answer/why/evidence_quote.
Validation includes Pydantic schema, English/script checks, citation allow-list,
quote containment, question duplication and evidence token overlap.

## Limitations and misleading claims

* Video capture accepts all caption starts <= currentTime + 1 second. Forward
  seeking incorrectly admits skipped captions. Temporal envelopes are discarded.
* Every embedding enters the same searchable index. No SEALED lifecycle exists.
* Raw context ingestion can bypass any future observation restriction unless all
  generation endpoints are changed together.
* Jobs are an in-memory dictionary backed by a two-thread executor. MV3 polling
  retries exist, but backend restart loses jobs and content script reload loses IDs.
* A failing quiz question regenerates the entire quiz, up to three calls.
* Mastery is a weighted heuristic and fixed-rate update, not Bayesian inference.
  Difficulty/IRT curves have fixed parameters, not estimated item parameters.
* Recommendation scores and review schedules are deterministic heuristics from
  persisted data. No trained recall predictor, controlled hot-cache or benchmarks.
* CORS allows every origin with credentials. Backend has no user authentication.
  Extension URLs are only loosely validated; host permissions cover all webpages.
* `/simulator` currently provides extension setup; its route name is historical.
  Old `streamSimulatorTranscript` client helper remains. Greeting canned responses
  are conversational shortcuts, not fake RAG. UI sidebar random widths are skeleton
  presentation. Neither provides patent evidence.
* Ordinary ask allows general-knowledge responses when evidence is absent; vector
  access control cannot guarantee a model never independently knows a future fact.

## Baseline validation

`python -m unittest discover -s tests -v`: 11 passed. Tests use mocked LLM/route
dependencies; no real embedding/promotion/browser interruption integration tests.
`npx.cmd tsc --noEmit`: passed. `npm.cmd run build`: passed, with existing bundle
size/tsconfig plugin warnings. PowerShell blocks npx.ps1; use npx.cmd/npm.cmd.
No baseline benchmark harness exists. No speedup measurements claimed.

## Planned file changes

Extension: manifest.json, content.js, background.js, popup.js; new observation.js.
Backend: models.py, app.py, routes/rag.py, routes/jobs.py, routes/learning_data.py;
new routes/vectors.py. ML: rag_engine.py, calibration.py; new temporal.py,
vector_state.py, scheduler.py, persistent_jobs.py, vector_cache.py, recall.py,
selective_repair.py, metrics.py. Integrate selective repair in llm_service.py while
preserving the user's timeout edits. Frontend: settings diagnostics and truthful
mastery/curve labels. Add integration/fault tests, benchmark runner/raw results,
architecture/state/security/demo documents and figures.

## Design decisions before implementation

Store sealed embeddings and temporal metadata in the existing SQL database, outside
ANN. Use a new model-versioned ACTIVE Chroma collection. Copy compatible ordinary
webpage vectors from the old collection without inference; historical video vectors
require re-ingestion. Keep the old collection untouched as a migration source.
Use deterministic chunk IDs, a durable promotion intent, idempotent Chroma upsert,
then SQL ACTIVE commit. Observation intervals, not playback position, govern access.
Do not claim atomic distributed transactions between SQL and Chroma. Document and
test recovery after the inter-store commit boundary. Local backend operates with
one process; multi-process coordination must be explicitly addressed before scale-out.
