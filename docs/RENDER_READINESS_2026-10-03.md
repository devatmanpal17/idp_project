# Render and localhost verification — 2026-10-03

The Render configuration is opt-in: a Linux Docker service with an nginx password
gate, a Node SSR dashboard, one FastAPI worker, CPU Ollama, and persistent SQL,
Chroma, and model storage. Its separate frontend output and runtime paths preserve
the existing localhost workflow. See [deployment instructions](RENDER_DEPLOYMENT.md).

## Completed checks

| Check | Result |
| --- | --- |
| Python backend, ML, contracts and deployment configuration | 151 passed |
| Extension unit checks, including actual worker password routing | 15 passed |
| Actual React auth provider with Firebase SDK doubles in Chrome | 20 passed |
| Chrome storage, API failure, cancellation and recovery checks | 14 passed |
| `start_local.py --smoke-test --no-browser` | Passed; backend, models and Vite ready |
| TypeScript and ESLint with zero allowed warnings | Passed |
| Default Cloudflare production build | Passed |
| Separate Render Node production build | Passed |
| Default Wrangler production preview with real Ollama and Chrome | 6 workflows, 24 layouts passed |
| Render Node output outside source/node_modules, behind actual Windows nginx | 7 workflows, 24 layouts passed |
| Final gateway password boundary, private caching, extension ZIP | Passed |
| Read-only setup API behind the real gateway | Dashboard routes/gate passed; learning requests return retryable 503 without opening SQL |
| `render.yaml` against Render's current official JSON schema | Passed |
| Final Linux Docker build and deployment smoke suite | Passed in GitHub Actions |

Both browser acceptance runs generated and graded a real grounded quiz, saved and
reloaded mistake review, checked all 12 app routes at desktop and mobile sizes, and
verified not-found handling. Reports contain zero runtime/API errors, broken images,
or document overflow. Screenshots were reviewed. Databases and Chrome profiles were
disposable; owned processes were stopped. The Windows gateway check uses a temporary
SHA password hash because Windows nginx lacks system bcrypt; production uses bcrypt
on Linux. It also verifies that the protected extension ZIP contains the installable
manifest/background script and excludes environment files.
The Render production browser run was repeated after the final quiz-generation
changes: seven workflows and all 24 layouts passed with zero recorded runtime/API
errors. TypeScript, lint, extension tests and localhost startup also passed in this
audit. Auth-provider and browser failure-injection counts above are retained from
the preceding audit; those frontend implementations did not change here.

## Bugs fixed in the deeper deployment audit

- Ollama was installed under `/usr/local/bin` while its inference helper lived in
  `/usr/lib/ollama`. Its daemon and model-list checks worked, but a real Linux
  embedding request failed. The image now preserves the upstream `/usr/bin` and
  `/usr/lib/ollama` layout, includes the CPU runtime dependencies, and excludes
  unused GPU payloads from the final image.
- First boot could open the patent stores before model downloads finished,
  assigning an unresolved embedding identity. A subsequent restart could hide or
  invalidate these records. The read-only setup API keeps the dashboard/probes
  available while blocking learning writes. The persistent backend starts only
  after both model manifests exist. A separate backend guard prevents recovery
  under an unresolved identity if inventory fails during the startup handoff.
- Blank runtime settings could bypass persistent defaults; copied localhost SQLite
  URLs could write onto temporary storage. Blank settings now receive defaults,
  hosted SQLite paths must stay under `/var/data`, and incompatible remote Chroma,
  invalid resource values and Render-reserved public ports fail before launch.
- The Linux CPU quiz run exposed repeated replacements after an invalid answer.
  Quote catalogs now cover the full evidence span, and repair targets unused
  facts while preserving accepted questions. Output grammar limits answers to
  four labels and citations to active aliases. Existing validation converts labels
  to exact stored choices and still rejects unsupported citations, quotes,
  non-English output and duplicate questions. Stored/public quiz formats remain
  compatible.

## Linux container check

The **Render container** GitHub workflow successfully built the actual Linux Docker
image and ran `scripts/check_render_container.py` with a **4 CPU / 8 GB** container
limit. It verified the production bcrypt gate, SSR pages/assets, extension ZIP,
API validation, private Ollama, setup-time write blocking, default automatic model
downloads, actual CPU embeddings, nine real F1/A/B/D/E patent checks including
grounded quiz generation and answer locking, actual SQL/Chroma records and model
identity across restart, recovery after independently killing Node/Ollama/FastAPI,
and clean shutdown. The final CPU image passed the size check of **under 4 GiB
uncompressed**. Feature C's policy behavior remains covered by the automated
residency tests; this run does not benchmark real playback dwell timings.

The final code run,
[a5aedec](https://github.com/devatmanpal17/idp_project/actions/runs/37134550722),
completed successfully. The preceding run for the quiz repair change also passed.
Earlier expanded runs found the runner-layout and quiz-repair failures described
above; both were fixed and the complete Linux suite was rerun successfully.
This report's subsequent documentation commit does not change tested code.

## Remaining hosted verification

No Render resources have been provisioned. The expanded Linux test now downloads
and runs the real models in its disposable container. Actual Render CPU
latency, initial model download, the final HTTPS hostname, Firebase authorized-domain
setup, and real Google sign-in/profile persistence must be checked after deployment.
The included service is a trusted single-user/shared demo: Firebase profiles do not
isolate the global learning database. Automatic Render deployment is disabled.

Raw artifacts are ignored under `benchmarks/results/render-20261003/`; auth and
failure-injection scripts retain their existing ignored result directories. A passing
test suite establishes these tested behaviors and does not guarantee every future
deployment or input is error-free.
