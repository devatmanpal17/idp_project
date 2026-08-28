const statusNode = document.getElementById("status");

function askBackground(type, payload) {
  return chrome.runtime.sendMessage({ type, payload });
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function sendToPage(type) {
  const tab = await activeTab();
  if (!tab?.id) throw new Error("No active webpage");
  try {
    return await chrome.tabs.sendMessage(tab.id, { type });
  } catch (_) {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
    return chrome.tabs.sendMessage(tab.id, { type });
  }
}

askBackground("HEALTH").then((response) => {
  if (!response?.ok) throw new Error(response?.error || "Offline");
  statusNode.className = "status online";
  statusNode.textContent = `${response.data.active_ai_provider} · ${response.data.indexed_chunks} notes indexed`;
}).catch(() => {
  statusNode.className = "status offline";
  statusNode.textContent = "Backend offline · start ChaiGaram on port 8000";
});

document.getElementById("open").addEventListener("click", async () => {
  try { await sendToPage("CHAIGARAM_TOGGLE"); window.close(); }
  catch (_) { statusNode.textContent = "This browser page cannot run extensions. Try a normal website."; }
});

document.getElementById("dashboard").addEventListener("click", async () => {
  const settings = await chrome.storage.sync.get({ dashboardUrl: "http://localhost:8080" });
  await chrome.tabs.create({ url: settings.dashboardUrl });
  window.close();
});

document.getElementById("capturePage").addEventListener("click", async () => {
  try { await sendToPage("CHAIGARAM_CAPTURE_PAGE"); window.close(); }
  catch (_) { statusNode.textContent = "Open a normal article, lesson, documentation, or video page first."; }
});

document.getElementById("capture").addEventListener("click", async () => {
  try { await sendToPage("CHAIGARAM_CAPTURE_SELECTION"); window.close(); }
  catch (_) { statusNode.textContent = "Select some learning text on the page first."; }
});

document.getElementById("options").addEventListener("click", () => chrome.runtime.openOptionsPage());
