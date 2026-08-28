(() => {
  const ROOT_ID = "chaigaram-extension-root";
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
    lastCaptureAt: Date.now(),
  };
  let host;
  let shadow;
  let captureTimer;

  const send = (type, payload) => new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type, payload }, (response) => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      if (!response?.ok) return reject(new Error(response?.error || "AI request failed"));
      resolve(response.data);
    });
  });

  function topic() {
    const candidates = [
      document.querySelector("h1")?.textContent,
      document.querySelector("[data-purpose='course-header-title']")?.textContent,
      document.querySelector("meta[property='og:title']")?.content,
      document.title,
    ];
    return candidates.find((value) => value?.trim())?.trim().slice(0, 300) || "Current lesson";
  }

  function learningPageText() {
    const root = document.querySelector("article, main, [role='main']") || document.body;
    const clone = root.cloneNode(true);
    clone.querySelectorAll("script, style, nav, footer, form, button, noscript, svg, aside, [aria-hidden='true']").forEach((node) => node.remove());
    const blocks = [...clone.querySelectorAll("h1, h2, h3, p, li, pre, blockquote, figcaption")]
      .map((node) => node.textContent?.replace(/\s+/g, " ").trim())
      .filter((text) => text && text.length > 20);
    return [...new Set(blocks)].join("\n").slice(0, 11000);
  }

  function activePageContext() {
    const page = state.pageContext || learningPageText();
    const captions = state.transcript.map((item) => `[${item.time}] ${item.text}`).join("\n");
    return [page, captions].filter(Boolean).join("\n\n").slice(0, 50000);
  }

  function timestamp() {
    const video = document.querySelector("video");
    const seconds = Math.max(0, Math.floor(video?.currentTime || 0));
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }

  async function ingest(text, source = "caption") {
    const clean = String(text || "").replace(/\s+/g, " ").trim();
    if (clean.length < 12 || clean === state.lastCaption) return;
    state.lastCaption = clean;
    const item = { text: clean, time: timestamp(), source };
    const now = Date.now();
    const dwellSeconds = Math.max(1, Math.round((now - state.lastCaptureAt) / 1000));
    state.lastCaptureAt = now;
    state.transcript.push(item);
    state.transcript = state.transcript.slice(-40);
    updateCaptureCount();
    try {
      const result = await send("INGEST", {
        video_title: document.title.slice(0, 300),
        timestamp: item.time,
        transcript_segment: clean,
        current_topic: topic(),
        dwell_seconds: dwellSeconds,
        page_url: location.href,
        video_position_seconds: Number(document.querySelector("video")?.currentTime || 0),
        video_duration_seconds: Number(document.querySelector("video")?.duration || 0),
      });
      setStatus(result.indexed ? `Captured ${result.words_captured} words` : "Caption already captured", "ok");
      await refreshTopicState();
    } catch (error) {
      setStatus(`Backend unavailable: ${error.message}`, "error");
    }
  }

  function scanCaptions() {
    const parts = [];
    for (const selector of CAPTION_SELECTORS) {
      document.querySelectorAll(selector).forEach((node) => {
        const value = node.textContent?.trim();
        if (value && !parts.includes(value)) parts.push(value);
      });
      if (parts.length) break;
    }
    if (parts.length) ingest(parts.join(" "));
  }

  function beginCapture() {
    chrome.storage.sync.get({ autoCapture: true }).then(({ autoCapture }) => {
      if (!autoCapture) return;
      const hasLearningMedia = () => Boolean(document.querySelector("video, audio, [class*='caption'], [class*='subtitle'], [class*='transcript']"));
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
    brandParts[0].textContent = "च";
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
    shadow.getElementById("ask").textContent = "Find it in my notes";
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
      const data = await send("ASK", {
        question,
        topic: topic(),
        transcript_context: activePageContext().slice(0, 12000),
        top_k: 5,
      });
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
    const context = activePageContext();
    if (context.length < 20) return setStatus("I could not find enough readable page or video text.", "error");
    button.disabled = true;
    button.textContent = "Building your lesson...";
    shadow.getElementById("answer").replaceChildren();
    try {
      const data = await send("SUMMARIZE", {
        topic: topic(),
        page_content: context,
        page_url: location.href,
      });
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
    try {
      const data = await send("QUIZ", {
        topic: topic(),
        source_context: activePageContext(),
        page_url: location.href,
        language: "English",
        mastery_score: state.mastery,
        quiz_perf_pct: state.quizPerf,
        time_on_section_pct: state.minutesOnSection,
        revisit_frequency_pct: state.revisits,
        recent_errors: [],
        question_count: 3,
      });
      state.quiz = data.questions;
      state.quizId = data.quiz_id;
      renderQuiz(data.questions, data.active_provider);
      setStatus(`Quiz generated by ${data.active_provider}.`, "ok");
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
        ingest(selected, "selection");
        setOpen(true);
        setStatus("Selected text added to this lesson.", "ok");
      }
      sendResponse({ ok: Boolean(selected) });
    }
    if (message?.type === "CHAIGARAM_CAPTURE_PAGE") {
      const text = learningPageText();
      if (text) {
        state.pageContext = text;
        setOpen(true);
        switchTab("ask");
        setStatus("Reading this page and preparing your lesson...", "ok");
        summarizePage();
      }
      sendResponse({ ok: Boolean(text) });
    }
  });

  buildOverlay();
  beginCapture();
})();
