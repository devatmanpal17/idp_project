const defaults = { apiBaseUrl: "http://localhost:8000", dashboardUrl: "http://localhost:8080", autoCapture: true };
const urlInput = document.getElementById("apiBaseUrl");
const dashboardInput = document.getElementById("dashboardUrl");
const autoInput = document.getElementById("autoCapture");
const result = document.getElementById("result");

chrome.storage.sync.get(defaults).then((settings) => {
  urlInput.value = settings.apiBaseUrl;
  dashboardInput.value = settings.dashboardUrl;
  autoInput.checked = settings.autoCapture;
});

document.getElementById("save").addEventListener("click", async () => {
  const apiBaseUrl = urlInput.value.trim().replace(/\/$/, "");
  const dashboardUrl = dashboardInput.value.trim().replace(/\/$/, "");
  if (!/^https?:\/\//.test(apiBaseUrl)) {
    result.textContent = "Enter a valid http:// or https:// URL.";
    return;
  }
  if (!/^https?:\/\//.test(dashboardUrl)) {
    result.textContent = "Enter a valid dashboard URL.";
    return;
  }
  await chrome.storage.sync.set({ apiBaseUrl, dashboardUrl, autoCapture: autoInput.checked });
  const response = await chrome.runtime.sendMessage({ type: "HEALTH" });
  result.textContent = response?.ok ? "Saved. AI engine is online." : `Saved, but connection failed: ${response?.error || "unknown error"}`;
});
