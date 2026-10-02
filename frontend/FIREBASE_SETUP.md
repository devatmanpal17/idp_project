# Firebase Google login setup

The dashboard uses Firebase Authentication for Google sign-in and Cloud Firestore for each user's private profile document.

## 1. Create the Firebase web app

1. Open the [Firebase console](https://console.firebase.google.com/), create or select a project, then add a Web app.
2. In **Authentication → Sign-in method**, enable **Google** and select a support email.
3. In **Authentication → Settings → Authorized domains**, add the production dashboard domain. `localhost` should also be present for local development.
4. Create a Cloud Firestore database.
5. In the Firestore **Rules** tab, publish the contents of `firestore.rules` from this folder.

## 2. Configure only your local environment

Create `frontend/.env.local` and paste the public web-app values shown under **Project settings → Your apps → SDK setup and configuration**:

```dotenv
VITE_FIREBASE_API_KEY=your_api_key
VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-project-id
VITE_FIREBASE_STORAGE_BUCKET=your-project.firebasestorage.app
VITE_FIREBASE_MESSAGING_SENDER_ID=your_sender_id
VITE_FIREBASE_APP_ID=your_app_id
```

The repository ignores `.env.local`, so this configuration is not committed. Firebase web configuration identifies the Firebase project; authorization is enforced by Authentication and the included Firestore security rules.

`API_KEY`, `AUTH_DOMAIN`, `PROJECT_ID`, and `APP_ID` are required. Storage bucket
and messaging sender ID are optional for the authentication/profile features.

## 3. Restart the dashboard

Stop and restart Vite after changing environment variables:

```powershell
npm run dev
```

Open `/profile` or use the account button in the dashboard header, then choose **Continue with Google**.

Use `http://localhost:8080` consistently for local sign-in. Sessions and local
dashboard preferences belong to their browser origin, so switching between
`localhost` and `127.0.0.1` uses separate storage. The launcher opens `localhost`.

Sign-in uses a popup on desktop and mobile. Allow the popup for the dashboard.
This follows Firebase's [popup alternative](https://firebase.google.com/docs/auth/web/redirect-best-practices#option_2_switch_to_signinwithpopup)
when the app and Firebase auth helper are hosted on different domains.
If durable browser storage is blocked, the app falls back to Firebase's
[in-memory persistence](https://firebase.google.com/docs/auth/web/auth-state-persistence);
that session ends on reload.

Saved-profile reads and writes have a 15-second UI deadline. Read failures show
the Google identity and an error; saving remains disabled until the saved fields
can be loaded, so fallback blanks cannot replace an existing profile. Reload to
retry. Login metadata writes do not block the form. A timed-out write can still
sync later through Firebase; reload before retrying a save. Account changes and
unmounts invalidate pending profile results.

## Hosted dashboard configuration

Set Firebase values in the frontend build environment, authorize the deployed
dashboard domain, and publish `firestore.rules` to the same project. Rebuild
after changing `VITE_*` values; they are embedded in the client bundle.

The built Cloudflare worker serves the dashboard. FastAPI, Ollama, and persistent
learning stores still run separately. Set `VITE_API_BASE_URL` to the reachable
HTTPS backend API (including `/api`) before building, and include the exact
dashboard origin in the backend's `CORS_ORIGINS`. Vite's local `/api` proxy does
not apply to the deployed worker. Verify `/api/health` and Google sign-in from
the hosted dashboard before a hosted showcase.

The local audit tests account transitions and failures with SDK doubles. It does
not verify a real Google account, Firebase project's console settings/rules, or
a public deployment.
