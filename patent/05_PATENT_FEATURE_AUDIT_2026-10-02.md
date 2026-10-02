# Patent-feature implementation audit — 2026-10-02

For the subsequent concurrency, durable replay, and fault-recovery audit, see
[deep feature interaction audit](06_DEEP_FEATURE_INTERACTION_AUDIT_2026-10-02.md).
The results below describe the first audit and retain their original counts.

This audit covers the working tree on `patent/features-a-e`, starting from
`e9ac2adaf3f96b20a045ab09e779f8a4b25f9cca`. Work began on October 1 and continued
on October 2, local time. It includes F1 observation-gated indexing, A evidence
leases, B answer-cache validity, C model residency, D cross-video transfer, and
E micro/macro retrieval, together with the API, extension, frontend, and jobs.
The verification results apply to the fixes recorded in the commit containing
this report.

This is engineering verification, not a certificate of zero undiscovered bugs
or a conclusion about patentability. The guarantees below refer to the tested
inputs and configuration. Historical reports retain their original results.

## Defects reproduced and corrected

| Area | Reproduced defect | Corrected behavior and evidence |
|---|---|---|
| F1/E caption spans | Overlapping captions could produce a chunk ending before an earlier cue ended. | Chunk bounds use the minimum start and maximum end; partial coverage cannot unlock the longer caption. |
| F1 revision reset | A new caption revision reset the sequence but retained old batch rows, causing a uniqueness error. | Reset also removes prior-revision batch rows; sequence reuse on the new revision passes. |
| F1 delayed uploads | Observation from the previous caption track could unlock replacement captions. | Seal returns a SHA-256 revision incorporating captions and duration; the HTTP interval endpoint requires that revision and rejects stale uploads before mutation. The extension propagates it. |
| F1 model isolation | Sealed vectors from an older embedding model could enter the current model's collection. | Recovery, promotion, retrieval, transfer, and cache reads select the current embedding version; resealing rebuilds mismatched vectors. |
| F1 model tags | When several Ollama tags shared a model name, startup could use the first tag's digest. | Startup resolves the exact requested tag, including the implicit `latest` alias. A missing digest/tag is marked unresolved. Both wrong-tag cases failed before the fix and pass now. |
| F1 embedding integrity | Invalid floats or inconsistent dimensions could persist an unusable batch. | Reject empty, boolean, nonnumeric, nonfinite, overflowing float32, and inconsistent-dimension vectors; regression checks verify batch rollback. |
| D timing alignment | Uniform time interpolation across a lexical block could credit unseen words when cue durations differed. | Map each complete target cue to its corresponding full source cue spans; all those source spans must be directly observed. Offset copies, trimmed introductions, inserted passages, middle clips, and unequal timing are covered. |
| D source revisions | A changed source caption track left its transferred evidence searchable elsewhere. | Revoke downstream transferred rows, remove their index entries, invalidate affected caches, and re-promote only independently observed target coverage. |
| A aligned counterparts | Linear timing projection could miss a re-upload counterpart during a quiz lease. | Hide overlapping aligned target cue spans using the same cue mapping as transfer. Multiple leases, newly sealed copies, expiry, restart, and final-close restoration are tested. |
| B question identity | Whitespace normalization could conflate questions about different quoted strings. | Versioned cache keys preserve question case and internal whitespace; top-k evidence validity remains checked on reads and mutations. |
| C settings | Changing the chat model left the residency controller preloading the old model. | Settings synchronize the controller's model under its lock; a regression verifies preload targets. |
| Extension observation | Fractional frame rounding introduced artificial 1 ms gaps, and callback/compositor submission jitter broke continuously displayed intervals. | Preserve the continuous run's outer boundaries. Use `expectedDisplayTime` from the frame callback, with submission/callback timestamps as fallbacks. Seek, rate-change, visibility, stall, and implausible-jump guards remain tested. |
| API inputs | Ambiguous scope separators, incomplete key pairs, noninteger sequence values, and nonfinite JSON inputs could bypass intended validation or produce a validation-response 500. | Constrained scope keys, paired scope validation, strict integer sequences, bounded/finite numbers, and a JSON-safe validation handler return controlled errors. |
| Frontend verification | Eight Fast Refresh lint warnings obstructed a zero-warning check. | Move reusable plain exports into separate modules and keep unused helpers local; lint passes with `--max-warnings 0`. |
| Benchmark harness | Dense 1,000-by-100,000 score matrices and scratch copies created substantial memory pressure during simultaneous browser/model checks. | Evaluate batches of 32 queries; compare batch sizes 1, 7, and 32 against a dense reference. Run live acceptance separately from benchmark workloads. |

