(() => {
  if (globalThis.__CHAIGARAM_LOADED__) return;
  globalThis.__CHAIGARAM_LOADED__ = true;
  const ROOT_ID = "chaigaram-extension-root";
  document.getElementById(ROOT_ID)?.remove();
  const CAPTION_SELECTORS = [
    ".ytp-caption-segment",
    "[data-purpose='caption-cue-text']",
    "[data-testid*='caption']",
    ".video-transcript--cue-text",
    ".subtitles .text",
    "[class*='captions-text']",
    "[class*='subtitle']",
    "[class*='transcript'] [aria-live='polite']",
    "video + [aria-live]",
  ];
  const MAX_CONTEXT_CHARS = 48000;
  const MIN_VIDEO_QUIZ_WORDS = 50;
  const state = {
    open: false,
    minimized: false,
    transcript: [],
    lastCaption: "",
    mastery: 0,
    assessed: false,
    quizPerf: 0,
    minutesOnSection: 0,
    revisits: 0,
    quiz: null,
    quizId: null,
    pageContext: "",
    pageKey: currentPageKey(),
    captionTrackKey: "",
    captionTrackPromise: null,
    lastCaptureAt: Date.now(),
  };
  let host;
  let shadow;
  let captureTimer;

  const send = (type, payload) => new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type, payload }, (response) => {
      if (chrome.runtime.lastError) {
        return reject(new Error("The extension connection restarted. Please retry the action."));
      }
      if (!response?.ok) return reject(new Error(response?.error || "AI request failed"));
      resolve(response.data);
    });
  });

  const pause = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  async function runAI(operation, payload) {
    const started = await send("JOB_START", { operation, payload });
    const deadline = Date.now() + 310000;
    let transientFailures = 0;
    while (Date.now() < deadline) {
      await pause(1400);
      try {
        const job = await send("JOB_STATUS", { job_id: started.job_id });
        transientFailures = 0;
        if (job.status === "succeeded") return job.result;
        if (job.status === "failed") {
          const failure = new Error(job.error || "The AI request failed.");
          failure.terminal = true;
          throw failure;
        }
      } catch (error) {
        if (error.terminal) throw error;
        transientFailures += 1;
        if (transientFailures >= 3) throw error;
      }
    }
    throw new Error("The AI request timed out. Please try again.");
  }

  function activeVideo() {
    const youtubePlayer = document.querySelector("#movie_player video.html5-main-video");
    if (youtubePlayer) return youtubePlayer;
    const candidate = [...document.querySelectorAll("video")]
      .map((video) => {
        const rect = video.getBoundingClientRect();
        return { video, area: rect.width * rect.height };
      })
      .filter(({ area }) => area >= 48000)
      .sort((a, b) => b.area - a.area)[0];
    return candidate?.video || null;
  }

  function playerIsShowingAd() {
    return Boolean(document.querySelector("#movie_player.ad-showing"));
  }

  function sourceType() {
    return activeVideo() ? "video" : "document";
  }

  function currentPageKey() {
    try {
      const url = new URL(location.href);
      const videoId = url.searchParams.get("v");
      return videoId ? `${url.origin}${url.pathname}?v=${videoId}` : `${url.origin}${url.pathname}${url.search}`;
    } catch (_) {
      return location.href.split("#")[0];
    }
  }

  function youtubeVideoId() {
    if (!location.hostname.includes("youtube.com")) return "";
    const url = new URL(location.href);
    if (url.pathname.startsWith("/shorts/")) return url.pathname.split("/")[2] || "";
    return url.searchParams.get("v") || "";
  }

  function resetForNavigation() {
    const nextKey = currentPageKey();
    if (nextKey === state.pageKey) return;
    state.pageKey = nextKey;
    state.transcript = [];
    state.lastCaption = "";
    state.pageContext = "";
    state.quiz = null;
    state.quizId = null;
    state.captionTrackKey = "";
    state.captionTrackPromise = null;
    state.mastery = 0;
    state.assessed = false;
    state.lastCaptureAt = Date.now();
    updateCaptureCount();
    if (shadow) {
      shadow.getElementById("answer")?.replaceChildren();
      shadow.getElementById("quiz")?.replaceChildren();
      refreshHeader();
      setStatus("New page detected. Ready to capture this source.");
    }
  }

  function topic() {
    const video = activeVideo();
    const candidates = video ? [
      document.querySelector("meta[property='og:title']")?.content,
      document.querySelector("h1.ytd-watch-metadata, #title h1")?.textContent,
      document.title,
    ] : [
      document.querySelector("[data-purpose='course-header-title']")?.textContent,
      document.querySelector("article h1, main h1, [role='main'] h1")?.textContent,
      document.querySelector("h1")?.textContent,
      document.querySelector("meta[property='og:title']")?.content,
      document.title,
    ];
    return candidates.find((value) => value?.trim())?.trim()
      .replace(/\s*[-|]\s*YouTube\s*$/i, "").slice(0, 300) || "Current lesson";
  }

  function learningPageText() {
    if (sourceType() === "video") return "";
    const root = document.querySelector("article")
      || document.querySelector("[itemprop='articleBody']")
      || document.querySelector("main")
      || document.querySelector("[role='main']")
      || document.body;
    const clone = root.cloneNode(true);
    clone.querySelectorAll([
      "script", "style", "nav", "header", "footer", "form", "button", "noscript", "svg", "aside",
      "[aria-hidden='true']", "[role='navigation']", "[role='complementary']", "[class*='sidebar']", "[id*='sidebar']",
      "[class*='recommend']", "[id*='recommend']", "[class*='related']", "[id*='related']",
      "[class*='comment']", "[id*='comment']", "[class*='advert']", "[id*='advert']",
    ].join(",")).forEach((node) => node.remove());
    clone.querySelectorAll("section, div, ul, ol").forEach((node) => {
      const textLength = (node.textContent || "").trim().length;
      const links = [...node.querySelectorAll("a")];
      const linkLength = links.reduce((total, link) => total + (link.textContent || "").trim().length, 0);
      if (links.length >= 3 && textLength > 0 && linkLength / textLength > 0.55) node.remove();
    });
    const blocks = [...clone.querySelectorAll("h1, h2, h3, p, li, pre, blockquote, figcaption")]
      .map((node) => node.textContent?.replace(/\s+/g, " ").trim())
      .filter((text) => text && text.length > 20);
    return [...new Set(blocks)].join("\n").slice(0, MAX_CONTEXT_CHARS);
  }

  function activePageContext() {
    resetForNavigation();
    const video = activeVideo();
    if (video) {
      collectNativeTextTrackCues(video);
      const currentSeconds = Number(video.currentTime || 0);
      const preferredSource = state.transcript.some(
        (item) => item.pageKey === state.pageKey && item.source === "official-caption"
      ) ? "official-caption" : state.transcript.some(
        (item) => item.pageKey === state.pageKey && item.source === "text-track"
      ) ? "text-track" : "caption";
      return state.transcript
        .filter((item) =>
          item.pageKey === state.pageKey
          && item.source === preferredSource
          && item.positionSeconds <= currentSeconds + 1
        )
        .sort((a, b) => a.positionSeconds - b.positionSeconds)
        .map((item) => `[${item.time}] ${item.text}`)
        .join("\n")
        .slice(-MAX_CONTEXT_CHARS);
    }
    return (state.pageContext || learningPageText()).slice(0, MAX_CONTEXT_CHARS);
  }

  async function sourceContext(action, minimumVideoWords = MIN_VIDEO_QUIZ_WORDS) {
    if (activeVideo()) await loadYouTubeCaptionCues();
    const text = activePageContext();
    const kind = sourceType();
    const countableText = kind === "video" ? text.replace(/^\[[^\]]+\]\s*/gm, "") : text;
    const wordCount = countableText.split(/\s+/).filter(Boolean).length;
    if (kind === "video" && wordCount < minimumVideoWords) {
      throw new Error(
        `Only ${wordCount} caption words have been captured. Turn on English captions and watch a little more before ${action}.`
      );
    }
    if (kind === "document" && wordCount < 20) {
      throw new Error("I could not find enough article or document text on this page.");
    }
    return {
      text,
      kind,
      wordCount,
      observedUntilSeconds: Number(activeVideo()?.currentTime || 0),
    };
  }

  function timestamp() {
    const video = activeVideo();
    const seconds = Math.max(0, Math.floor(video?.currentTime || 0));
    return formatTime(seconds);
  }

  function formatTime(value) {
    const seconds = Math.max(0, Math.floor(value || 0));
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function newCaptionText(previous, current) {
    if (!previous) return current;
    if (previous === current || previous.includes(current)) return "";
    const oldWords = previous.split(/\s+/);
    const newWords = current.split(/\s+/);
    const maxOverlap = Math.min(oldWords.length, newWords.length);
    for (let size = maxOverlap; size > 0; size -= 1) {
      const oldTail = oldWords.slice(-size).join(" ").toLocaleLowerCase();
      const newHead = newWords.slice(0, size).join(" ").toLocaleLowerCase();
      if (oldTail === newHead) return newWords.slice(size).join(" ");
    }
    return current;
  }

  function trimTranscript() {
    while (state.transcript.length > 600) state.transcript.shift();
    let chars = state.transcript.reduce((total, item) => total + item.text.length + 12, 0);
    while (chars > MAX_CONTEXT_CHARS && state.transcript.length > 1) {
      chars -= state.transcript.shift().text.length + 12;
    }
  }

  function storeTranscriptCue(text, positionSeconds, source = "text-track") {
    const clean = String(text || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
    if (clean.length < 2) return;
    const duplicate = state.transcript.some((item) =>
      item.pageKey === state.pageKey
      && Math.abs(item.positionSeconds - positionSeconds) < 0.25
      && item.text.toLocaleLowerCase() === clean.toLocaleLowerCase()
    );
    if (duplicate) return;
    const seconds = Math.max(0, Math.floor(positionSeconds));
    state.transcript.push({
      text: clean,
      time: `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`,
      source,
      pageKey: state.pageKey,
      positionSeconds,
    });
    state.transcript.sort((a, b) => a.positionSeconds - b.positionSeconds);
    trimTranscript();
    updateCaptureCount();
  }

  function collectNativeTextTrackCues(video) {
    const currentSeconds = Number(video.currentTime || 0);
    let eligibleCues = 0;
    for (const track of [...(video.textTracks || [])]) {
      for (const cue of [...(track.cues || [])]) {
        if (Number(cue.startTime || 0) <= currentSeconds + 1) {
          eligibleCues += 1;
          storeTranscriptCue(cue.text, Number(cue.startTime || 0));
        }
      }
    }
    return eligibleCues;
  }

  function balancedJson(text, startIndex) {
    const start = text.indexOf("{", startIndex);
    if (start < 0) return null;
    let depth = 0;
    let quoted = false;
    let escaped = false;
    for (let index = start; index < text.length; index += 1) {
      const character = text[index];
      if (quoted) {
        if (escaped) escaped = false;
        else if (character === "\\") escaped = true;
        else if (character === '"') quoted = false;
        continue;
      }
      if (character === '"') quoted = true;
      else if (character === "{") depth += 1;
      else if (character === "}") {
        depth -= 1;
        if (depth === 0) return text.slice(start, index + 1);
      }
    }
    return null;
  }

  function youtubePlayerResponse() {
    const expectedId = youtubeVideoId();
    for (const script of [...document.scripts]) {
      const text = script.textContent || "";
      let marker = text.indexOf("ytInitialPlayerResponse");
      while (marker >= 0) {
        const candidate = balancedJson(text, marker);
        if (!candidate) break;
        try {
          const response = JSON.parse(candidate);
          if (!expectedId || response?.videoDetails?.videoId === expectedId) return response;
        } catch (_) {
          // Some scripts mention the variable without embedding its JSON value.
        }
        marker = text.indexOf("ytInitialPlayerResponse", marker + 1);
      }
    }
    return null;
  }

  async function fetchYouTubeCaptionCues(pageKey) {
    const playerResponse = youtubePlayerResponse();
    const tracks = playerResponse?.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
    const track = tracks.find((item) => String(item.languageCode || "").toLowerCase().startsWith("en"))
      || tracks[0];
    if (!track?.baseUrl) return 0;
    const captionUrl = new URL(track.baseUrl);
    captionUrl.searchParams.set("fmt", "json3");
    const response = await fetch(captionUrl.toString(), { credentials: "include" });
    if (!response.ok) throw new Error(`Caption track request failed (${response.status}).`);
    const payload = await response.json();
    const observedUntil = Number(activeVideo()?.currentTime || 0) + 1;
    let stored = 0;
    for (const event of payload.events || []) {
      if (state.pageKey !== pageKey || !Array.isArray(event.segs)) break;
      const startSeconds = Number(event.tStartMs || 0) / 1000;
      if (startSeconds > observedUntil) continue;
      const text = event.segs.map((segment) => segment.utf8 || "").join("");
      if (!text.trim() || text.trim() === "\n") continue;
      storeTranscriptCue(text, startSeconds, "official-caption");
      stored += 1;
    }
    return stored;
  }

  async function loadYouTubeCaptionCues() {
    if (!youtubeVideoId()) return 0;
    const pageKey = state.pageKey;
    if (state.captionTrackKey === pageKey && state.captionTrackPromise) {
      return state.captionTrackPromise;
    }
    state.captionTrackKey = pageKey;
    const request = fetchYouTubeCaptionCues(pageKey).catch(() => 0);
    state.captionTrackPromise = request;
    try {
      return await request;
    } finally {
      if (state.captionTrackPromise === request) state.captionTrackPromise = null;
    }
  }

  async function ingest(text, source = "caption") {
    resetForNavigation();
    const raw = String(text || "").replace(/\s+/g, " ").trim();
    if (raw.length < 2) return;
    const clean = source === "caption" ? newCaptionText(state.lastCaption, raw) : raw;
    if (source === "caption") state.lastCaption = raw;
    if (clean.length < 2) return;
    const video = activeVideo();
    const item = {
      text: clean,
      time: timestamp(),
      source,
      pageKey: state.pageKey,
      positionSeconds: Number(video?.currentTime || 0),
    };
    const now = Date.now();
    const dwellSeconds = Math.max(1, Math.round((now - state.lastCaptureAt) / 1000));
    state.lastCaptureAt = now;
    state.transcript.push(item);
    trimTranscript();
    updateCaptureCount();
    try {
      const result = await send("INGEST", {
        video_title: document.title.slice(0, 300),
        timestamp: item.time,
        transcript_segment: clean,
        current_topic: topic(),
        dwell_seconds: dwellSeconds,
        page_url: location.href,
        video_position_seconds: Number(video?.currentTime || 0),
        video_duration_seconds: Number(video?.duration || 0),
      });
      setStatus(result.indexed ? `Captured ${result.words_captured} words` : "Caption already captured", "ok");
      await refreshTopicState();
    } catch (error) {
      setStatus(`Backend unavailable: ${error.message}`, "error");
    }
  }

  function scanCaptions() {
    resetForNavigation();
    const video = activeVideo();
    if (!video || playerIsShowingAd()) return;
    if (collectNativeTextTrackCues(video) > 0) return;
    const parts = [];
    const selectors = location.hostname.includes("youtube.com")
      ? ["#movie_player:not(.ad-showing) .ytp-caption-segment"]
      : CAPTION_SELECTORS;
    for (const selector of selectors) {
      document.querySelectorAll(selector).forEach((node) => {
        const value = node.textContent?.trim();
        if (value && !parts.includes(value)) parts.push(value);
      });
      if (parts.length) break;
    }
    if (parts.length) ingest(parts.join(" "));
  }

  function beginCapture() {
    setInterval(resetForNavigation, 1000);
    window.addEventListener("popstate", resetForNavigation);
    window.addEventListener("yt-navigate-finish", resetForNavigation);
    chrome.storage.sync.get({ autoCapture: true }).then(({ autoCapture }) => {
      if (!autoCapture) return;
      const hasLearningMedia = () => Boolean(activeVideo());
      const observer = new MutationObserver(() => {
        if (!hasLearningMedia()) return;
        clearTimeout(captureTimer);
        captureTimer = setTimeout(scanCaptions, 350);
      });
      observer.observe(document.body, { childList: true, subtree: true, characterData: true });
      setInterval(() => hasLearningMedia() && scanCaptions(), 3000);
    });
  }

  const styles = `
    :host { all: initial; }
    * { box-sizing: border-box; }
    .panel { position:fixed; z-index:2147483647; top:68px; right:20px; width:390px; max-height:calc(100vh - 90px); overflow:hidden; color:#f5f0e5; background:#191918; border:2px solid #f5f0e5; box-shadow:8px 9px 0 #090909; font:13px/1.45 "Arial Narrow", "Segoe UI", sans-serif; }
    .panel::after { content:""; position:absolute; inset:0; z-index:-1; opacity:.16; pointer-events:none; background-image:radial-gradient(#f5f0e5 1px,transparent 1px); background-size:15px 15px; }
    .panel.hidden { display:none; } .panel.min .body { display:none; }
    header { display:flex; align-items:center; justify-content:space-between; padding:11px 12px; border-bottom:2px solid #f5f0e5; background:#22211f; }
    .brand { display:flex; align-items:center; gap:9px; font-size:14px; font-weight:950; letter-spacing:-.03em; text-transform:uppercase; }
    .mark { display:grid; place-items:center; width:31px; height:31px; color:#171716; background:#ff5a36; border:2px solid #f5f0e5; box-shadow:2px 2px 0 #f5f0e5; font-size:13px; transform:rotate(-4deg); }
    .live { padding:3px 5px; color:#171716; background:#e8f24e; font:800 8px ui-monospace,monospace; letter-spacing:.08em; }
    .header-actions { display:flex; align-items:center; gap:7px; }
    .icon { width:25px; height:25px; padding:0; border:1px solid #625e57; color:#f5f0e5; background:#191918; font-size:16px; cursor:pointer; }
    .body { max-height:calc(100vh - 145px); overflow:auto; padding:14px; scrollbar-color:#ff5a36 #252421; }
    .lesson { margin-bottom:13px; padding-bottom:9px; border-bottom:1px dashed #625e57; color:#aaa398; font:10px ui-monospace,monospace; text-transform:uppercase; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .meterline { display:flex; justify-content:space-between; margin-bottom:6px; font-size:11px; font-weight:750; }
    .meter { height:8px; margin-bottom:14px; overflow:hidden; border:1px solid #f5f0e5; background:#2e2c29; } .meter span { display:block; height:100%; background:#5577ff; }
    .tabs { display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-bottom:13px; }
    .tab { padding:8px; border:1px solid #625e57; color:#aaa398; background:#252421; font-weight:850; cursor:pointer; } .tab.active { color:#171716; border-color:#f5f0e5; background:#e8f24e; box-shadow:2px 2px 0 #f5f0e5; }
    textarea { width:100%; min-height:82px; resize:vertical; padding:11px; border:2px solid #625e57; outline:none; color:#f5f0e5; background:#111; font:inherit; } textarea:focus { border-color:#5577ff; }
    .primary { width:100%; margin-top:8px; padding:11px; border:2px solid #f5f0e5; color:#171716; background:#ff5a36; box-shadow:3px 3px 0 #f5f0e5; font-weight:900; cursor:pointer; } .primary:hover { transform:translate(1px,1px); box-shadow:2px 2px 0 #f5f0e5; } .primary:disabled { opacity:.55; cursor:wait; }
    .answer { margin-top:13px; padding:12px; border:2px solid #f5f0e5; color:#e9e3d8; background:#252421; white-space:pre-wrap; }
    .sources { margin-top:10px; color:#aaa398; font:10px ui-monospace,monospace; } .source { margin-top:6px; padding-left:8px; border-left:3px solid #5577ff; }
    .status { margin:12px 0 0; padding-top:9px; border-top:1px dashed #625e57; color:#aaa398; font:10px ui-monospace,monospace; } .status.ok { color:#49d78d; } .status.error { color:#ff8292; }
    .quiz-item { margin:12px 0; padding:12px; border:2px solid #625e57; background:#252421; } .question { margin:0 0 10px; font-weight:850; }
    .choice { display:flex; gap:8px; margin-top:7px; padding:9px; border:1px solid #4d4943; color:#ded8cd; background:#111; cursor:pointer; } .choice:hover { border-color:#e8f24e; } .choice input { accent-color:#ff5a36; }
    .result { margin-top:10px; padding:10px; border-left:4px solid currentColor; background:#111; } .correct { color:#49d78d; } .wrong { color:#ff8292; }
    @media (max-width:520px) { .panel { top:8px; right:8px; left:8px; width:auto; max-height:calc(100vh - 16px); } }
  `;

  function buildOverlay() {
    if (host) return;
    host = document.createElement("div");
    host.id = ROOT_ID;
    shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>${styles}</style>
      <aside class="panel hidden" aria-label="ChaiGaram learning assistant">
        <header><div class="brand"><span class="mark">CG</span><span>ChaiGaram Companion</span></div><div class="header-actions"><span class="live">● LIVE RAG</span><button class="icon" id="min" title="Minimize">−</button><button class="icon" id="close" title="Close">×</button></div></header>
        <div class="body">
          <div class="lesson" id="lesson"></div>
          <div class="meterline"><span>Verified lesson mastery</span><strong id="mastery">Not assessed</strong></div><div class="meter"><span id="meter" style="width:0%"></span></div>
          <div class="tabs"><button class="tab active" data-tab="ask">Ask tutor</button><button class="tab" data-tab="quiz">Adaptive quiz</button></div>
          <div id="askPane"><button class="primary" id="summarize">Teach me this page</button><textarea id="question" placeholder="Ask anything about this page or video..."></textarea><button class="primary" id="ask">Ask about this page</button><div id="answer"></div></div>
          <div id="quizPane" hidden><button class="primary" id="generate">Generate quiz from this lesson</button><div id="quiz"></div></div>
          <div class="status" id="status">Waiting for visible captions · <span id="count">0</span> captured</div>
        </div>
      </aside>`;
    const brandParts = shadow.querySelectorAll(".brand span");
    brandParts[0].textContent = "CG";
    brandParts[1].textContent = "ChaiGaram Sidekick";
    shadow.querySelector(".live").textContent = "ON THIS PAGE";
    shadow.getElementById("min").textContent = "−";
    shadow.getElementById("close").textContent = "×";
    shadow.querySelector(".meterline span").textContent = "What has actually stuck";
    shadow.getElementById("mastery").textContent = "Not tested yet";
    const tabs = shadow.querySelectorAll(".tab");
    tabs[0].textContent = "Ask the page";
    tabs[1].textContent = "Test me";
    shadow.getElementById("question").placeholder = "Ask about this page, video, article, or saved selection…";
    shadow.getElementById("ask").textContent = "Ask about this page";
    shadow.getElementById("generate").textContent = "Make a quiz from this page";
    shadow.getElementById("status").innerHTML = 'Ready for captions, page text, or a selection · <span id="count">0</span> saved';
    document.documentElement.appendChild(host);

    shadow.getElementById("close").addEventListener("click", () => setOpen(false));
    shadow.getElementById("min").addEventListener("click", () => {
      state.minimized = !state.minimized;
      shadow.querySelector(".panel").classList.toggle("min", state.minimized);
      shadow.getElementById("min").textContent = state.minimized ? "+" : "−";
    });
    shadow.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.tab)));
    shadow.getElementById("ask").addEventListener("click", askQuestion);
    shadow.getElementById("summarize").addEventListener("click", summarizePage);
    shadow.getElementById("generate").addEventListener("click", generateQuiz);
    refreshHeader();
  }

  function refreshHeader() {
    if (!shadow) return;
    shadow.getElementById("lesson").textContent = topic();
    shadow.getElementById("mastery").textContent = state.assessed ? `${Math.round(state.mastery)}%` : "Not tested yet";
    shadow.getElementById("meter").style.width = `${Math.max(0, Math.min(100, state.mastery))}%`;
  }

  function setOpen(open) {
    buildOverlay();
    state.open = open;
    shadow.querySelector(".panel").classList.toggle("hidden", !open);
    if (open) {
      refreshTopicState();
    }
  }

  async function refreshTopicState() {
    try {
      const data = await send("TOPIC_STATE", { topic: topic() });
      state.mastery = Number(data.mastery_score || 0);
      state.assessed = Boolean(data.assessed);
      state.quizPerf = Number(data.quiz_perf_pct || 0);
      state.minutesOnSection = Number(data.minutes_on_section || 0);
      state.revisits = Number(data.revisits || 0);
      refreshHeader();
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  function switchTab(name) {
    shadow.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === name));
    shadow.getElementById("askPane").hidden = name !== "ask";
    shadow.getElementById("quizPane").hidden = name !== "quiz";
  }

  function setStatus(message, kind = "") {
    if (!shadow) return;
    const node = shadow.getElementById("status");
    node.className = `status ${kind}`;
    node.textContent = message;
  }

  function updateCaptureCount() {
    if (shadow?.getElementById("count")) shadow.getElementById("count").textContent = state.transcript.length;
  }

  async function askQuestion() {
    const input = shadow.getElementById("question");
    const button = shadow.getElementById("ask");
    const question = input.value.trim();
    if (question.length < 2) return setStatus("Type a question first.", "error");
    button.disabled = true;
    button.textContent = "Looking through your notes…";
    shadow.getElementById("answer").replaceChildren();
    try {
      const context = await sourceContext("asking a question", 8);
      const requestPageKey = state.pageKey;
      const data = await runAI("ask", {
        question,
        topic: topic(),
        transcript_context: context.text,
        source_type: context.kind,
        observed_until_seconds: context.observedUntilSeconds,
        top_k: 5,
      });
      if (requestPageKey !== state.pageKey) return;
      const answer = document.createElement("div");
      answer.className = "answer";
      answer.textContent = data.answer;
      const sources = document.createElement("div");
      sources.className = "sources";
      sources.textContent = `${data.active_provider} · ${data.sources.length} sources`;
      data.sources.slice(0, 3).forEach((source) => {
        const node = document.createElement("div");
        node.className = "source";
        node.textContent = `${source.timestamp} · ${source.snippet.slice(0, 130)}`;
        sources.appendChild(node);
      });
      shadow.getElementById("answer").append(answer, sources);
      setStatus("Answer grounded in indexed lesson chunks.", "ok");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = "Ask about this page";
    }
  }

  async function summarizePage() {
    const button = shadow.getElementById("summarize");
    button.disabled = true;
    button.textContent = "Building your lesson...";
    shadow.getElementById("answer").replaceChildren();
    try {
      const context = await sourceContext("building a lesson", 20);
      const requestPageKey = state.pageKey;
      setStatus(
        context.kind === "video"
          ? `Teaching only from ${context.wordCount} caption words captured through ${formatTime(context.observedUntilSeconds)}.`
          : `Teaching only from the current document (${context.wordCount} words).`,
        "ok",
      );
      const data = await runAI("summarize", {
        topic: topic(),
        page_content: context.text,
        page_url: location.href,
        source_type: context.kind,
        observed_until_seconds: context.observedUntilSeconds,
      });
      if (requestPageKey !== state.pageKey) return;
      const answer = document.createElement("div");
      answer.className = "answer";
      answer.textContent = data.summary;
      shadow.getElementById("answer").appendChild(answer);
      shadow.getElementById("question").focus();
      setStatus("Page lesson ready. Ask a follow-up question below.", "ok");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = "Teach me this page again";
    }
  }

  async function generateQuiz() {
    const button = shadow.getElementById("generate");
    button.disabled = true;
    button.textContent = "Writing your questions…";
    const container = shadow.getElementById("quiz");
    container.replaceChildren();
    state.quiz = null;
    state.quizId = null;
    try {
      const context = await sourceContext("making a quiz");
      const requestPageKey = state.pageKey;
      const scopeMessage = context.kind === "video"
        ? `${context.wordCount} caption words through ${formatTime(context.observedUntilSeconds)}`
        : `${context.wordCount} words from this document`;
      setStatus(`Generating an English quiz from ${scopeMessage} only.`, "ok");
      const data = await runAI("quiz", {
        topic: topic(),
        source_context: context.text,
        page_url: location.href,
        language: "English",
        source_type: context.kind,
        observed_until_seconds: context.observedUntilSeconds,
        mastery_score: state.mastery,
        quiz_perf_pct: state.quizPerf,
        time_on_section_pct: state.minutesOnSection,
        revisit_frequency_pct: state.revisits,
        recent_errors: [],
        question_count: 3,
      });
      if (requestPageKey !== state.pageKey) return;
      state.quiz = data.questions;
      state.quizId = data.quiz_id;
      renderQuiz(data.questions, data.active_provider);
      setStatus(`English quiz generated from ${scopeMessage} only.`, "ok");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = "Generate another quiz";
    }
  }

  function renderQuiz(questions, provider) {
    const container = shadow.getElementById("quiz");
    container.replaceChildren();
    questions.forEach((question, index) => {
      const card = document.createElement("section");
      card.className = "quiz-item";
      const title = document.createElement("p");
      title.className = "question";
      title.textContent = `${index + 1}. ${question.q}`;
      card.appendChild(title);
      question.choices.forEach((choice) => {
        const label = document.createElement("label");
        label.className = "choice";
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = `cg-question-${index}`;
        radio.value = choice;
        const text = document.createElement("span");
        text.textContent = choice;
        label.append(radio, text);
        card.appendChild(label);
      });
      container.appendChild(card);
    });
    const submit = document.createElement("button");
    submit.className = "primary";
    submit.textContent = `Check answers · ${provider}`;
    submit.addEventListener("click", evaluateQuiz);
    container.appendChild(submit);
  }

  async function evaluateQuiz(event) {
    if (!state.quizId) return setStatus("Generate a fresh quiz before submitting.", "error");
    const answers = state.quiz.map((_, index) => shadow.querySelector(`input[name='cg-question-${index}']:checked`)?.value || "");
    if (answers.some((answer) => !answer)) return setStatus("Answer every question before submitting.", "error");
    event.currentTarget.disabled = true;
    try {
      const result = await send("EVALUATE", {
        topic: topic(), quiz_id: state.quizId, given_answers: answers, current_mastery: state.mastery,
      });
      state.mastery = result.new_mastery;
      state.assessed = true;
      refreshHeader();
      result.evaluations.forEach((evaluation, index) => {
        const node = document.createElement("div");
        node.className = `result ${evaluation.is_correct ? "correct" : "wrong"}`;
        node.textContent = evaluation.is_correct ? `Correct · ${evaluation.explanation}` : `Review: ${evaluation.expected_answer} · ${evaluation.explanation}`;
        shadow.querySelectorAll(".quiz-item")[index]?.appendChild(node);
      });
      setStatus(`Score ${result.score}% · mastery is now ${result.new_mastery}%`, result.score >= 50 ? "ok" : "error");
    } catch (error) {
      setStatus(error.message, "error");
      event.currentTarget.disabled = false;
    }
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "CHAIGARAM_TOGGLE") {
      setOpen(!state.open);
      sendResponse({ ok: true });
    }
    if (message?.type === "CHAIGARAM_CAPTURE_SELECTION") {
      const selected = window.getSelection()?.toString().trim();
      if (selected) {
        if (sourceType() === "document") {
          state.pageContext = [learningPageText(), selected].filter(Boolean).join("\n\n").slice(0, MAX_CONTEXT_CHARS);
        }
        ingest(selected, "selection");
        setOpen(true);
        setStatus("Selected text added to this lesson.", "ok");
      }
      sendResponse({ ok: Boolean(selected) });
    }
    if (message?.type === "CHAIGARAM_CAPTURE_PAGE") {
      resetForNavigation();
      setOpen(true);
      switchTab("ask");
      if (sourceType() === "document") state.pageContext = learningPageText();
      setStatus("Reading this source and preparing your lesson...", "ok");
      summarizePage();
      sendResponse({ ok: true });
    }
  });

  buildOverlay();
  beginCapture();
})();
