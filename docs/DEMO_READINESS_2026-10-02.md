# Demo readiness audit - 2026-10-02

This audit follows commit `c923494` on `patent/features-a-e`. It targets failures
that could interrupt a local showcase, with disposable databases, a fresh Chrome
profile, and the installed Ollama models.

## Bugs fixed

| Trigger | Previous behavior | Current behavior |
|---|---|---|
| Corrupted saved chat, including null entries and non-string message/source values | React could crash the entire dashboard. | Invalid entries are discarded, valid messages retained, and history bounded to 30 messages. |
| Blocked or full browser storage | Chat persistence, reset, or theme changes could crash. | Chat/reset/theme continue in memory when persistence is unavailable. |
| Stop response or a slow assistant request | Cancellation was rewritten as an offline error; timeouts looked like user cancellation. | Cancellation is preserved and Stop/timeout have distinct messages. |
| Hung API or wrong backend returning HTML | Requests could wait indefinitely or silently accept an empty object. | Read requests time out after 15 seconds; writes after five minutes. Invalid JSON produces a clear error. Chat retains its shorter 60-second deadline. |
| Incomplete successful quiz/assessment/assistant responses | Invalid quiz data could enter React state and crash rendering. | Runtime contracts reject malformed payloads before they enter state and show a recoverable error. |
| Pydantic validation errors | Only the HTTP status was displayed. | The affected field and validation message are shown without echoing rejected content. |
| A topic/quiz removed while Practice remains open | A copied selected quiz and one-time topic list remained stale. | Selection is derived from current query data; indexed topics refresh and are invalidated after capture/deletion. |
| No indexed lesson evidence | The generator could submit an empty or telemetry-only topic and fail. | Generation/retake require an indexed topic; the empty screen explains how to capture evidence. |
| Close generator or change topic during generation | The browser request continued; old quiz state could survive regeneration. | The request is aborted, each topic has separate component state, and old results are cleared. |
| Backend reachable but Ollama/model unavailable | Header incorrectly said the engine was offline; assistant always advertised Online. | Header distinguishes AI setup from backend connectivity; assistant avoids claiming live readiness. |
| Only a non-default model tag installed | Health checks could report the uninstalled default tag as ready. | Chat and embedding checks compare canonical exact tags, including registry names with ports. |
| One-click startup | Wrong pip interpreter, inaccurate Node minimum, ignored installer failures, unchecked ports/models, and success before readiness. | Active-interpreter pip, locked npm install, Node 22.12+, fixed-port checks, exact model preflight, local Ollama startup, readiness checks, logs, and owned-process cleanup. |
| Pulling dependency fixes with old node_modules present | The launcher could reuse a stale dependency tree. | Installed package versions and root dependency declarations must match the repository lockfile; mismatches trigger npm ci. |
| Production preview on Windows | Nitro failed with spawn npx ENOENT. | npm run preview uses the explicitly installed, locked Wrangler CLI in local mode. |
| Vulnerable dependency versions | npm audit reported known dependency vulnerabilities. | Nitro and affected transitive packages are updated; Firestore's gRPC dependency is pinned to a patched 1.x version. The final full npm audit reports zero known vulnerabilities. |

The launcher serves the development frontend, so it no longer performs an unused
production build on every launch. Missing dependencies are installed; already
installed dependencies are reused. `--install` forces dependency installation.

## Verification

- Python: **129 passed**, including all prior patent/notebook tests and 20 new
  startup/model-readiness regressions; actual temporary SQLite and Chroma stores,
  with controlled model responses in the automated suite.
- Extension: **12 Node tests passed**.
- Failure injection: **14 Chrome checks passed**. These use a mocked API and real
  React rendering in an isolated browser. They cover corrupt/blocked/full storage,
  preserving valid history, cancellation, timeout, invalid JSON, validation
  messages, invalid AI payloads, empty evidence, generator cancellation, and
  deleting the selected quiz/topic during polling.
- Complete real Chrome acceptance: **28 checks and 25 desktop/mobile layout
  checks passed**, with zero runtime exceptions, API errors, broken images, or
  document-level horizontal overflow. This includes live dashboard chat, real
  quiz generation/scoring, notebook reveal/scheduling/reload, all dashboard
  routes, settings save, theme/navigation, calendar export, source deletion,
  actual MV3 extension requests, and real video seek gating. Both contact sheets
  were visually reviewed.
- TypeScript, ESLint with zero errors/warnings, fresh `npm ci`, production client/server build,
  Python compilation, and `git diff --check`: passed. Build output includes
  bundle-size and module-directive advisories; neither fails the build.
