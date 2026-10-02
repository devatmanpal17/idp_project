# Deep patent-feature interaction audit - 2026-10-02

This follow-up audits the working tree after commit
`ce4a5548b7ef6c40fb7f30fe82cc9f7781070ecf` on `patent/features-a-e`.
It extends the [first audit](05_PATENT_FEATURE_AUDIT_2026-10-02.md), preserving
that report's historical results. The emphasis is interactions between F1
observation, A evidence leases, B answer caching, C residency, D transfer,
E micro/macro retrieval, and durable job publication.

The results establish the behavior of the exercised cases. They do not establish
zero undiscovered bugs, universal semantic correctness, or patentability.

## Reproduced defects and corrections

| Interaction | Defect demonstrated | Correction and regression evidence |
|---|---|---|
| D lexical alignment | Punctuation removal made `x > 5` and `x < 5`, `!=` and `==`, `-5` and `5`, `a_b` and `ab`, and `left-right` and `leftright` equivalent. Changed target cues could be activated without observation. | Alignment preserves exact whitespace-separated tokens, including operators, case, signs, and punctuation. Five adversarial pairs remain sealed. |
| F1 rolling captions | Case folding and punctuation removal erased meaningful changes from successive cues, including comparison operators and variable case. | Deduplication requires exact token equality. Four changed-cue cases retain both meanings. This deliberately favors evidence preservation over aggressive deduplication. |
| A/F1 concurrent generation | An answer or summary could publish context after another request leased it. Replacing captions during model work could publish an outdated answer. | Snapshot evidence before model work and validate eligibility, content, model version, and revision immediately before publication under the RAG lock. Unsafe output fails with 422 and is not cached. |
| A quiz publication | A competing lease or revision change during generation could cause a saved quiz with no safe publishable evidence. | Validate before saving the quiz and open its evidence lease under the same RAG lock. The controlled lease/revision races reject before saving. |
| A/B index deletion fault | SQL demotion could commit while Chroma deletion failed, leaving a hot retrieval result or a global index query able to return leased evidence. | Invalidate caches before deleting index entries. Legacy/global retrieval checks authoritative SQL eligibility on cached and fresh results. Injected deletion faults return no protected evidence. |
| A recovery | An interrupted restore followed by same-process recovery could leave a cached empty result after evidence had been restored. | Clear retrieval caches before restoration and after recovery. The failure/retry regression returns restored evidence without re-embedding. |
| D persisted activations | Fixing the matcher alone left incorrect activations produced by the old matcher searchable after restart. | Record transfer policy versions. Startup revokes and rechecks old-policy activations against direct observation and exact cue matching. A durable recheck queue survives an index fault; valid transfers recover and invalid transfers stay sealed without new embedding calls. |
| B/C configuration changes | Switching the chat model away and back during generation could publish/cache an answer under a configuration it did not consistently use. | Increment a configuration version on each successful configuration update and validate it before publication. Serialize settings updates with publication. A switch-away-and-back test rejects the output and leaves the answer cache empty. |
| C aliases and unmanaged requests | `chat` and `chat:latest` could receive different dwell behavior. An unrelated or retired model request could receive an indefinite pin. | Compare canonical model names and give unmanaged requests the configured finite TTL. Alias and unmanaged-request regressions pass. |
| C retired model pins | Switching models retained a controller-managed old chat pin. A request could pin before the worker's next sample; an in-flight request could also finish after an early retirement attempt. | Queue retirement for controller pins and request pin intents, respect cooldown, and register completed requests so late old-model pins are retired again. The embedder and unrelated models are preserved in the tested switch cases. Freeze the request's model name for its model/keep-alive pair. |
| A/F1 durable output replay | Completed job reads and checkpoint resume bypassed current evidence checks. Uncited answers and cache hits could not be protected by inspecting public citations alone. | Collect private proofs for all retrieved evidence, including cache hits. Validate on completion, resume, and completed-job reads. Changed/leased stored output returns 409. Proofs and checkpointed output remain absent from public checkpoints. |
| A owning quiz delivery | Applying a general lease check to durable quiz delivery also blocks the quiz that owns the lease. | Allow demoted evidence only when its sole open lease belongs to that output's quiz. Another lease blocks delivery. Normal delivery, validated-checkpoint resume, second-lease blocking, restoration, and a real three-question durable quiz are tested. |

