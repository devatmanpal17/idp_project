# Full-stack Render deployment

The root `render.yaml` defines one Docker web service in Singapore with **4 CPU,
8 GB RAM, and a 20 GB persistent disk**. This is paid infrastructure. Review
[Render pricing](https://render.com/pricing) before creating the Blueprint.
The free 512 MB service cannot run this model stack or attach persistent storage.

It hosts the React server-rendered dashboard, FastAPI, Chroma, SQLite, and CPU
Ollama (`embeddinggemma` and `llama3.2:3b`). The browser extension still installs
in Chrome/Edge; websites cannot automatically install extensions.
The final image includes the CPU inference runner and its libraries, with the
upstream executable/library layout preserved. GPU payloads are excluded to keep
the image and build disk smaller. The Linux acceptance check tests actual
inference; an online Ollama daemon or downloaded model list alone is insufficient.

## Deploy

1. In [Render](https://dashboard.render.com/), connect GitHub repository
   `devatmanpal17/idp_project`, choose **New → Blueprint**, and select branch
   **`patent/features-a-e`**. Use **`render.yaml` at the repo root**. Do not set a
   `frontend` root directory or create a static site.
2. Enter **`CHAI_HOST_PASSWORD`**, a unique, randomly generated password of 16–72
   printable ASCII characters. It is runtime-only, excluded from the frontend
   and image. Review the paid compute and disk settings before Create/Deploy.
3. To enable Google sign-in and profile saving, provide your existing Firebase
   **web app configuration**: `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`,
   `VITE_FIREBASE_PROJECT_ID`, and `VITE_FIREBASE_APP_ID`. These are public browser
   configuration, not service-account credentials. Optional
   `VITE_FIREBASE_STORAGE_BUCKET` and `VITE_FIREBASE_MESSAGING_SENDER_ID` can be
   added in Render's Environment tab. Never add a Firebase private key.
   If Firebase is omitted, learning still works and account features show their
   existing configuration message.
4. Add the exact Render hostname to Firebase Authentication → Settings → Authorized
   domains, retaining `localhost`. Deploy the existing `frontend/firestore.rules`
   if needed; see [Firebase setup](../frontend/FIREBASE_SETUP.md).
5. Visit your Render HTTPS URL. At the browser password prompt, use username
   **`demo`** and `CHAI_HOST_PASSWORD`. All dashboard and API paths are gated.
   `/healthz` exposes only `{"status":"ok"}` for platform probes.
6. First startup downloads models onto `/var/data/ollama`. The dashboard starts
   before downloads finish. A read-only setup API reports `setup_required` and
   returns a retryable 503 for learning operations. The persistent patent store
   opens only after both model manifests are available, so its embedding identity
   stays consistent across the first restart. Wait until the engine says **ready**, or authenticated
   `/api/health` returns `"status":"ready"`, before testing AI. Logs show progress;
   temporary download failures retry automatically.
7. Download the extension ZIP from the dashboard's **Extension** screen, extract it,
   and use Chrome/Edge **Load unpacked** to select its `extension` folder.
   In extension settings set **both Backend URL and Dashboard URL** to the HTTPS
   Render origin, such as `https://your-service.onrender.com`. **Do not append
   `/api`**; the extension adds it. Enter the hosted password, click **Save and test
   connection**, and reload lesson tabs. Open the dashboard once to enter its
   browser password prompt too.

Render translates environment variables into Docker build arguments. Only public
Firebase configuration is declared in this Dockerfile; the Render build forces
`VITE_API_BASE_URL=/api`. Firebase configuration changes require a fresh deploy.
Automatic deployment is off so pushes do not interrupt showcases; use Manual
Deploy after checks pass. [Docker on Render](https://render.com/docs/docker)

## Localhost stays independent

Run `start_all.bat` as before. It needs no Render password, Docker, or production
build. Dashboard `http://localhost:8080`, API `http://localhost:8000`, Ollama
`http://localhost:11434`, local `.env`, and local learning/model storage remain
unchanged. Docker excludes local credentials, dependencies, builds, and data.

`npm run build` / `npm run preview` keep the existing Cloudflare worker workflow.
The opt-in `npm run build:render` writes `frontend/dist-render` and forces the
same-origin API without editing `.env`. Its Node entry is
`node frontend/dist-render/server/index.mjs`, run behind the production gateway.
The two build directories are independent.

To restore local extension use, set Backend URL `http://localhost:8000`, Dashboard
URL `http://localhost:8080`, and clear the hosted password. Passwords are bound to
the saved server origin and stored in `chrome.storage.local`, never Chrome sync
or the captured webpage.

## Storage and operating limits

| Data | Render path |
| --- | --- |
| History, jobs, leases, F1/A–E SQL state | `/var/data/analytics.sqlite3` |
| Searchable Chroma vectors | `/var/data/chroma` |
| Ollama models | `/var/data/ollama` |

Render starts with a separate empty database; local learning data is not uploaded.
For migration, arrange a stopped-service copy and backups rather than copying live
SQLite/Chroma files during writes. Storage survives restarts and redeploys, but
deleting the disk destroys it. Keep application-consistent SQL/Chroma backups;
Render cautions against disk snapshot restores for recovering custom databases.
[Persistent disk documentation](https://render.com/docs/disks)

This is a **single-user or trusted shared demo**, with one backend worker and one
instance. Firebase profiles do not isolate the shared learning database. Anyone
given the demo password can capture, read, quiz, change settings, and delete that
data. Public multi-user hosting first requires authenticated API users and data
isolation. Startup refuses a missing/invalid password. Ollama, Node and FastAPI
listen only on loopback behind the public gateway.
Protected pages, API responses, and downloads disable shared caching.
Blank model, memory and database settings use the Blueprint defaults. A custom
SQLite `DATABASE_URL` must stay inside `/var/data`; temporary or in-memory paths
are rejected. Remove any localhost `CHROMA_HOST` setting: this Blueprint uses
Chroma on its mounted disk. `CHAI_MODEL_AUTO_PULL=false` disables downloads and
keeps the setup API active until both models are installed manually.
If the model inventory fails between setup and backend initialization, the API
refuses recovery rather than invalidating existing patent records under an
unresolved embedding identity; the container can restart safely.

Disk services cannot scale to multiple instances and have a short redeploy outage.
CPU generation can be slower than a local GPU; increase resources if your workload
needs it. The 8 GB plan reserves 6 GB for model residency management. Test on the
actual Render URL before showcasing. `/healthz` checks process availability;
`/api/health` separately reports AI readiness.
The hosted chat allows up to five minutes for inference; localhost retains its
existing one-minute deadline.
[Render health checks](https://render.com/docs/health-checks)

## Verification

GitHub Actions **Render container** builds the Linux image and tests its real
gateway password boundary, SSR routes/assets, API validation, private Ollama,
safe first-boot setup, automatic real model downloads, CPU embedding, nine patent
acceptance checks, actual records across restart, dependency failure recovery,
and graceful shutdown. It limits the container to 4 CPU and 8 GB RAM. This does
not establish latency on Render's actual infrastructure. With a running Docker
daemon, reproduce it (downloads several GB into disposable test storage):

```powershell
docker build -t chaigaram-render:test .
python scripts/check_render_container.py --image chaigaram-render:test
```

After deploying, test Google sign-in, extension capture, watched-caption gating,
tutor, quizzes/grading, mistake review, and restart persistence on the actual HTTPS
origin. Committing these files does not create a cloud service or paid resources.
