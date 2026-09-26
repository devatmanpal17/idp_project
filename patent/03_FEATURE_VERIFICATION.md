# Feature verification — 2026-09-23

This report describes the working tree on `patent/observation-gated-vector-system`.
The initial audit is in `00_IMPLEMENTATION_AUDIT.md`; the architecture, state
transitions, threat boundary, and reproduction steps are in
`02_ARCHITECTURE_AND_SECURITY.md`.

## Implemented feature scope

- Video caption chunks remain SEALED outside Chroma search until a claimed,
  decoded and visible playback interval covers them. An observation request
  promotes only covered chunks. Rewinds and seeking do not grant a skipped
  interval. A track source change resets capture state. Observation attaches
  promptly when a video appears, so opening segments are not lost to the slower
  transcript sync interval.
- SQL backed jobs preserve request identity, checkpoints and results across a
  single backend process restart. Interactive work has separate capacity from
  future caption speculation. Deletion cancels linked work. An eligible sealed
  embedding can be promoted without another model embedding call.
- Quiz generation validates each slot against its cited source and selectively
  repairs failed slots. Public quiz responses omit answer keys; grading uses the
  persisted server copy. Model answer formatting is normalized only when it
  unambiguously selects an existing choice.
- A bounded byte accounted TTL cache serves identical ACTIVE retrievals and is
  cleared on vector mutations. Recall forecasts use prior assessment outcomes
  after enough training pairs, otherwise a labelled cold start heuristic.
  Unassessed topics have no probability.
- Diagnostics show state counts, job and cache counters, and recall training
  status. The dashboard labels mastery, difficulty, and curves according to
  their actual methods. A legacy migration endpoint copies only explicitly
  compatible document vectors; it leaves uncertain provenance untouched.

## Automated results

- Python: `python -m unittest discover -s tests -v` — 38 passed. This includes
  HTTP acceptance, real disposable SQLite and Chroma state, crash points,
  deletion, migration, cache and recall behavior, source validation, and jobs.
- Extension: `node --test tests/observation.test.cjs tests/extension_jobs.test.cjs tests/connection.test.cjs`
  — 7 passed. These exercise interval math, actual content-script job retry and
  navigation behavior in a browser-service harness, and URL validation.
- Frontend: TypeScript check and Vite build passed. ESLint reported zero errors
  and eight existing `react-refresh/only-export-components` warnings in shared
  component modules.
- JavaScript syntax and `git diff --check` passed. The Python test process also
  emitted a shutdown `ResourceWarning` for an unclosed SQLite connection after
  its 38 passing tests; this is not counted as a test failure.
- [Real local model run](results/live_models.json): embedding, retrieval,
  grounded answering, summarization, and quiz generation passed with
  `embeddinggemma` and `llama3.2:3b` on disposable data.
- The final [real Chrome extension and dashboard run](results/browser_checks.json)
  passed all 22 checks with zero captured runtime exceptions or API errors.
  It completed the dashboard's three-question live quiz and grading, document
  ingestion, ten routes, settings save and diagnostics, mobile theme and
  navigation, calendar export, history deletion, and extension options,
  article summary and question. It played a locally decoded WebM and sought
  over one caption: reported intervals were `[100,2100]` and `[8000,10100]`
  milliseconds, leaving two captions ACTIVE and the skipped caption SEALED.
  The skipped phrase was absent from retrieved chunks.
- [Desktop](results/ui_desktop.png) and [mobile](results/ui_mobile.png) contact
  sheets show the ten dashboard routes at 1422px and 390px respectively. All
  20 captures had no page-level horizontal overflow or broken images. Visual
  review found no obvious overlap or clipping; the course detail table has
  its own horizontal scroll on mobile. The [light mobile settings view](results/ui_light_mobile.png)
  was also visually reviewed. A React hydration mismatch found during testing
  was fixed by rendering a stable initial route placeholder; the final Chrome
  run captured no runtime exceptions.
- Prompt-local citation labels map back to persistent chunk IDs before
  validation. One earlier live rerun with a short 60-word lesson returned a
  retryable 503 when `llama3.2:3b` exhausted three repair calls on duplicate
  questions. The final fuller lesson passed, but the short-input model-quality
  limit remains; quiz generation cannot be guaranteed for every source.
- [Synthetic benchmark](results/benchmark.json), [raw trials](results/retrieval_trials.csv),
  and [chart](results/benchmark.png): 30 trials per retrieval mode. Median
  uncached retrieval was 15.32 ms versus 0.058 ms cached; embedding calls were
  30 versus 1. Promotion made zero embedding calls and a skipped SEALED chunk
  stayed absent from results. These numbers isolate pipeline overhead using
  deterministic synthetic embeddings. They are not real model throughput or a
  general speedup estimate.

## Boundaries

Generated content can still be wrong; validators check structure and source
quotations, not all semantic claims. Observation is client reported, not
tamperproof. Backend endpoints currently lack authentication and per-user data
isolation. The job runner supports one process, not distributed workers. Model
calls interrupted before checkpointing may repeat. The recall model has only
in-sample diagnostics; its out-of-sample accuracy is unmeasured. Google login,
remote services, and third-party site caption variants need checks in their
respective environments. These boundaries prevent any claim that every possible
use has no errors.