The first five new invariant regressions produced four failures and one error
before their fixes. The exact-tag regression later produced two failing
subcases before its fix. Failures were used to validate the tests' ability to
detect the defects rather than merely matching the implementation.

Chrome's native frame samples showed a media delta of 100 ms while successive
submission timestamps differed by approximately 28–49 ms. Expected display
timestamps remained approximately 98–100 ms apart. The clock choice follows
the distinction documented in
[MDN's requestVideoFrameCallback API reference](https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/requestVideoFrameCallback).
The focused playback fixture watches the opening and ending of a 12-second
video while seeking over a caption containing “copper lantern”; that skipped
caption must remain outside retrieval.

## Verification results

| Check | Result | Scope |
|---|---|---|
| Python suite | 79 tests passed, 0 failures | Real temporary SQLite/Chroma; deterministic embeddings for invariant tests; API, jobs, guardrails, cache, leases, transfer, residency, revision, and recovery. |
| Node extension suite | 12 tests passed, 0 failures | Durable request/learner/sequence behavior, source changes, frame timing, seeks, hidden playback, and revision propagation. |
| Extension syntax and Python compilation | Passed | Extension JavaScript syntax and Python source compilation. |
| Frontend ESLint | Passed with 0 errors and 0 warnings | `npm run lint -- --max-warnings 0`. |
| TypeScript | Passed | `npx tsc --noEmit`. |
| Production build | Passed | Existing bundle-size and Nitro `inlineDynamicImports` advisories remain; these are not compile failures. |
| General live Ollama smoke | 5 checks passed | Real document embedding, retrieval, answer, summary, and a grounded three-question quiz. |
| Scoped live Ollama acceptance | 8 checks passed | F1 sealing/promotion, E parent eligibility, D vector reuse/transfer, B cache hit, A hiding/restart/restoration, and revision revocation. |
| Complete Chrome acceptance | 22 checks passed; 20 layout checks passed | Desktop/mobile routes, extension, settings, real quiz/assessment/history, and actual seek playback; no captured runtime exceptions or API errors. |
| Batched benchmark | Completed: 400 rows, including 15 successful real residency trials | Seed 0, five repeats, 1k/10k/100k vectors; 250 comparable non-timing synthetic rows match the earlier dense run within numerical tolerance. |
| Whitespace integrity | Passed | `git diff --check`. |

Live feature checks use real `embeddinggemma` embeddings and `llama3.2:3b`
responses. The report records the embedding digest. A live cache hit returns
the saved response without another query embedding. Lease restoration checks
that stored vector bytes and IDs remain identical and that evidence is not
re-embedded. It also checks that the restored source is retrievable.

The final Chrome playback produced observed intervals `[100, 2100]` and
`[8100, 10100]` ms, with two ACTIVE captions and one SEALED skipped caption.
The skipped secret phrase was absent from retrieval. All 20 route/viewport
captures had no broken images or document-level horizontal overflow; the
desktop and mobile contact sheets were also visually reviewed. Browser
acceptance includes a real quiz and assessment; it does not skip model work.

The final benchmark records zero synthetic leased-evidence leakage, restored
recall@5 of 1.0, zero exact-cache false-positive/false-negative rates, and zero
offset mapping error. These are generated-fixture results, not general claims.
The dense/batched comparison uses relative tolerance `1e-6` and absolute
tolerance `1e-7` and excludes timing rows. Scratch-memory bounding is verified
by the implementation and dense-reference regression, not a measured peak
process-memory trace.

Across five short trials per condition, mean first-token latency was 6,993 ms
after an explicit unload, 248 ms with fixed warm residency, and 243 ms after
controller pause preload. The two preload conditions separately spent about
5,830 ms preparing the model before the question. Reported sampled model
residency reached about 3,072 MiB. These measurements shift loading work before
the request; they do not establish a general end-to-end speedup or a hard RAM
bound. All final executed checks completed without a failing acceptance check.

## Evidence and reproduction

Local raw results are excluded by the existing `benchmarks/results/` gitignore
rule. They are retained on the audit machine; this report is the tracked
summary. No user database or Chrome profile was used as a test fixture.

- Final Python log: `benchmarks/results/patent-audit-20261002/python-tests-final.log`.
- Final live scoped feature report: `benchmarks/results/patent-audit-20261002/live_features-final.json`.
- General live model report: `benchmarks/results/patent-audit-20261001/live_models.json`.
- Complete browser report and screenshots: `benchmarks/results/patent-audit-20261002/browser/`.
- Focused frame timing samples: `benchmarks/results/patent-audit-20261001/video-timing-samples/report.json`.
- Initial dense benchmark: `benchmarks/results/20261001T165137Z/`.
- Final batched benchmark and local residency traces: `benchmarks/results/20261001T194718Z/`.
- Dense/batched comparison: `benchmarks/results/patent-audit-20261002/benchmark-verification.json`.

Failed runs remain visible. The initial complete browser run timed out waiting
for two observed captions. Focused runs isolated the interval-fragmentation
defect and supplied native frame timing evidence. The first live scoped
restart run and its diagnostic repeat failed because the new test injected an
embedder and skipped production digest resolution, creating a different model
version. The corrected test follows production startup and passes; neither
the assertion nor the evidence requirement was removed. Those reports are
`live_features-first-failed.json` and `live_features-diagnostic.json` in the
October 2 audit directory. An interrupted October 1 `browser-final` run has
logs but no completion report and is not counted as a pass.

From the repository root, with Python/frontend dependencies and the local
Ollama models installed:

```powershell
python -m unittest discover -s tests -v
node --test tests/*.test.cjs
python -m compileall -q backend ml benchmarks scripts tests
python scripts/check_patent_features.py --output benchmarks/results/patent-live/live_features.json
$env:CHAI_LIVE_CHECK_OUTPUT = 'benchmarks/results/patent-live/live_models.json'
python scripts/check_live_models.py
$env:CHAI_BROWSER_CHECK_OUTPUT = 'benchmarks/results/patent-live/browser'
python scripts/check_browser.py
$env:CHAI_VIDEO_CHECK_OUTPUT = 'benchmarks/results/patent-live/video'
python scripts/check_video_observation.py
$env:OPENBLAS_NUM_THREADS = '1'
python -m benchmarks.run_all --seed 0 --repeats 5 --real-ollama
git diff --check
```

From `frontend/`: `npm run lint -- --max-warnings 0`, `npx tsc --noEmit`, and
`npm run build`. Run the model/browser checks and benchmark sequentially to
avoid resource contention. The real residency benchmark explicitly unloads
and preloads local models between its declared trial conditions.

## Boundaries that must remain in the technical disclosure

- Observation is client-reported evidence of visible playback, with timing
  checks. It is not cryptographic proof that a human watched or understood the
  content. Full captions and their sealed embeddings may be persisted locally
  before observation; gating restricts searchable evidence.
- This is a local application. Learner/video keys scope F1 evidence, but they
  are not authenticated user identities. Global learning analytics and local
  settings are not a demonstrated multi-user authorization boundary.
- Default macro coverage is 100%. Lowering `F1_COVERAGE_THRESHOLD` weakens the
  claim that every word in an eligible macro was observed.
- D uses conservative exact lexical matching and full cue coverage. Repeated
  wording, paraphrases, translations, or incomplete cue matches are not proof
  of semantic equivalence. Transfer cannot chain through transferred coverage
  or cross learner keys in the tested implementation.
- C uses a global playback state and sampled Ollama model sizes, dwell, and
  cooldown. These are policy controls, not a hard process-memory cap or a
  tested priority policy for competing tabs. Short pause trials do not model
  a complete viewing session.
- Quiz validation checks schema, citations, source quotes, and answer format.
  Those checks do not prove every model-generated statement is semantically
  correct. Invalid generations can fail closed after bounded repair attempts.
- The durable jobs and locks are designed for one backend process. Distributed
  workers and an arbitrary number of concurrent clients were not validated;
  an already running model request cannot necessarily be preempted.
- Synthetic exact-vector metrics do not establish general product performance
  or HNSW agreement. Broad crash matrices, browser/platform combinations,
  adversarial security testing, and real-world transcript corpora remain
  outside this audit's coverage.

The executed checks can demonstrate that specific invariants hold and that
reproduced defects are corrected. They cannot justify an unqualified “perfect”
or “zero possible errors” statement for a patent submission.

### Later browser timing correction

The subsequent [demo-readiness audit](../docs/DEMO_READINESS_2026-10-02.md)
supersedes the frame-clock choice recorded in the observation row above.
A real 10 fps VP9 trace showed submitted-frame timestamps jumping ahead of the
caption playback clock and leaving continuously played cues sealed. The adapter
now witnesses `video.currentTime` on advancing rendered-frame callbacks against
the callback clock. Duplicate frames, hidden playback, seeks, implausible jumps,
and long callback stalls still break traversal. Full caption coverage remains
required; no coverage threshold was relaxed to make the browser check pass.
