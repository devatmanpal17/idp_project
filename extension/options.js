const defaults = { apiBaseUrl: "http://localhost:8000", dashboardUrl: "http://localhost:8080", autoCapture: true };
const urlInput = document.getElementById("apiBaseUrl");
const dashboardInput = document.getElementById("dashboardUrl");
const autoInput = document.getElementById("autoCapture");
const result = document.getElementById("result");
const saveButton = document.getElementById("save");

function showResult(message, state = "") {
  result.className = state;
  result.textContent = message;
}

chrome.storage.sync.get(defaults).then((settings) => {
  urlInput.value = settings.apiBaseUrl;
  dashboardInput.value = settings.dashboardUrl;
  autoInput.checked = settings.autoCapture;
});

document.getElementById("back").addEventListener("click", () => {
  if (history.length > 1) history.back();
  else window.close();
});

saveButton.addEventListener("click", async () => {
  let apiBaseUrl, dashboardUrl;
  try {
    apiBaseUrl = ChaiConnection.connectionURL(urlInput.value);
    dashboardUrl = ChaiConnection.connectionURL(dashboardInput.value);
  } catch (error) {
    showResult(error.message, 'error');
    return;
  }
  saveButton.disabled = true;
  showResult("Saving settings and testing the engine...");
  try {
    await chrome.storage.sync.set({ apiBaseUrl, dashboardUrl, autoCapture: autoInput.checked });
    const response = await chrome.runtime.sendMessage({ type: "HEALTH" });
    if (!response?.ok) throw new Error(response?.error || "Engine did not respond.");
    showResult(response.data.status === 'ready' ? "Saved. Your private AI engine is online." :
      "Saved. The backend is online, but an Ollama model needs setup.", response.data.status === 'ready' ? 'success' : 'error');
  } catch (error) {
    showResult(`Saved, but the connection test failed: ${error.message}`, "error");
  } finally {
    saveButton.disabled = false;
  }
});