The generation tests release the RAG lock during model work. One test uses
events and a separate thread to open a lease while generation waits, then checks
that publication rejects without deadlock. A seeded 100-operation trace mixes
observations and overlapping lease opens/closes; after every operation it
compares SQL ACTIVE/unleased IDs to the actual Chroma IDs and checks nonnegative
reference counts. This is one reproducible trace, not exhaustive concurrency
exploration.

## Verification results

| Check | Result | Evidence scope |
|---|---|---|
| Complete Python suite | 101 passed, 0 failures | Includes 17 new interaction tests and five additional residency tests beyond the first audit's 79. Uses temporary SQLite/Chroma and controlled embedding/model doubles for invariants. |
| Complete extension Node suite | 12 passed, 0 failures | All four `*.test.cjs` files, including concurrent learner/sequence persistence. |
| Scoped real Ollama acceptance | 9 passed | Real `embeddinggemma` vectors and `llama3.2:3b` generation, F1/E coverage, D transfer, B cache, A lease/restart/restore, revision revocation, and real durable quiz/answer delivery. |
| General real Ollama smoke | 5 passed | Real embedding, retrieval, grounded answer, summary, and three-question grounded quiz. |
| Complete Chrome acceptance | 22 passed; 20 layout checks passed | Real quiz/assessment, extension durable article requests, settings, history deletion, and real video seek. No captured runtime exceptions or API errors. |
| Batched benchmark | 400 rows; 15 successful real residency trials | Seed 0, five repeats, 1k/10k/100k generated vectors. Real trials explicitly unload/preload the installed chat model between cold, fixed TTL, and controller pause conditions. |
| Real Ollama pin retirement | Passed, two old-chat unloads | A request pin before the worker's next tick and a simulated late request completion both release the switched-away real model while preserving the embedder. |
| Python compilation and whitespace integrity | Passed | `compileall` and `git diff --check`. |

The benchmark's generated fixtures report zero leased-evidence leakage, restored
recall@5 of 1.0, zero exact-cache false-positive/false-negative rates, and zero
offset mapping error. These generated-vector metrics do not measure all Chroma
or real-transcript behavior. The real C results measure short local pause traces;
switch/race coverage comes from the separate residency regressions and a direct
real transport check. That transport check uses an uninstalled sentinel as the
new configured name, but never loads it: each tick returns after unloading the
retired installed chat model. It reproduces retirement bookkeeping, not a live
generation race between two different chat models.

The Chrome seek run observed `[100, 2100]` and `[8000, 10100]` ms of a
12-second video. Two observed captions were ACTIVE; the skipped caption stayed
SEALED and its secret phrase was absent from retrieval. All 20 desktop/mobile
route checks had no broken images or document-level horizontal overflow.
Desktop and mobile contact sheets were visually reviewed. Chrome's fixture
uses the legacy observation route; the separate scoped live test exercises
learner/video patent paths and durable quiz delivery.

The live durable check delivers three questions without answer keys, hides a
previous durable answer while the quiz's lease is open, and makes the saved
answer readable again after closing the lease without regenerating it. Unit
tests additionally cover an uncited answer, a cached answer, a caption revision
after completion, and process interruption after VALIDATING followed by resume.

## Reproduction and evidence

From the repository root, with Ollama running and both installed models available:

