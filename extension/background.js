const DEFAULT_SETTINGS = {
  apiBaseUrl: "http://localhost:8000",
  autoCapture: true,
};

chrome.runtime.onInstalled.addListener(async () => {
  const current = await chrome.storage.sync.get(DEFAULT_SETTINGS);
  await chrome.storage.sync.set(current);
});

async function apiRequest(path, init = {}) {
  const { apiBaseUrl } = await chrome.storage.sync.get(DEFAULT_SETTINGS);
  const base = String(apiBaseUrl || DEFAULT_SETTINGS.apiBaseUrl).replace(/\/$/, "");
  const response = await fetch(`${base}${path}`, {
    ...init,
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
  HEALTH: () => apiRequest("/api/health"),
  INGEST: (payload) => apiRequest("/api/rag/stream-transcript", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  ASK: (payload) => apiRequest("/api/rag/ask", {
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
  TOPIC_STATE: (payload) => apiRequest(`/api/learning/topic-state?topic=${encodeURIComponent(payload.topic)}`),
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const handler = handlers[message?.type];
  if (!handler) return false;

  handler(message.payload)
    .then((data) => sendResponse({ ok: true, data }))
    .catch((error) => sendResponse({ ok: false, error: error.message || "Request failed" }));
  return true;
});
