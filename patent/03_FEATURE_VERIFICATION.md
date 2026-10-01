# Feature verification — 2026-09-27

This is a historical verification snapshot. The later F1/A–E implementation and
follow-up regression audit are recorded in
[the 2026-10-02 audit](05_PATENT_FEATURE_AUDIT_2026-10-02.md).

This report describes the working tree on `patent/observation-gated-vector-system`.
The initial audit is in `00_IMPLEMENTATION_AUDIT.md`; the architecture, state
transitions, threat boundary, and reproduction steps are in
`02_ARCHITECTURE_AND_SECURITY.md`. The phrase-by-phrase implementation map and
prior-art references are in `04_PRIOR_ART_FEATURE_MATRIX.md`.

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
  repairs failed slots. The prompt gives the local model exact quote choices
  copied from source chunks; validation still checks the cited source. Public
  quiz responses omit answer keys; grading uses the persisted server copy.
  Model answer formatting is normalized only when it
  unambiguously selects an existing choice.
- Bounded byte accounted TTL caches serve identical ACTIVE retrievals and reuse
  query embeddings across ACTIVE search scopes. They clear on vector or assessment
  mutations. Lower predicted recall raises cache admission and retention priority;
  LRU breaks ties. Recall forecasts use prior assessment outcomes
  after enough training pairs, otherwise a labelled cold start heuristic.
  Unassessed topics have no probability.
- Diagnostics show state counts, job and cache counters, and recall training
  status. The dashboard labels mastery, difficulty, and curves according to
  their actual methods. A legacy migration endpoint copies only explicitly
  compatible document vectors; it leaves uncertain provenance untouched.

## Automated results

- Python: `python -m unittest discover -s tests -q` — 41 passed. This includes
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
  its 41 passing tests; this is not counted as a test failure. One concurrent
  run timed out on a five-second background-job assertion under Chrome/model
  load; the isolated rerun passed.
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
  validation. A first live rerun failed after `llama3.2:3b` returned invalid
  quotes or duplicate questions on three calls. After adding source-derived
  quote choices, the [live rerun](results/live_models.json) and the dashboard's
  three-question Chrome quiz passed. A short 60-word lesson had also produced
  a retryable 503 in earlier testing. Stochastic model output can still fail;
  the UI exposes retry instead of accepting ungrounded questions.
- [Synthetic benchmark](results/benchmark.json), [raw trials](results/retrieval_trials.csv),
  and [chart](results/benchmark.png): 30 trials per retrieval mode. Median
  retrieval was 2.41 ms with no caches, 3.14 ms with only the query-vector
  cache, and 0.0064 ms with both caches; embedding calls were 30, 1, and 1.
  The synthetic embedding cost is tiny, so the query-vector-only mode does not
  demonstrate a latency improvement. Promotion made zero embedding calls and a
  skipped SEALED chunk stayed absent from results. These numbers isolate pipeline overhead using
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