```powershell
python -m unittest discover -s tests -v
node --test tests/*.test.cjs
python scripts/check_patent_features.py --output benchmarks/results/patent-deep-audit-20261002/live_features.json
$env:CHAI_LIVE_CHECK_OUTPUT = 'benchmarks/results/patent-deep-audit-20261002/live_models.json'
python scripts/check_live_models.py
$env:CHAI_BROWSER_CHECK_OUTPUT = 'benchmarks/results/patent-deep-audit-20261002/browser'
python scripts/check_browser.py
$env:OPENBLAS_NUM_THREADS = '1'
python -m benchmarks.run_all --seed 0 --repeats 5 --real-ollama
python -m compileall -q backend ml tests scripts
git diff --check
```

Run live model/browser checks and the real residency benchmark sequentially.
Use disposable `DATABASE_URL` and `CHROMA_PERSIST_DIR` when running the Python
suite if the default local store contains learning data. The three live check
scripts create their own temporary stores. The browser script also creates a
separate Chrome profile and cleans up its own servers/browser processes.

Local raw evidence, intentionally ignored by Git, is under
`benchmarks/results/patent-deep-audit-20261002/`:

- `python-final.log`: final full Python suite.
- `live_features.json`, `live_models.json`: real model checks and their timings.
- `live_residency_switch.json`: the direct real managed-pin/late-completion
  retirement check, preserving the embedder during both retirements.
- `browser/browser_checks.json` and contact sheets: real Chrome results,
  playback observations, runtime/API error captures, and layout evidence.
- `benchmarks/results/20261002T100123Z/raw.json`, `raw.csv`, and `summary.md`:
  the final benchmark's 400 rows, trial conditions, timings, and metadata.
- `initial-regressions.log`: the first six interaction test methods produced
  13 failing assertions before fixes, including operator and rolling-cue subcases.
- `additional-regressions.log`: subsequent model-switch, old transfer policy,
  and restore-cache failures; this intermediate run also contains one test
  harness sequence error, which was corrected and is not counted as a product bug.
- `durable-before-fix.log`: the stored-answer lease check failed against the
  previously committed job route. The new route was restored afterward.
- `residency-regressions.log` and `request-pin-before-fix.log`: failures for
  retained pins, unmanaged requests, and a request pin before the worker tick.

The first live attempt encountered a stopped Ollama service and a connection
refusal. Starting the installed local service enabled the successful runs.
That setup failure is separate from the reproduced application defects.

## Compatibility and remaining boundaries

- Existing completed video jobs without private evidence proofs return 409;
  submit a fresh request. They cannot be safely grandfathered into replay.
- Source changes or leases during generation can now return 422; retry after
  the source is current and the competing quiz closes. A completed job blocked
  by a lease can become readable after restoration, without another model call.
- Exact case/punctuation matching reduces transfer recall for harmless caption
  edits. Re-sealing under the stricter rolling-caption policy can change chunk
  IDs and legitimately require embeddings for newly assembled text. Policy
  rechecking existing transfers reuses stored vectors.
- A publication check suppresses an unsafe late response; it cannot remove
  context already sent to an in-flight model or revoke text already delivered
  to a client. Durable jobs and locks still support one backend process.
- On an index deletion fault, SQL eligibility prevents returning held rows.
  Filtering stale top-k entries can reduce retrieval availability until index
  recovery; this audit does not claim uninterrupted availability under faults.
- Evidence leases protect the indexed evidence and scoped/aligned counterparts
  selected by their policy. They do not prove universal blocking of equivalent
  information in independently ingested pages, paraphrases, user-supplied chat
  history, or model knowledge.
- C still uses a global player state, sampled residency, dwell, and cooldown.
  It is not a hard memory cap or a proven competing-tab priority policy. Short
  local trials do not establish behavior over a complete viewing session.
- The first audit's client-reported observation, unauthenticated local API,
  learner identity, semantic generation, and cross-platform limits still apply.
  PostgreSQL deployment was not exercised here; the patent persistence paths
  contain existing SQLite-specific SQL and must not be represented as verified
  PostgreSQL support.
