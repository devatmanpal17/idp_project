// Compile the actual provider and React DOM with controlled Firebase SDK doubles.
// No Firebase network calls or real account data are used by this harness.
const { createRequire } = require("node:module");
const path = require("node:path");
const fs = require("node:fs");
const root = path.resolve(__dirname, "../..");
const frontend = path.join(root, "frontend");
const requireFrontend = createRequire(path.join(frontend, "package.json"));
const esbuild = requireFrontend("esbuild");
const output = process.argv[2];
const provider =
  process.argv[3] ||
  path.join(frontend, "src/components/auth/AuthProvider.tsx");
const sdk = `
const state = window.authSDK = {
  listeners: new Set(), reads: [], writes: [], updates: [], persistence: [], popups: 0,
  flags: window.authFlags || {}, currentUser: null,
  emit(user) { this.currentUser = user; for (const listener of this.listeners) listener(user); },
  user(uid) { return { uid, displayName: uid+' Google', email: uid+'@example.test', photoURL:null, metadata:{} }; },
  read(index, data) { this.reads[index].resolve({ exists:()=>data!==null, data:()=>data }); },
};
export const browserLocalPersistence = 'local';
export const inMemoryPersistence = 'memory';
export class GoogleAuthProvider { setCustomParameters() {} }
export function setPersistence(_, mode) {
  state.persistence.push(mode);
  if (state.flags.blockStorage && mode==='local') return Promise.reject(new Error('Storage blocked'));
  if (state.flags.hangPersistence) return new Promise(()=>{});
  return Promise.resolve();
}
export const getRedirectResult = () => Promise.resolve(null);
export function onAuthStateChanged(_, listener) {
  state.listeners.add(listener); if(!state.flags.hangAuthState) queueMicrotask(()=>state.listeners.has(listener) && listener(state.currentUser));
  return ()=>state.listeners.delete(listener);
}
export function signInWithPopup() { state.popups++; return Promise.resolve(); }
export function signInWithRedirect() { throw new Error('Unexpected redirect'); }
export function signOut() { state.emit(null); return Promise.resolve(); }
export function updateProfile(user, updates) {
  if (!state.flags.deferUpdate) return Promise.resolve();
  return new Promise((resolve,reject)=>state.updates.push({uid:user.uid,updates,resolve,reject}));
}
export const doc = (_, collection, uid) => ({collection,uid});
export const serverTimestamp = () => 'server-time';
export const getDoc = ref => new Promise((resolve,reject)=>state.reads.push({uid:ref.uid,resolve,reject}));
export const setDoc = (ref,data) => new Promise((resolve,reject)=>state.writes.push({uid:ref.uid,data,resolve,reject}));
export const isFirebaseConfigured = true;
export function getFirebaseServices() {
  if(state.flags.badConfig) throw new Error('Firebase: invalid configuration');
  return {auth:state,db:{}};
}
`;
const fakeConfigSDK = `
const state = window.configSDK = { apps: [{ name:'other-project' }], initialized: 0 };
export const getApps = () => state.apps;
export function getApp() { throw new Error('No default app'); }
export function initializeApp(config) { state.initialized++; const app={name:'[DEFAULT]',options:config};state.apps.push(app);return app; }
export const getAuth = app => ({app});
export const getFirestore = app => ({app});
`;
async function build() {
  fs.mkdirSync(output, { recursive: true });
  await esbuild.build({
    stdin: {
      contents: `
      import React from 'react';
      import {createRoot} from 'react-dom/client';
      import {AuthProvider,useAuth} from ${JSON.stringify(provider)};
      function Probe() {
        const auth = useAuth(); window.authView = auth;
        return React.createElement('pre', {id:'state'}, JSON.stringify({uid:auth.user?.uid,profile:auth.profile,loading:auth.loading,configured:auth.configured,error:auth.error}));
      }
      const root = createRoot(document.getElementById('root'));
      window.unmountAuth = () => root.unmount();
      root.render(React.createElement(AuthProvider,null,React.createElement(Probe)));
    `,
      resolveDir: frontend,
      loader: "tsx",
    },
    bundle: true,
    outfile: path.join(output, "auth.js"),
    format: "iife",
    jsx: "automatic",
    nodePaths: [path.join(frontend, "node_modules")],
    define: { "process.env.NODE_ENV": '"production"' },
    plugins: [
      {
        name: "controlled-firebase",
        setup(build) {
          build.onResolve(
            { filter: /^(firebase\/(auth|firestore)|@\/lib\/firebase)$/ },
            () => ({ path: "sdk", namespace: "fake" }),
          );
          build.onLoad({ filter: /.*/, namespace: "fake" }, () => ({
            contents: sdk,
            loader: "js",
          }));
        },
      },
    ],
  });
  for (const missing of [false, true]) {
    await esbuild.build({
      stdin: {
        contents: `import {isFirebaseConfigured,getFirebaseServices} from './src/lib/firebase'; window.configResult={configured:isFirebaseConfigured}; if(isFirebaseConfigured) {const services=getFirebaseServices(); window.configResult.appName=services.app.name;window.configResult.reused=services===getFirebaseServices();}`,
        resolveDir: frontend,
      },
      bundle: true,
      outfile: path.join(output, missing ? "config-missing.js" : "config.js"),
      format: "iife",
      define: {
        "import.meta.env": JSON.stringify({
          VITE_FIREBASE_API_KEY: "fake-key",
          VITE_FIREBASE_AUTH_DOMAIN: "fake.example.test",
          VITE_FIREBASE_PROJECT_ID: "fake",
          ...(!missing ? { VITE_FIREBASE_APP_ID: "fake-id" } : {}),
        }),
      },
      plugins: [
        {
          name: "config-sdk",
          setup(build) {
            build.onResolve({ filter: /^firebase\// }, () => ({
              path: "config",
              namespace: "fake",
            }));
            build.onLoad({ filter: /.*/, namespace: "fake" }, () => ({
              contents: fakeConfigSDK,
              loader: "js",
            }));
          },
        },
      ],
    });
  }
  for (const name of ["auth", "config", "config-missing"]) {
    fs.writeFileSync(
      path.join(output, name + ".html"),
      `<!doctype html><div id="root"></div><script src="${name}.js"></script>`,
    );
  }
}
build().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
