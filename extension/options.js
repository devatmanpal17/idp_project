const defaults = { apiBaseUrl: "http://localhost:8000", autoCapture: true };
const urlInput = document.getElementById("apiBaseUrl");
const autoInput = document.getElementById("autoCapture");
const result = document.getElementById("result");

chrome.storage.sync.get(defaults).then((settings) => {
  urlInput.value = settings.apiBaseUrl;
  autoInput.checked = settings.autoCapture;
});

document.getElementById("save").addEventListener("click", async () => {
  const apiBaseUrl = urlInput.value.trim().replace(/\/$/, "");
  if (!/^https?:\/\//.test(apiBaseUrl)) {
    result.textContent = "Enter a valid http:// or https:// URL.";
    return;
  }
  const origin = new URL(apiBaseUrl).origin;
  if (!["http://localhost:8000", "http://127.0.0.1:8000"].includes(origin)) {
    result.textContent = "This build only permits the local backend on port 8000.";
    return;
  }
  await chrome.storage.sync.set({ apiBaseUrl, autoCapture: autoInput.checked });
  const response = await chrome.runtime.sendMessage({ type: "HEALTH" });
  result.textContent = response?.ok ? "Saved. AI engine is online." : `Saved, but connection failed: ${response?.error || "unknown error"}`;
});
