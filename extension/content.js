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
    observation: null,
    trackedVideo: null,
    mediaElementSource: '',
    mediaCaptions: [],
    documentId: null,
    mediaSession: crypto.randomUUID(),
    sequence: 0,
    mediaSignature: '',
    scopedSequence: 0,
    scopedRevision: null,
    scopedEnabled: null,
    syncPromise: null,
    visibleCue: null,
    officialLoaded: false,
  };
  let host;
  let shadow;
  let captureTimer;
  let playerStateCleanup = null;
  let playerStateTimer = null;
  let learnerKeyPromise = null;

  function learnerKey() {
    if (!learnerKeyPromise) learnerKeyPromise = send('LEARNER_KEY');
    return learnerKeyPromise;
  }

  function schedulePlayerState(video) {
    clearTimeout(playerStateTimer);
    playerStateTimer = setTimeout(async () => {
      if (video !== state.trackedVideo) return;
      const playerState = document.hidden ? 'HIDDEN' : video.ended ? 'ENDED'
        : video.seeking ? 'SEEKING' : video.paused ? 'PAUSED' : 'PLAYING';
      const id = youtubeVideoId();
      if (!id) return;
      try {
        await send('PLAYER_STATE', {learner_key: await learnerKey(), video_key: `youtube:${id}`,
          state: playerState, media_time: video.currentTime, ts: Date.now()});
      } catch (_) { /* The local runtime may be offline. */ }
    }, 250);
  }

  function attachPlayerState(video) {
    playerStateCleanup?.();
    const events = ['play','playing','pause','seeking','seeked','ratechange','waiting','ended'];
    const update = event => {
      schedulePlayerState(video);
      if (['pause', 'ended', 'pagehide'].includes(event?.type) || document.hidden) {
        if (state.mediaCaptions.length) void syncMedia().catch(() => {});
      }
    };
    events.forEach(event => video.addEventListener?.(event, update));
    document.addEventListener?.('visibilitychange', update);
    globalThis.addEventListener?.('pagehide', update);
    playerStateCleanup = () => {
      events.forEach(event => video.removeEventListener?.(event, update));
      document.removeEventListener?.('visibilitychange', update);
      globalThis.removeEventListener?.('pagehide', update);
      clearTimeout(playerStateTimer);
    };
    update();
  }

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
    const key = `chaigaram-job:${state.pageKey}:${operation}`;
    const saved = (await chrome.storage.local.get(key))[key];
    const signature = JSON.stringify(payload);
    const request = saved?.signature === signature ? saved : { request_id: crypto.randomUUID(), signature };
    await chrome.storage.local.set({ [key]: request });
    const started = await send("JOB_START", { operation, payload, request_id: request.request_id });
    const deadline = Date.now() + 310000;
    let transientFailures = 0;
    while (Date.now() < deadline) {
      await pause(1400);
      try {
        const job = await send("JOB_STATUS", { job_id: started.job_id });
        transientFailures = 0;
        if (job.status === "succeeded") {
          await chrome.storage.local.remove(key);
          return job.result;
        }
        if (job.status === "failed") {
          await chrome.storage.local.remove(key);
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
    state.observation?.detach();
    playerStateCleanup?.(); playerStateCleanup = null;
    state.observation = null; state.trackedVideo = null;
    state.mediaElementSource = '';
    state.mediaCaptions = []; state.documentId = null;
    state.mediaSession = crypto.randomUUID(); state.sequence = 0;
    state.mediaSignature = ''; state.visibleCue = null; state.officialLoaded = false;
    state.scopedSequence = 0;
    state.scopedRevision = null;
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
      ensureObservation(video);
      return state.mediaCaptions.filter(cue => state.observation.tracker.covers(cue.start_ms, cue.end_ms))
        .map(cue => cue.text).join('\n').slice(-MAX_CONTEXT_CHARS);
    }
    return (state.pageContext || learningPageText()).slice(0, MAX_CONTEXT_CHARS);
  }

  async function sourceContext(action, minimumVideoWords = MIN_VIDEO_QUIZ_WORDS) {
    const pageKey = state.pageKey;
    if (activeVideo()) {
      ensureObservation(activeVideo());
      await loadYouTubeCaptionCues();
      collectNativeTextTrackCues(activeVideo());
      await syncMedia(true);
    }
    if (state.pageKey !== pageKey) throw new Error('The page changed. Please retry on this source.');
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
      documentId: state.documentId,
      observedUntilSeconds: (state.observation?.tracker.watermark || 0) / 1000,
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
    if (state.officialLoaded) return state.mediaCaptions.length;
    const tracks = [...(video.textTracks || [])];
    const track = tracks.find(t => t.language?.startsWith('en')) || tracks.find(t => t.cues?.length);
    if (!track?.cues?.length) return 0;
    state.mediaCaptions = [...track.cues].filter(c => c.endTime > c.startTime).map(c => ({
      start_ms: Math.floor(c.startTime * 1000), end_ms: Math.ceil(c.endTime * 1000),
      text: String(c.text).replace(/<[^>]+>/g, ' ').trim(),
    })).filter(c => c.text);
    return state.mediaCaptions.length;
  }

  function ensureObservation(video) {
    const source = video.currentSrc || video.src || '';
    if (state.trackedVideo === video && state.mediaElementSource === source) return;
    if (state.trackedVideo) {
      state.mediaCaptions = []; state.documentId = null; state.mediaSignature = '';
      state.mediaSession = crypto.randomUUID(); state.sequence = 0;
      state.scopedSequence = 0;
      state.scopedRevision = null;
      state.visibleCue = null; state.officialLoaded = false; state.lastCaption = '';
    }
    state.observation?.detach();
    state.trackedVideo = video;
    state.mediaElementSource = source;
    state.observation = ChaiObservation.attach(video, { allowed: () => !playerIsShowingAd() });
    attachPlayerState(video);
  }

  async function syncMedia(interactive = false) {
    if (state.syncPromise) { await state.syncPromise; if (interactive) return syncMedia(true); return; }
    const video = activeVideo();
    if (!video) return;
    ensureObservation(video);
    if (!state.mediaCaptions.length) return;
    const pageKey = state.pageKey;
    const observation = state.observation;
    const stillCurrent = () => state.pageKey === pageKey && state.observation === observation;
    const sync = async () => {
      const captions = state.mediaCaptions.slice(0, 20000);
      const signature = JSON.stringify(captions);
      const videoId = youtubeVideoId();
      if (videoId && state.scopedEnabled === null) {
        try { state.scopedEnabled = Boolean((await send('F1_STATUS')).enabled); }
        catch (_) { state.scopedEnabled = false; }
      }
      if (videoId && state.scopedEnabled) {
        const key = await learnerKey();
        const videoKey = `youtube:${videoId}`;
        if (signature !== state.mediaSignature) {
          const sealed = await runAI('seal', {learner_key: key, video_key: videoKey,
            cues: captions.map(cue => ({start: cue.start_ms / 1000, end: cue.end_ms / 1000, text: cue.text})),
            duration: Number.isFinite(video.duration) && video.duration > 0
              ? video.duration : Math.max(...captions.map(cue => cue.end_ms)) / 1000});
          if (!stillCurrent()) return;
          state.scopedSequence = Math.max(state.scopedSequence, sealed.last_batch_seq || 0);
          state.scopedRevision = sealed.revision;
          state.mediaSignature = signature;
        }
        const pending = observation.tracker.pending.splice(0, 10000);
        if (pending.length) {
          try {
            await send('F1_INTERVALS', {learner_key: key, video_key: videoKey,
              revision: state.scopedRevision, batch_seq: ++state.scopedSequence, intervals: pending});
          } catch (error) {
            observation.tracker.pending.unshift(...pending);
            throw error;
          }
        }
        return;
      }
      // The legacy API sends the merged ledger, so raw frame batches are unnecessary.
      if (observation.tracker.pending) observation.tracker.pending.length = 0;
      if (signature !== state.mediaSignature) {
        const result = await send('TRANSCRIPT', { source_url: pageKey, topic: topic(), captions });
        if (!stillCurrent()) return;
        state.documentId = result.document_id;
        state.mediaSession = crypto.randomUUID(); state.sequence = 0;
        state.mediaSignature = signature;
      }
      if (!state.documentId || !stillCurrent()) return;
      const documentId = state.documentId;
      await send('OBSERVE', { document_id: documentId, media_session_id: state.mediaSession,
        event_sequence: ++state.sequence, evidence: observation.evidence,
        observed_intervals: observation.tracker.intervals.map(([start_ms, end_ms]) => ({start_ms, end_ms})) });
      if (!stillCurrent()) return;
      const idle = interactive || video.paused || video.readyState < 3 || document.hidden;
      if (idle) {
        const deadline = Date.now() + 130000;
        do {
          if (!stillCurrent()) return;
          const job = await send('SPECULATE', { document_id: documentId,
            position_ms: Math.floor(video.currentTime * 1000), idle, observed_only: interactive,
            budget_ms: interactive ? 10000 : 2000 });
          if (!interactive) return;
          if (!job.job_id) {
            if (job.pending_chunks) throw new Error('Caption indexing is busy. Please retry shortly.');
            return;
          }
          while (Date.now() < deadline) {
            if (!stillCurrent()) return;
            const status = await send('JOB_STATUS', {job_id: job.job_id});
            if (status.status === 'succeeded') break;
            if (status.status === 'failed') throw new Error(status.error);
            await pause(1000);
          }
        } while (Date.now() < deadline);
        throw new Error('Caption indexing is still running. Please retry shortly.');
      }
    };
    state.syncPromise = sync();
    try { await state.syncPromise; } finally { state.syncPromise = null; }
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
    const captions = [];
    let stored = 0;
    for (const event of payload.events || []) {
      if (state.pageKey !== pageKey) return 0;
      if (!Array.isArray(event.segs)) continue;
      const startSeconds = Number(event.tStartMs || 0) / 1000;

      const text = event.segs.map((segment) => segment.utf8 || "").join("");
      if (!text.trim() || text.trim() === "\n") continue;
      if (!(event.dDurationMs > 0)) continue;
      captions.push({start_ms: Math.floor(startSeconds * 1000),
        end_ms: Math.ceil(startSeconds * 1000 + event.dDurationMs), text: text.trim()});
      stored += 1;
    }
    if (captions.length && state.pageKey === pageKey) {
      state.mediaCaptions = captions; state.officialLoaded = true;
    }
    return stored;
  }

  async function loadYouTubeCaptionCues() {
    if (!youtubeVideoId() || state.officialLoaded) return 0;
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
    if (video) {
      if (state.officialLoaded) return;
      ensureObservation(video);
      const pos = Math.floor(video.currentTime * 1000);
      const previous = state.visibleCue;
      if (previous && pos > previous.start_ms && pos - previous.start_ms < 15000 &&
          state.observation.tracker.covers(previous.start_ms, pos)) {
        state.mediaCaptions.push({...previous, end_ms: pos});
      }
      state.visibleCue = {text: clean, start_ms: pos};
      return;
    }
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
      const result = await send("DOCUMENT", {
        title: document.title.slice(0, 300), topic: topic(), content: clean, course: document.title.slice(0,300),
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
    ensureObservation(video);
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
      // Attach frame observation promptly; the slower transcript sync must not
      // miss the first seconds of a newly started video.
      setInterval(() => {
        const video = activeVideo();
        if (video) ensureObservation(video);
      }, 500);
      setInterval(async () => {
        resetForNavigation();
        if (!hasLearningMedia()) return;
        try {
          ensureObservation(activeVideo());
          await loadYouTubeCaptionCues();
          collectNativeTextTrackCues(activeVideo());
          await syncMedia();
        } catch (error) { setStatus(`Capture sync failed: ${error.message}`, 'error'); }
      }, 5000);
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
    button, textarea { font:inherit; }
    button { -webkit-tap-highlight-color:transparent; }
    svg { width:16px; height:16px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
    .panel { position:fixed; z-index:2147483647; top:18px; right:18px; width:420px; max-height:calc(100vh - 36px); overflow:hidden; color:#f5f5f7; background:radial-gradient(circle at 80% -10%,rgb(41 151 255 / 12%),transparent 35%),#000; border:1px solid #2d2d2f; border-radius:22px; box-shadow:0 28px 90px -28px rgb(0 0 0 / 95%),0 0 0 1px rgb(255 255 255 / 2%); font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; -webkit-font-smoothing:antialiased; }
    .panel.hidden { display:none; } .panel.min .body { display:none; }
    header { display:grid; grid-template-columns:34px 1fr auto; align-items:center; gap:10px; min-height:62px; padding:10px 12px; border-bottom:1px solid #2d2d2f; background:rgb(11 11 12 / 88%); backdrop-filter:blur(18px); }
    .brand { display:flex; align-items:center; gap:9px; min-width:0; }
    .mark { display:grid; place-items:center; width:32px; height:32px; flex:none; border-radius:10px; color:#000; background:#f5f5f7; font-size:9px; font-weight:800; }
    .brand-copy { display:grid; min-width:0; }
    .brand-name { font-size:13px; font-weight:750; letter-spacing:-.035em; }
    .live { display:flex; align-items:center; gap:5px; color:#86868b; font:700 8px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; letter-spacing:.09em; text-transform:uppercase; }
    .live::before { content:""; width:6px; height:6px; border-radius:50%; background:#30d158; box-shadow:0 0 0 3px rgb(48 209 88 / 10%); }
    .header-actions { display:flex; align-items:center; gap:6px; }
    .icon { display:grid; width:32px; height:32px; place-items:center; padding:0; border:1px solid #2d2d2f; border-radius:50%; color:#86868b; background:#161617; cursor:pointer; transition:160ms ease; }
    .icon:hover { border-color:#424245; color:#f5f5f7; background:#222224; }
    .body { display:grid; gap:12px; max-height:calc(100vh - 99px); overflow:auto; padding:14px; scrollbar-width:thin; scrollbar-color:#424245 transparent; }
    .source-card { padding:14px; border:1px solid #2d2d2f; border-radius:15px; background:linear-gradient(145deg,#1c1c1e,#161617); }
    .source-label { color:#2997ff; font:700 8px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; letter-spacing:.13em; text-transform:uppercase; }
    .lesson { margin-top:6px; overflow:hidden; color:#f5f5f7; font-size:13px; font-weight:700; letter-spacing:-.025em; text-overflow:ellipsis; white-space:nowrap; }
    .meterline { display:flex; align-items:center; justify-content:space-between; margin-top:13px; padding-top:12px; border-top:1px solid #2d2d2f; color:#86868b; font-size:10px; }
    .meterline strong { color:#f5f5f7; font:700 10px ui-monospace,SFMono-Regular,Menlo,monospace; }
    .meter { height:5px; margin-top:8px; overflow:hidden; border-radius:999px; background:#2d2d2f; } .meter span { display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,#0071e3,#2997ff); transition:width 300ms ease; }
    .tabs { display:grid; grid-template-columns:1fr 1fr; gap:3px; padding:3px; border:1px solid #2d2d2f; border-radius:12px; background:#161617; }
    .tab { min-height:35px; padding:7px; border:0; border-radius:9px; color:#86868b; background:transparent; font-size:10px; font-weight:700; cursor:pointer; transition:160ms ease; } .tab:hover { color:#f5f5f7; } .tab.active { color:#f5f5f7; background:#2a2a2c; box-shadow:inset 0 0 0 1px rgb(255 255 255 / 4%); }
    .workspace { padding:14px; border:1px solid #2d2d2f; border-radius:15px; background:#161617; }
    .feature { display:flex; width:100%; align-items:center; justify-content:space-between; gap:10px; padding:12px 13px; border:1px solid rgb(41 151 255 / 30%); border-radius:11px; color:#d8ecff; background:rgb(41 151 255 / 8%); font-size:10px; font-weight:700; text-align:left; cursor:pointer; transition:160ms ease; }
    .feature:hover { border-color:rgb(41 151 255 / 55%); background:rgb(41 151 255 / 13%); }
    .feature small { display:block; margin-top:2px; color:#86868b; font-size:8px; font-weight:500; }
    .input-label { display:block; margin:14px 0 6px; color:#86868b; font:700 8px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; letter-spacing:.1em; text-transform:uppercase; }
    textarea { width:100%; min-height:92px; resize:vertical; padding:11px 12px; border:1px solid #424245; border-radius:10px; outline:none; color:#f5f5f7; background:#0b0b0c; font-size:11px; line-height:1.55; transition:160ms ease; } textarea::placeholder { color:#636366; } textarea:focus { border-color:#2997ff; box-shadow:0 0 0 3px rgb(41 151 255 / 10%); }
    .primary { display:flex; width:100%; min-height:40px; align-items:center; justify-content:center; gap:7px; margin-top:9px; padding:9px 12px; border:0; border-radius:10px; color:#fff; background:#2997ff; font-size:10px; font-weight:750; cursor:pointer; transition:160ms ease; } .primary:hover { filter:brightness(1.08); transform:translateY(-1px); } .primary:disabled,.feature:disabled { opacity:.5; cursor:wait; transform:none; }
    .answer { margin-top:12px; padding:13px; border:1px solid #2d2d2f; border-radius:11px; color:#d1d1d6; background:#0b0b0c; font-size:11px; line-height:1.65; white-space:pre-wrap; }
    .sources { margin-top:9px; color:#86868b; font:9px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; } .source { margin-top:6px; padding:7px 9px; border-left:2px solid #2997ff; border-radius:0 6px 6px 0; background:rgb(41 151 255 / 5%); }
    .status { padding:10px 11px; border:1px solid #2d2d2f; border-radius:10px; color:#86868b; background:#0b0b0c; font:9px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; } .status::before { content:""; display:inline-block; width:6px; height:6px; margin-right:7px; border-radius:50%; background:#8e8e93; } .status.ok { color:#72dd8a; border-color:rgb(48 209 88 / 22%); } .status.ok::before { background:#30d158; } .status.error { color:#ff8a83; border-color:rgb(255 69 58 / 25%); } .status.error::before { background:#ff453a; }
    .quiz-item { margin-top:11px; padding:13px; border:1px solid #2d2d2f; border-radius:12px; background:#0b0b0c; } .question { margin:0 0 10px; color:#f5f5f7; font-size:11px; font-weight:700; line-height:1.5; }
    .choice { display:flex; align-items:flex-start; gap:8px; margin-top:7px; padding:9px 10px; border:1px solid #2d2d2f; border-radius:9px; color:#c7c7cc; background:#161617; font-size:10px; cursor:pointer; transition:140ms ease; } .choice:hover { border-color:#424245; color:#f5f5f7; background:#222224; } .choice input { margin-top:2px; accent-color:#2997ff; }
    .result { margin-top:9px; padding:9px 10px; border-radius:8px; background:#161617; font-size:10px; } .correct { color:#72dd8a; border:1px solid rgb(48 209 88 / 25%); } .wrong { color:#ff8a83; border:1px solid rgb(255 69 58 / 25%); }
    [hidden] { display:none !important; }
    :focus-visible { outline:2px solid #2997ff; outline-offset:2px; }
    @media (max-width:520px) { .panel { top:8px; right:8px; left:8px; width:auto; max-height:calc(100vh - 16px); border-radius:18px; } .body { max-height:calc(100vh - 79px); } }
  `;

  function buildOverlay() {
    if (host) return;
    host = document.createElement("div");
    host.id = ROOT_ID;
    shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>${styles}</style>
      <aside class="panel hidden" aria-label="ChaiGaram learning assistant">
        <header>
          <button class="icon" id="back" title="Go back to the previous webpage" aria-label="Go back"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg></button>
          <div class="brand"><span class="mark">CG</span><span class="brand-copy"><span class="brand-name">ChaiGaram</span><span class="live">On this page</span></span></div>
          <div class="header-actions"><button class="icon" id="min" title="Minimize" aria-label="Minimize">&minus;</button><button class="icon" id="close" title="Close" aria-label="Close">&times;</button></div>
        </header>
        <div class="body">
          <section class="source-card"><div class="source-label">Current learning source</div><div class="lesson" id="lesson"></div><div class="meterline"><span>What has actually stuck</span><strong id="mastery">Not tested yet</strong></div><div class="meter"><span id="meter" style="width:0%"></span></div></section>
          <div class="tabs"><button class="tab active" data-tab="ask">Ask tutor</button><button class="tab" data-tab="quiz">Adaptive quiz</button></div>
          <section class="workspace">
            <div id="askPane"><button class="feature" id="summarize"><span>Teach me this page<small>Get a structured lesson and concise summary</small></span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg></button><label class="input-label" for="question">Ask a follow-up</label><textarea id="question" placeholder="Ask anything about this page, video, article, or saved selection..."></textarea><button class="primary" id="ask">Ask about this page</button><div id="answer"></div></div>
            <div id="quizPane" hidden><button class="primary" id="generate">Make an English quiz from this page</button><div id="quiz"></div></div>
          </section>
          <div class="status" id="status">Ready for captions, page text, or a selection · <span id="count">0</span> saved</div>
        </div>
      </aside>`;
    const tabs = shadow.querySelectorAll(".tab");
    tabs[0].textContent = "Ask the page";
    tabs[1].textContent = "Test me";
    document.documentElement.appendChild(host);

    shadow.getElementById("back").addEventListener("click", () => window.history.back());
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
        transcript_context: context.kind === "video" ? null : context.text,
        source_type: context.kind,
        document_id: context.kind === "video" ? context.documentId : null,
        learner_key: context.kind === 'video' && youtubeVideoId() && state.scopedEnabled ? await learnerKey() : null,
        video_key: context.kind === 'video' && youtubeVideoId() && state.scopedEnabled ? `youtube:${youtubeVideoId()}` : null,
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

  function setSummarizeButton(title, subtitle) {
    const label = shadow.getElementById("summarize").querySelector(":scope > span");
    if (!label) return;
    label.firstChild.nodeValue = title;
    label.querySelector("small").textContent = subtitle;
  }

  async function summarizePage() {
    const button = shadow.getElementById("summarize");
    button.disabled = true;
    setSummarizeButton("Building your lesson...", "Reading only the current page or watched video");
    shadow.getElementById("answer").replaceChildren();
    try {
      const context = await sourceContext("building a lesson", 20);
      const requestPageKey = state.pageKey;
      setStatus(
        context.kind === "video"
          ? `Teaching only from ${context.wordCount} caption words from observed intervals.`
          : `Teaching only from the current document (${context.wordCount} words).`,
        "ok",
      );
      const data = await runAI("summarize", {
        topic: topic(),
        page_content: context.kind === "video" ? "" : context.text,
        page_url: location.href,
        source_type: context.kind,
        document_id: context.kind === "video" ? context.documentId : null,
        learner_key: context.kind === 'video' && youtubeVideoId() && state.scopedEnabled ? await learnerKey() : null,
        video_key: context.kind === 'video' && youtubeVideoId() && state.scopedEnabled ? `youtube:${youtubeVideoId()}` : null,
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
      setSummarizeButton("Teach me this page again", "Refresh the lesson from the latest page context");
    }
  }

  async function generateQuiz() {
    if (state.quizId) {
      try { await send('ABANDON', { quiz_id: state.quizId }); } catch (_) { /* expiry remains a backstop */ }
    }
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
        ? `${context.wordCount} caption words from observed intervals`
        : `${context.wordCount} words from this document`;
      setStatus(`Generating an English quiz from ${scopeMessage} only.`, "ok");
      const data = await runAI("quiz", {
        topic: topic(),
        source_context: context.kind === "video" ? null : context.text,
        page_url: location.href,
        language: "English",
        source_type: context.kind,
        document_id: context.kind === "video" ? context.documentId : null,
        learner_key: context.kind === 'video' && youtubeVideoId() && state.scopedEnabled ? await learnerKey() : null,
        video_key: context.kind === 'video' && youtubeVideoId() && state.scopedEnabled ? `youtube:${youtubeVideoId()}` : null,
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
