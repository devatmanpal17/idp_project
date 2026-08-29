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

## 3. Restart the dashboard

Stop and restart Vite after changing environment variables:

```powershell
npm run dev
```

Open `/profile` or use the account button in the dashboard header, then choose **Continue with Google**.
