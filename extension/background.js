importScripts('connection.js');

const DEFAULT_SETTINGS = {
  apiBaseUrl: "http://localhost:8000",
  dashboardUrl: "http://localhost:8080",
  autoCapture: true,
};

chrome.runtime.onInstalled.addListener(async () => {
  const current = await chrome.storage.sync.get(DEFAULT_SETTINGS);
  await chrome.storage.sync.set(current);
});

async function apiRequest(path, init = {}) {
  const { apiBaseUrl } = await chrome.storage.sync.get(DEFAULT_SETTINGS);
  const base = ChaiConnection.connectionURL(apiBaseUrl || DEFAULT_SETTINGS.apiBaseUrl);
  const { hostPassword } = await chrome.storage.local.get('hostPassword');
  const authHeaders = ChaiConnection.hostPasswordHeaders(base, hostPassword);
  const response = await fetch(`${base}${path}`, {
    ...init,
    signal: AbortSignal.timeout(180000),
    headers: { "Content-Type": "application/json", ...(init.headers || {}), ...authHeaders },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    if (response.status === 401) detail = 'Check the hosted demo password in extension settings.';
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {
      // Keep the HTTP status when the server does not return JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

let learnerKeyPromise;
function learnerKey() {
  if (!learnerKeyPromise) learnerKeyPromise = (async () => {
    const key = 'chaigaram-learner-key';
    const saved = (await chrome.storage.local.get(key))[key];
    if (saved) return saved;
    const created = crypto.randomUUID();
    await chrome.storage.local.set({[key]: created});
    return created;
  })();
  return learnerKeyPromise;
}

const scopeQueues = new Map();
function serialScope(payload, action) {
  const scope = `${payload.learner_key}|${payload.video_key}`;
  const previous = scopeQueues.get(scope) || Promise.resolve();
  const next = previous.catch(() => {}).then(() => action(`chaigaram-sequence:${scope}`));
  scopeQueues.set(scope, next);
  void next.finally(() => {
    if (scopeQueues.get(scope) === next) scopeQueues.delete(scope);
  }).catch(() => {});
  return next;
}

const handlers = {
  LEARNER_KEY: learnerKey,
  TRANSCRIPT: payload => apiRequest('/api/vectors/transcript', {method:'POST',body:JSON.stringify(payload)}),
  OBSERVE: payload => apiRequest('/api/observation/intervals', {method:'POST',body:JSON.stringify(payload)}),
  SPECULATE: payload => apiRequest('/api/vectors/speculate', {method:'POST',body:JSON.stringify(payload)}),
  DOCUMENT: payload => apiRequest('/api/rag/ingest', {method:'POST',body:JSON.stringify(payload)}),
  HEALTH: () => apiRequest("/api/health"),
  INGEST: (payload) => apiRequest("/api/rag/stream-transcript", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  ASK: (payload) => apiRequest("/api/rag/ask", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  SUMMARIZE: (payload) => apiRequest("/api/rag/summarize", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  QUIZ: (payload) => apiRequest("/api/rag/generate-quiz", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  EVALUATE: (payload) => apiRequest("/api/rag/evaluate-quiz", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  ABANDON: (payload) => apiRequest(`/api/rag/abandon-quiz/${encodeURIComponent(payload.quiz_id)}`, {
    method: "POST",
  }),
  PLAYER_STATE: payload => apiRequest('/api/runtime/player-state', {
    method: 'POST', body: JSON.stringify(payload),
  }),
  F1_SEAL: payload => serialScope(payload, async key => {
    const result = await apiRequest('/api/f1/seal', {method:'POST',body:JSON.stringify(payload)});
    const previous = Number((await chrome.storage.local.get(key))[key] || 0);
    await chrome.storage.local.set({[key]: Math.max(previous, Number(result.last_batch_seq || 0))});
    return result;
  }),
  F1_INTERVALS: payload => serialScope(payload, async key => {
    const previous = Number((await chrome.storage.local.get(key))[key] || 0);
    const sequence = Math.max(Date.now(), previous + 1, Number(payload.batch_seq || 0));
    // Persist before sending: retries after a lost response always consume a new sequence.
    await chrome.storage.local.set({[key]: sequence});
    return apiRequest('/api/f1/intervals', {method:'POST',
      body:JSON.stringify({...payload, batch_seq: sequence})});
  }),
  F1_STATUS: () => apiRequest('/api/f1/status'),
  TOPIC_STATE: (payload) => apiRequest(`/api/learning/topic-state?topic=${encodeURIComponent(payload.topic)}`),
  JOB_START: (payload) => apiRequest("/api/jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  JOB_STATUS: (payload) => apiRequest(`/api/jobs/${encodeURIComponent(payload.job_id)}`),
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const handler = handlers[message?.type];
  if (!handler) return false;

  Promise.resolve().then(() => handler(message.payload))
    .then((data) => sendResponse({ ok: true, data }))
    .catch((error) => sendResponse({ ok: false, error: error.message || "Request failed" }));
  return true;
});
