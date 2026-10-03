# Render and localhost verification — 2026-10-03

The Render configuration is opt-in: a Linux Docker service with an nginx password
gate, a Node SSR dashboard, one FastAPI worker, CPU Ollama, and persistent SQL,
Chroma, and model storage. Its separate frontend output and runtime paths preserve
the existing localhost workflow. See [deployment instructions](RENDER_DEPLOYMENT.md).

## Completed checks

| Check | Result |
| --- | --- |
| Python backend, ML, contracts and deployment configuration | 137 passed |
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

## Linux container check

The **Render container** GitHub workflow successfully built the actual Linux Docker
image and ran `scripts/check_render_container.py`. It verified the production bcrypt gate,
SSR pages/assets, installable extension download, API validation, private Ollama,
disk contents across restart, and clean shutdown. The final code run,
[97fd540](https://github.com/devatmanpal17/idp_project/actions/runs/37096686198),
completed successfully. Earlier runs for the base deployment and cache protection
also passed. Final startup waits for Ollama transport before the API resumes saved
jobs. This report's subsequent documentation commit does not change tested code.

## Remaining hosted verification

No Render resources have been provisioned. The Linux smoke test deliberately skips
model downloads; real quiz/model checks above use local Ollama. Actual Render CPU
latency, initial model download, the final HTTPS hostname, Firebase authorized-domain
setup, and real Google sign-in/profile persistence must be checked after deployment.
The included service is a trusted single-user/shared demo: Firebase profiles do not
isolate the global learning database. Automatic Render deployment is disabled.

Raw artifacts are ignored under `benchmarks/results/render-20261003/`; auth and
failure-injection scripts retain their existing ignored result directories. A passing
test suite establishes these tested behaviors and does not guarantee every future
deployment or input is error-free.
