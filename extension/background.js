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
  const response = await fetch(`${base}${path}`, {
    ...init,
    signal: AbortSignal.timeout(180000),
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
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

const handlers = {
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
  F1_SEAL: payload => apiRequest('/api/f1/seal', {method:'POST',body:JSON.stringify(payload)}),
  F1_INTERVALS: payload => apiRequest('/api/f1/intervals', {method:'POST',body:JSON.stringify(payload)}),
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
