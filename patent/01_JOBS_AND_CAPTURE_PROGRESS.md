# Durable jobs and capture integration — 2026-09-21

This records the first implementation milestone. The later feature work and final
verification are documented in `02_ARCHITECTURE_AND_SECURITY.md` and
`03_FEATURE_VERIFICATION.md`; the counts and remaining-work list below are a
snapshot from this date.

## Implemented in this working tree

- SQL job ledger with idempotent request IDs, atomic job claiming, checkpoints,
  restart recovery, and completed results. Saved validated generation output is
  reused after a crash before the terminal status write.
- A dedicated speculation worker. Admission uses a cold-start probe, an EWMA of
  measured embedding time, queue depth, an estimated memory allowance, and a
  five-minute future horizon. Observed chunks take priority even after rewinding.
- Persisted embeddings are reused when a job resumes after the embedding write
  but before its job checkpoint. Promotion remains a separate, recoverable step.
- Document deletion and transcript revision invalidate attached jobs and clear
  their payloads, checkpoints, and results. Late job completion cannot restore
  a cancelled result.
- Extension capture sends timestamped transcripts and observed intervals.
  Interactive actions drain observed embedding batches before generation;
  background work may prepare sealed future chunks during idle periods.
- Retrying an unchanged AI payload reuses a request ID saved in extension storage.
  Navigation during observation upload stops the old capture from scheduling
  work against the new document. Official tracks are not mixed with visible cues.
- CORS defaults to local dashboard URLs and Chrome extension origins.

## Validation

`python -m unittest discover -s tests -v`: 25 passed, including real SQLite/Chroma
tests with deterministic test embeddings. Fault tests cover interruption after
embedding persistence and after validated generation output persistence.

`node --test tests/observation.test.cjs tests/extension_jobs.test.cjs`: 5 passed.
Tests exercise the actual content-script functions with browser services stubbed,
including a lost start response, page navigation, and multiple observed batches.

`npx.cmd tsc --noEmit`, `npm.cmd run build`, and syntax checks for the modified
extension scripts passed. Build retains its existing chunk-size and tsconfig-path
plugin warnings. No live Chrome interruption or real Ollama throughput measurement
was performed; no measured speedup is claimed.

## Boundaries and remaining audit work

Use one backend process. Recovery has no distributed lease or cross-process worker
ownership. A model call interrupted before its output checkpoint can run again;
quiz creation and job completion are not one SQL transaction. Deletion prevents
publication of cancelled job results, but cannot undo an already-running model
call or automatically roll back every handler side effect.

The memory allowance is an admission estimate, not measured process RSS or an
implemented hot cache. One in-flight embedding call may exceed its nominal time
budget. Direct RAG HTTP requests and generation jobs suppress further speculative
chunks, but cannot preempt an already-running embedding call.

Observation proofs are client-reported and do not establish tamper-proof viewing.
Future caption text may be stored and embedded locally while sealed. Model prior
knowledge is outside the retrieval gate. Backend authentication remains absent.

Extension retries require the same payload; the assistant UI is not automatically
restored after reload. Continuously changing live caption snapshots invalidate
prior transcript revisions and may cause repeated work.

The broader audit plan still includes selective quiz repair, a controlled hot
cache, recall modeling, frontend diagnostics/label updates, benchmark artifacts,
and architecture/security/demo documents. Those are not completed by this step.
The pre-existing Ollama timeout edits remain preserved in the working tree.
