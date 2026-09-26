const statusNode = document.getElementById("status");
const statusText = document.getElementById("statusText");

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
  } catch (error) {
    if (!/Receiving end does not exist|Could not establish connection/i.test(error?.message || "")) {
      throw error;
    }
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["observation.js", "content.js"] });
    return chrome.tabs.sendMessage(tab.id, { type });
  }
}

function showStatus(message, state) {
  statusNode.className = `status ${state}`;
  statusText.textContent = message;
}

askBackground("HEALTH")
  .then((response) => {
    if (!response?.ok) throw new Error(response?.error || "Offline");
    showStatus(
      `${response.data.active_ai_provider} · ${response.data.indexed_chunks} notes indexed`,
      "online",
    );
  })
  .catch(() => showStatus("Engine offline · start ChaiGaram on port 8000", "offline"));

document.getElementById("back").addEventListener("click", async () => {
  const tab = await activeTab();
  if (tab?.id) await chrome.tabs.goBack(tab.id).catch(() => undefined);
  window.close();
});

document.getElementById("open").addEventListener("click", async () => {
  try {
    await sendToPage("CHAIGARAM_TOGGLE");
    window.close();
  } catch (_) {
    showStatus("This page cannot run extensions. Try a normal website.", "offline");
  }
});

document.getElementById("dashboard").addEventListener("click", async () => {
  try {
    const settings = await chrome.storage.sync.get({ dashboardUrl: "http://localhost:8080" });
    await chrome.tabs.create({ url: ChaiConnection.connectionURL(settings.dashboardUrl) });
    window.close();
  } catch (error) {
    showStatus(error.message, 'offline');
  }
});

document.getElementById("capturePage").addEventListener("click", async () => {
  try {
    await sendToPage("CHAIGARAM_CAPTURE_PAGE");
    window.close();
  } catch (_) {
    showStatus("Open an article, lesson, documentation page, or video first.", "offline");
  }
});

document.getElementById("capture").addEventListener("click", async () => {
  try {
    await sendToPage("CHAIGARAM_CAPTURE_SELECTION");
    window.close();
  } catch (_) {
    showStatus("Select some learning text on the page first.", "offline");
  }
});

document.getElementById("options").addEventListener("click", () =>
  chrome.runtime.openOptionsPage(),
);
