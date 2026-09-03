import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouterState } from "@tanstack/react-router";
import {
  Bot,
  ChevronDown,
  GraduationCap,
  MessageCircle,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  UserRound,
} from "lucide-react";

import { useAuth } from "@/components/auth/AuthProvider";
import { askRAGAssistant } from "@/lib/ai-client";
import { coursesQuery, recommendationsQuery, topicsQuery } from "@/lib/queries";
import { cn } from "@/lib/utils";

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
  sources?: string[];
  error?: boolean;
  retryQuestion?: string;
};

const STORAGE_KEY = "chaigaram-assistant-messages";

const STARTERS = [
  "What can you help me with?",
  "What should I study next?",
  "Show my learning progress",
];

const PAGE_NAMES: Record<string, string> = {
  "/": "Overview",
  "/courses": "Courses",
  "/mastery": "Mastery",
  "/quizzes": "Practice",
  "/study-plan": "Study plan",
  "/recommendations": "Recommendations",
  "/history": "History",
  "/simulator": "Extension",
  "/profile": "Profile",
  "/settings": "Settings",
};

function messageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function compactSource(source: string) {
  return source.length > 28 ? `${source.slice(0, 27)}…` : source;
}

export function PersonalChatbot() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const activeRequestRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const { user, profile } = useAuth();
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  });
  const { data: topics = [] } = useQuery(topicsQuery);
  const { data: courses = [] } = useQuery(coursesQuery);
  const { data: recommendations = [] } = useQuery(recommendationsQuery);

  const firstName = useMemo(
    () =>
      (profile?.displayName || user?.displayName || "")
        .trim()
        .split(/\s+/)[0] || "there",
    [profile?.displayName, user?.displayName],
  );

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed: unknown = JSON.parse(saved);
        if (Array.isArray(parsed)) setMessages(parsed as ChatMessage[]);
      }
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    if (!messages.length) return;
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(messages.slice(-30)),
    );
  }, [messages]);

  useEffect(() => {
    if (!open) return;
    window.setTimeout(() => inputRef.current?.focus(), 180);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, thinking, open]);

  useEffect(
    () => () => {
      activeRequestRef.current?.abort();
    },
    [],
  );

  const welcome = `Hi ${firstName} — I’m your ChaiGaram learning assistant. I can explain your saved lessons, review your progress, and help you decide what to study next.`;

  function localAnswer(question: string): string | null {
    const normal = question.toLowerCase();

    if (/^(hi|hello|hey|hiya|howdy)(\s|[!,.?]|$)/.test(normal)) {
      if (/how are you|how'?s it going|what'?s up/.test(normal)) {
        return `I’m doing well, ${firstName} — thanks for asking! What are you learning today?`;
      }
      return `Hi ${firstName}! What would you like to learn or work through today?`;
    }

    if (/^(how are you|how'?s it going|what'?s up)(\s|[!,.?]|$)/.test(normal)) {
      return `I’m doing well, ${firstName} — thanks for asking! What are you learning today?`;
    }

    if (/^(thanks|thank you|thx)(\s|[!,.?]|$)/.test(normal)) {
      return "You’re welcome! Send me the next question whenever you’re ready.";
    }

    if (/^(bye|goodbye|see you)(\s|[!,.?]|$)/.test(normal)) {
      return "See you soon! Your learning progress will be here when you come back.";
    }

    if (/what can you|how can you|what do you do|help me/.test(normal)) {
      return "I can answer questions from your indexed lessons, explain difficult ideas, summarize your learning progress, recommend what to study next, and guide you around ChaiGaram. Ask naturally — for example, “Explain the hardest topic in simple words.”";
    }

    if (/where am i|this page|current page/.test(normal)) {
      const page =
        Object.entries(PAGE_NAMES).find(([path]) =>
          path === "/" ? pathname === "/" : pathname.startsWith(path),
        )?.[1] ?? "ChaiGaram";
      return `You’re on the ${page} page. Ask me about anything you see here, or about one of your saved lessons.`;
    }

    if (/progress|how am i doing|mastery|performance/.test(normal)) {
      if (!topics.length) {
        return "You don’t have enough learning data yet. Capture a lesson with the extension, then complete a quiz so I can track your mastery and progress.";
      }
      const average = Math.round(
        topics.reduce((sum, topic) => sum + topic.mastery_score, 0) /
          topics.length,
      );
      const strongest = [...topics].sort(
        (a, b) => b.mastery_score - a.mastery_score,
      )[0];
      if (!strongest) {
        return "I don’t have enough topic data to calculate your progress yet.";
      }
      return `You have ${topics.length} tracked topic${topics.length === 1 ? "" : "s"} across ${courses.length} course${courses.length === 1 ? "" : "s"}, with ${average}% average mastery. Your strongest topic right now is ${strongest.title} at ${Math.round(strongest.mastery_score)}%.`;
    }

    if (/study next|recommend|focus|weakest|improve/.test(normal)) {
      const recommendation = [...recommendations].sort(
        (a, b) => b.impact_score - a.impact_score,
      )[0];
      const weakest = [...topics].sort(
        (a, b) => a.mastery_score - b.mastery_score,
      )[0];
      if (recommendation) {
        return `Your highest-impact next step is a ${recommendation.estimated_minutes}-minute ${recommendation.type.replaceAll("_", " ")} session. ${recommendation.reasoning}`;
      }
      if (weakest) {
        return `Start with ${weakest.title}, currently at ${Math.round(weakest.mastery_score)}% mastery. Review its saved material, then take a short practice quiz to check what stuck.`;
      }
      return "First, capture a lesson or article with the ChaiGaram extension. Once it’s indexed, I can recommend exactly what to review and create grounded practice from it.";
    }

    return null;
  }

  async function sendMessage(raw: string) {
    const question = raw.trim();
    if (!question || thinking) return;

    const history = messages
      .filter((message) => !message.error)
      .slice(-12)
      .map((message) => ({ role: message.role, content: message.text }));
    setMessages((current) => [
      ...current,
      { id: messageId(), role: "user", text: question },
    ]);
    setInput("");
    setThinking(true);
    const requestId = ++requestIdRef.current;

    try {
      const instant = localAnswer(question);
      if (instant) {
        await new Promise((resolve) => window.setTimeout(resolve, 350));
        if (requestId !== requestIdRef.current) return;
        setMessages((current) => [
          ...current,
          { id: messageId(), role: "assistant", text: instant },
        ]);
        return;
      }

      const controller = new AbortController();
      activeRequestRef.current = controller;
      const timeout = window.setTimeout(() => controller.abort(), 60_000);
      let result: Awaited<ReturnType<typeof askRAGAssistant>>;
      try {
        result = await askRAGAssistant({
          question,
          topK: 5,
          history,
          signal: controller.signal,
        });
      } finally {
        window.clearTimeout(timeout);
      }
      if (requestId !== requestIdRef.current) return;
      const sources = Array.from(
        new Set(
          result.sources.map(
            (source) => source.course || source.topic || source.chunk_id,
          ),
        ),
      ).slice(0, 3);
      setMessages((current) => [
        ...current,
        {
          id: messageId(),
          role: "assistant",
          text: result.answer,
          sources,
        },
      ]);
    } catch (reason) {
      if (requestId !== requestIdRef.current) return;
      const stopped =
        reason instanceof DOMException && reason.name === "AbortError";
      const detail = stopped
        ? "I stopped that response."
        : reason instanceof Error
          ? reason.message
          : "I couldn’t answer that.";
      setMessages((current) => [
        ...current,
        {
          id: messageId(),
          role: "assistant",
          text: stopped
            ? detail
            : `${detail} You can retry, or ask in a different way.`,
          error: true,
          retryQuestion: question,
        },
      ]);
    } finally {
      if (requestId === requestIdRef.current) {
        activeRequestRef.current = null;
        setThinking(false);
      }
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void sendMessage(input);
  }

  function clearChat() {
    requestIdRef.current += 1;
    activeRequestRef.current?.abort();
    activeRequestRef.current = null;
    setThinking(false);
    setMessages([]);
    window.localStorage.removeItem(STORAGE_KEY);
    inputRef.current?.focus();
  }

  function stopResponse() {
    activeRequestRef.current?.abort();
  }

  function handleComposerKeyDown(
    event: ReactKeyboardEvent<HTMLTextAreaElement>,
  ) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (input.trim() && !thinking) void sendMessage(input);
    }
  }

  return (
    <aside
      className="fixed bottom-4 right-4 z-[70] sm:bottom-6 sm:right-6"
      aria-label="Personal learning assistant"
    >
      <section
        className={cn(
          "absolute bottom-[76px] right-0 flex h-[min(620px,calc(100vh-112px))] w-[min(390px,calc(100vw-32px))] origin-bottom-right flex-col overflow-hidden rounded-[26px] border border-border bg-background/95 shadow-float backdrop-blur-2xl transition duration-200",
          open
            ? "pointer-events-auto translate-y-0 scale-100 opacity-100"
            : "pointer-events-none translate-y-3 scale-95 opacity-0",
        )}
        aria-hidden={!open}
        inert={!open}
      >
        <header className="flex items-center gap-3 border-b border-border px-4 py-3.5">
          <span className="relative grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground shadow-lg shadow-primary/20">
            <GraduationCap className="h-5 w-5" />
            <span className="absolute bottom-0 right-0 h-3 w-3 rounded-full border-2 border-background bg-positive" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <h2 className="truncate text-sm font-semibold tracking-tight">
                Chai, your study buddy
              </h2>
              <Sparkles className="h-3.5 w-3.5 text-primary" />
            </div>
            <p className="mt-0.5 text-[10px] font-medium text-positive">
              Online · grounded in your lessons
            </p>
          </div>
          <button
            onClick={clearChat}
            className="grid h-8 w-8 place-items-center rounded-full text-muted-foreground transition hover:bg-surface-2 hover:text-foreground"
            title="Start a new chat"
            aria-label="Start a new chat"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setOpen(false)}
            className="grid h-8 w-8 place-items-center rounded-full text-muted-foreground transition hover:bg-surface-2 hover:text-foreground"
            aria-label="Minimize assistant"
          >
            <ChevronDown className="h-4 w-4" />
          </button>
        </header>

        <div
          ref={scrollRef}
          className="min-h-0 flex-1 overflow-y-auto px-4 py-5"
          aria-live="polite"
        >
          <div className="mb-5 flex items-start gap-2.5">
            <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary/12 text-primary">
              <Bot className="h-3.5 w-3.5" />
            </span>
            <p className="max-w-[285px] rounded-2xl rounded-tl-md bg-surface-2 px-3.5 py-2.5 text-[13px] leading-relaxed text-foreground">
              {welcome}
            </p>
          </div>

          {!messages.length && (
            <div className="ml-9 space-y-2">
              {STARTERS.map((starter) => (
                <button
                  key={starter}
                  onClick={() => void sendMessage(starter)}
                  className="block w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-left text-[12px] font-medium text-muted-foreground transition hover:border-primary/40 hover:text-foreground"
                >
                  {starter}
                </button>
              ))}
            </div>
          )}

          <div className="space-y-4">
            {messages.map((message) => (
              <div
                key={message.id}
                className={cn(
                  "flex items-start gap-2.5",
                  message.role === "user" && "flex-row-reverse",
                )}
              >
                <span
                  className={cn(
                    "mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full",
                    message.role === "assistant"
                      ? "bg-primary/12 text-primary"
                      : "bg-surface-2 text-muted-foreground",
                  )}
                >
                  {message.role === "assistant" ? (
                    <Bot className="h-3.5 w-3.5" />
                  ) : (
                    <UserRound className="h-3.5 w-3.5" />
                  )}
                </span>
                <div
                  className={cn(
                    "max-w-[285px]",
                    message.role === "user" && "text-right",
                  )}
                >
                  <p
                    className={cn(
                      "inline-block whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-left text-[13px] leading-relaxed",
                      message.role === "assistant"
                        ? message.error
                          ? "rounded-tl-md border border-destructive/30 bg-destructive/8 text-foreground"
                          : "rounded-tl-md bg-surface-2 text-foreground"
                        : "rounded-tr-md bg-primary text-primary-foreground",
                    )}
                  >
                    {message.text}
                  </p>
                  {message.retryQuestion && (
                    <button
                      type="button"
                      onClick={() => void sendMessage(message.retryQuestion!)}
                      disabled={thinking}
                      className="mt-1.5 block rounded-lg px-2 py-1 text-[10px] font-semibold text-primary transition hover:bg-primary/10 disabled:opacity-40"
                    >
                      Retry response
                    </button>
                  )}
                  {!!message.sources?.length && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {message.sources.map((source) => (
                        <span
                          key={source}
                          className="rounded-full border border-border px-2 py-0.5 text-[9px] text-muted-foreground"
                        >
                          {compactSource(source)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {thinking && (
              <div className="flex items-center gap-2.5">
                <span className="grid h-7 w-7 place-items-center rounded-full bg-primary/12 text-primary">
                  <Bot className="h-3.5 w-3.5" />
                </span>
                <span
                  className="flex gap-1 rounded-2xl rounded-tl-md bg-surface-2 px-4 py-3"
                  aria-label="Assistant is thinking"
                >
                  {[0, 1, 2].map((dot) => (
                    <i
                      key={dot}
                      className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground"
                      style={{ animationDelay: `${dot * 120}ms` }}
                    />
                  ))}
                </span>
                <span className="self-center text-[10px] text-muted-foreground">
                  Thinking…
                </span>
              </div>
            )}
          </div>
        </div>

        <form
          onSubmit={submit}
          className="border-t border-border bg-surface/45 p-3"
        >
          <div className="flex items-center gap-2 rounded-2xl border border-border bg-background px-3 py-2 transition focus-within:border-primary/60 focus-within:ring-2 focus-within:ring-primary/10">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              rows={1}
              maxLength={2000}
              placeholder={thinking ? "Chai is answering…" : "Message Chai…"}
              className="max-h-24 min-h-8 min-w-0 flex-1 resize-none bg-transparent px-1 py-1.5 text-[13px] leading-5 outline-none placeholder:text-muted-foreground"
              aria-label="Message Chai"
            />
            {thinking ? (
              <button
                type="button"
                onClick={stopResponse}
                className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-foreground text-background transition hover:opacity-80"
                aria-label="Stop response"
                title="Stop response"
              >
                <Square className="h-3 w-3 fill-current" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!input.trim()}
                className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-35"
                aria-label="Send message"
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <p className="mt-2 text-center text-[9px] text-muted-foreground">
            Chai can chat generally and uses your saved lessons when relevant.
          </p>
        </form>
      </section>

      {!open && (
        <span className="pointer-events-none absolute -left-32 top-2 hidden rounded-full border border-border bg-background/90 px-3 py-2 text-[11px] font-medium text-foreground opacity-0 shadow-panel transition group-hover:opacity-100 sm:block">
          Ask your study buddy
        </span>
      )}
      <button
        onClick={() => setOpen((current) => !current)}
        className={cn(
          "group relative grid h-16 w-16 place-items-center rounded-full border border-white/15 bg-primary text-primary-foreground shadow-[0_14px_40px_-10px_color-mix(in_srgb,var(--primary)_70%,transparent)] transition duration-200 hover:-translate-y-1 hover:scale-105 focus:outline-none focus-visible:ring-4 focus-visible:ring-primary/30",
          open && "rotate-3 scale-95",
        )}
        aria-label={
          open ? "Close personal assistant" : "Open personal assistant"
        }
        aria-expanded={open}
      >
        <span className="absolute inset-0 rounded-full bg-white/10 opacity-0 transition group-hover:opacity-100" />
        {open ? (
          <ChevronDown className="h-6 w-6" />
        ) : (
          <MessageCircle className="h-6 w-6" />
        )}
        {!open && (
          <span className="absolute right-0 top-0 h-4 w-4 rounded-full border-[3px] border-background bg-positive" />
        )}
      </button>
    </aside>
  );
}
