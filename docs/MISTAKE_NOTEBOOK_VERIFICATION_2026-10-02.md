# Mistake Notebook and app verification - 2026-10-02

The new `/mistakes` dashboard turns a missed assessment question into a persistent
review card. The app previously displayed quiz history and topic schedules;
it did not persist a review schedule for each missed question. The notebook
connects assessment feedback to a repeatable recall workflow without extra model
inference or changing the patent observation/transfer algorithms.

These results cover the changes after commit `ce4a554` on
`patent/features-a-e`, including the fixes from the preceding
[interaction audit](../patent/06_DEEP_FEATURE_INTERACTION_AUDIT_2026-10-02.md).

## Behavior

- Only complete missed-question feedback creates a card. Correct answers and
  older partial telemetry do not create unusable cards. Each card is identified
  by its assessment attempt and question position.
- The assessment and its new cards commit atomically. Initialization backfills
  complete old mistakes once without overwriting review progress.
- Feedback is concealed in the interface until Reveal feedback. The expected
  answer, original answer, explanation, Bloom level, and source-reference count
  come from the saved assessment; they are not new model output.
- Again schedules 10 minutes later and resets the streak. Remembered uses
  intervals of 1, 3, 7, 14, then 30 days from review time. Subsequent remembered
  reviews remain capped at 30 days. This is a scheduling heuristic, not a claim
  of scientifically optimal retention.
- Due now and All cards include counts, pagination, refresh, loading/error/empty
  states, and desktop/mobile layouts. Review progress survives reload and restart.
- Review writes require the current version, so a repeated stale write cannot
  silently schedule the same card twice. The UI refreshes after conflicts.
- Self-review does not change assessment mastery, recall-model training data,
  query embeddings, or model residency.
- The server checks open evidence holds under the RAG lock. A held card omits
  its question, answers, and explanation entirely and rejects review with 409.
  It becomes readable after the relevant holds close.
- Deleting a topic's last indexed source removes its assessments and cards.
  If other sources for that topic remain, the existing topic deletion policy
  preserves its assessment history and cards.

## Verification

| Check | Result | What was exercised |
|---|---|---|
| Complete Python suite | 109 passed, 0 failures | Existing 101 tests plus eight notebook storage/API tests. Actual temporary SQLite/Chroma, controlled model responses, and patent feature interleavings. |
| Extension Node tests | 12 passed, 0 failures | All four behavior test files: capture, timing, request retry, source changes, learner identity, and concurrent sequence persistence. |
| TypeScript | Passed | `npx tsc --noEmit`, including the generated `/mistakes` route types. |
| ESLint | Passed, 0 errors and 0 warnings | `npm run lint -- --max-warnings 0`. |
| Production build | Passed | Client and server bundles, including the notebook route. Existing bundle-size/Nitro advisories are not build failures. |
| Complete Chrome acceptance | 27 passed; 25 layout checks passed | Actual quiz scoring, notebook reveal/scheduling/reload, all dashboard routes, settings, export, history deletion, extension article requests, and real seek playback. |
| Scoped live Ollama acceptance | 9 passed | Observation gating, micro/macro eligibility, vector reuse/transfer, exact answer cache, lease hiding/restart/restore, durable quiz delivery, and revision revocation. |
| General live Ollama smoke | 5 passed | Real embedding, retrieval, answer, summary, and grounded three-question quiz. |
| Extension syntax / Python compilation / whitespace integrity | Passed | Extension scripts, `compileall`, and `git diff --check`. |

Chrome captured no runtime exceptions or API errors. The live quiz was not
skipped. Desktop and mobile contact sheets were visually reviewed, and all 25
layout checks had zero broken images and no document-level horizontal overflow.
The live checks use the installed `embeddinggemma` and `llama3.2:3b` models.
Their reports record per-check results and timings; the scoped report also
records the resolved embedding-model digest.

The eight new tests cover correct/missed/partial questions, idempotent capture,
SQL rollback on capture failure, version conflicts, interval growth/cap/reset,
due filtering, pagination, restart, migration preservation, input validation,
unchanged mastery, evidence hold/restoration, and source/history deletion.

The Chrome fixture uses a real generated three-question quiz. It reads answer
positions only from its own disposable test database to choose one wrong and
two correct answers through the real UI. That makes the notebook fixture
deterministic without replacing generation or scoring. It verifies answer
concealment, reveal, Again, persistence after reload, Remembered, and future
scheduling. Browser acceptance also exercises the extension and the remaining
dashboard routes.

## Reproduce

From the repository root:

```powershell
# Use disposable DATABASE_URL and CHROMA_PERSIST_DIR for unit tests.
python -m unittest discover -s tests -v
node --test tests/*.test.cjs
python -m compileall -q backend ml tests scripts
git diff --check

# With Ollama running and embeddinggemma / llama3.2:3b installed:
python scripts/check_patent_features.py --output benchmarks/results/mistake-notebook-20261002/live_features.json
$env:CHAI_LIVE_CHECK_OUTPUT = 'benchmarks/results/mistake-notebook-20261002/live_models.json'
python scripts/check_live_models.py
$env:CHAI_BROWSER_CHECK_OUTPUT = 'benchmarks/results/mistake-notebook-20261002/browser'
python scripts/check_browser.py
```

From `frontend/`: `npx tsc --noEmit`,
`npm run lint -- --max-warnings 0`, and `npm run build`.
Run live model/browser scripts sequentially; they create disposable stores and
the browser uses its own Chrome profile. Raw evidence is intentionally ignored
by Git under `benchmarks/results/mistake-notebook-20261002/`.
The full Python output is `python-tests.log`; browser results and visual evidence
are in `browser/browser_checks.json`, `browser/ui_desktop.png`, and
`browser/ui_mobile.png`.
Live model evidence is in `live_features.json` and `live_models.json`.

## Limits

The notebook retains historical quiz feedback, which can itself contain model
mistakes. Its self-ratings are not a new assessment or proof of mastery. One
question missed in different assessments creates separate assessment cards.
Cards reveal historical feedback rather than fetching a new source revision.

The evidence guard covers the card's cited IDs held by the lease policy; it
does not establish universal semantic blocking of equivalent information.
Already delivered content cannot be revoked from a client's memory. The existing
local, unauthenticated, single-process model and global learning-data scope
still apply. Firebase/Google login, production deployment, PostgreSQL, Edge,
other browser/platform combinations, and exhaustive crash/concurrency matrices
were not validated in this run. These results do not certify zero undiscovered
bugs or patentability.