- Cold launcher smoke test: started its own Ollama, waited for both servers and
  AI readiness, then stopped its own processes. The batch wrapper's read-only
  preflight also passed against the installed models.
  A real preflight with an uninstalled chat-model tag returned failure and the
  specific `ollama pull` command before launching backend/frontend services.
- Real Ollama: **nine patent acceptance checks and five general checks passed**:
  observed-only retrieval, micro/macro gates, transfer reuse, answer-cache reuse,
  lease hiding/restart/restoration, durable quiz delivery, revision revocation,
  embeddings, retrieval, grounded answers, summaries, and grounded quizzes.

Raw results are intentionally ignored by Git under
`benchmarks/results/demo-readiness-20261002/`. `failure_checks_before.json`
records the initial eight failing scenarios; `failure_checks.json` records the
expanded suite after fixes. Python/build logs and live JSON reports are there.
Launcher logs are under `logs/startup-*.log`.

## Follow-up website check after the first push

Commit `46c1a6e` was pushed and its hash verified on GitHub. A second complete
website run again passed all 28 real Chrome checks and 25 layout checks. The
expanded audit then reproduced the Windows production-preview failure above.

The correction locks Wrangler 4.147.0 and Nitro 3.0.260903-beta, refreshes the
affected dependency graph, and overrides Firestore's gRPC client to 1.13.6.
The version choices were checked against the
[Nitro release notes](https://github.com/nitrojs/nitro/releases/tag/v3.0.260903-beta),
[maintainer gRPC advisory](https://github.com/grpc/grpc-node/security/advisories/GHSA-m9gg-hp2v-232j),
and [Wrangler local command documentation](https://developers.cloudflare.com/workers/wrangler/commands/workers/).
Firebase remains on its existing major version. The gRPC override should be
revisited when Firestore updates its own dependency range.

Retesting caught a development-only mismatch: the new Nitro dev runner selected
the Miniflare 5 installed by Wrangler, while its current adapter expects the
Miniflare 4 API. Vite's local runner is now explicitly `node-worker`; the built
Cloudflare worker is tested using Wrangler. This preserves the local Node/FastAPI
development workflow and exercises the production worker separately.

The built-site acceptance passed **six workflow checks and 24 layout checks**:
preview startup, real three-question quiz scoring/graphs, notebook review/reload,
12 routes in each viewport with direct HTTP requests and client hydration, and
the 404 screen. Runtime exceptions, API failures, broken images, and horizontal
document overflow were all zero. The production checks use actual built assets
and a local workerd runtime, temporary stores, and a new Chrome profile.
The refreshed dependency tree passed a clean npm ci, zero-vulnerability audit,
TypeScript, ESLint, production build, the 129 Python/12 extension tests, and all
14 failure-injection checks.
The final complete development run again passed all 28 checks and 25 layouts,
and the final rebuilt production preview repeated all six checks and 24 layouts
without runtime/API errors. Both production contact sheets were visually reviewed.
The batch launcher's final prerequisite and startup/shutdown smoke checks passed
with the refreshed dependency graph.

The additional evidence is under `post-push/` (first follow-up and refreshed
Python/build logs), `production/` (built-site checks and contact sheets), and
`final/browser/` (final complete development-site rerun).

## Follow-up account, configuration, and playback audit

The later review found account and startup paths outside the earlier live
coverage. Delayed profile reads/saves could replace the current account's
profile after sign-out or an account switch. Firestore requests could also keep
the profile form busy indefinitely. Account generations now invalidate stale
results, and the form resets per user. Auth initialization, persistence setup,
profile reads, and writes have 15-second UI deadlines. Failed reads retain the
Google identity but disable saving until the saved fields can be loaded; empty
fallback values cannot overwrite an existing document. Login metadata writes
are separate from editable fields and do not block the form. A new document is
created on the first explicit save with all fields required by `firestore.rules`.

Google sign-in uses a popup in both viewports, following Firebase's
[popup alternative](https://firebase.google.com/docs/auth/web/redirect-best-practices#option_2_switch_to_signinwithpopup).
Blocked durable storage falls back to
[in-memory persistence](https://firebase.google.com/docs/auth/web/auth-state-persistence).
Invalid SDK configuration becomes a visible setup error. Authentication no longer
requires unused storage/messaging configuration, and initialization handles an
existing named app without assuming a default app already exists. The launcher
opens `localhost` consistently instead of changing browser origins on a sign-in
click. The [setup guide](../frontend/FIREBASE_SETUP.md) covers hosted API/Firebase
configuration; a hosted worker needs a separately reachable FastAPI backend.

Malformed model registries, corrupt lockfile shapes, unreadable/non-UTF-8 root
environment files, and a missing npm executable now give actionable startup
results. The backend reads UTF-8/BOM environment files consistently and trims
spaces/empty entries from its CORS origin list. Real OPTIONS requests verified
both configured local origins, including an origin following a comma and space.

The first full browser attempt was interrupted by an AuthProvider development
reload while generating a quiz. The subsequent frozen-code run exposed a separate
playback defect: in a 10 fps VP9 trace, frame `mediaTime` jumped from 0.7 to 1.0
seconds while `currentTime` advanced from about 0.762 to 0.869. This broke continuous
observation spans and left played captions sealed. The
[frame callback specification](https://wicg.github.io/video-rvfc/) distinguishes
the submitted frame's presentation timestamp from callback/display clocks.
The adapter now samples caption playback time only at callbacks with an advancing
`presentedFrames` counter, against the callback clock. Duplicate frames, seeks,
hidden playback, rate changes, implausible jumps, and long callback stalls still
break traversal. Full coverage remains required; no threshold was relaxed.

Final verification after those fixes:

- **133 Python tests**, **13 extension tests**, TypeScript, ESLint with zero
  warnings, production build, compile checks, and zero known npm vulnerabilities.
- **20 account checks** using the actual provider and React DOM in Chrome with
  controlled Firebase SDK doubles. These cover out-of-order accounts, sign-out,
  read/write/persistence/auth-initialization stalls, permission failures, first
  document creation, saves during account changes, blocked storage, invalid
  configuration, and unmount cleanup. They do not perform a real Google login.
- A standalone decoded-video test covers both watched caption spans and rejects
  the seek gap. The subsequent complete development run passed **29 workflows
  and 25 layouts**, including actual extension playback/promotion with the skipped
  caption still sealed. Runtime/API errors, broken images, and document overflow
  were zero; desktop/mobile contact sheets were visually reviewed.
- The **nine real Ollama patent checks** were repeated successfully: F1/E
  observed-only promotion, D transfer/revision revocation, B cache reuse, A lease
  hiding/restoration/restart, and durable quiz/answer holds. The final launcher's
  read-only prerequisite check and cold startup/shutdown smoke test also passed.

Evidence is under `auth/`, `observation/`, and `auth-followup/` in the ignored audit
results directory. `auth-followup/browser/` records the interrupted run;
`auth-followup/final-browser/` records the playback failure;
`auth-followup/repaired-browser/` records the final passing run. The earlier
provider reproduction is under `auth-before/`. Browser checks use disposable
stores/profiles. Optional browser-test Python versions are recorded in
`tests/browser-requirements.txt`.

## Reproduce

```powershell
# From the repository root, with Ollama and both required models available:
.\start_all.bat --check
.\start_all.bat --smoke-test
python -m pip install -r tests/browser-requirements.txt
python scripts/check_auth_browser.py
python scripts/check_observation_browser.py
python scripts/check_demo_failures.py
python scripts/check_patent_features.py --output benchmarks/results/demo-readiness-20261002/live_features.json
$env:CHAI_LIVE_CHECK_OUTPUT = 'benchmarks/results/demo-readiness-20261002/live_models.json'
python scripts/check_live_models.py
$env:CHAI_BROWSER_CHECK_OUTPUT = 'benchmarks/results/demo-readiness-20261002/browser'
python scripts/check_browser.py
# After npm run build, with ports 8000/8080 free:
python scripts/check_production_browser.py
```

Run live model/browser scripts sequentially. Set disposable `DATABASE_URL` and
`CHROMA_PERSIST_DIR` before `python -m unittest discover -s tests -v`. From
`frontend/`, run `npx tsc --noEmit`, `npm run lint -- --max-warnings 0`, and
`npm run build`. Normal showcase startup is `.\start_all.bat`.

## Tested boundaries

Browser storage may not persist when blocked/full. Cancelling or timing out a
browser request does not guarantee cancellation of inference already running on
the server; refresh before repeating a timed-out write. Model generation remains
variable and can fail grounding/English validation despite a ready health check.
The launcher checks initial readiness, not guaranteed future model output.

These results cover this Windows/local/Chrome setup. Hosted deployment, PostgreSQL,
Google sign-in, Edge, and multiple backend worker processes were not exercised.
The existing local single-instance/global-learning-data limits still apply.
Feature C's residency behavior remains covered by the existing automated suite;
its earlier real unload/budget benchmark was not repeated in this audit.
Passing these checks does not establish patentability or prove absence of every
possible defect.
