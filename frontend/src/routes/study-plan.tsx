import { chartAxis } from "@/lib/chart-axis";
import { useState, useMemo } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceDot,
} from "recharts";
import {
  Calendar,
  CalendarCheck,
  CheckCircle2,
  Clock,
  ExternalLink,
  Layers,
  RefreshCw,
  Sparkles,
  TrendingDown,
} from "lucide-react";
import {
  studyEventsQuery,
  topicsQuery,
  STUDY_EVENT_META,
  retentionCurve,
  type StudyEvent,
  type Topic,
} from "@/lib/chaigaram";
import {
  Panel,
  PanelHeader,
  MasteryPill,
} from "@/components/chaigaram/primitives";
import { QuizGenerator } from "@/components/chaigaram/QuizGenerator";

export const Route = createFileRoute("/study-plan")({
  head: () => ({
    meta: [
      { title: "Study Plan | ChaiGaram" },
      {
        name: "description",
        content:
          "Spaced-repetition study schedule & Ebbinghaus retention decay curve",
      },
    ],
  }),
  component: StudyPlanScreen,
});

function StudyPlanScreen() {
  const {
    data: studyEvents = [],
    isLoading,
    error,
  } = useQuery(studyEventsQuery);
  const { data: topics = [] } = useQuery(topicsQuery);

  const [calendarView, setCalendarView] = useState<"week" | "month">("week");
  const [selectedTopicId, setSelectedTopicId] = useState<string>(
    topics[0]?.id || "",
  );
  const [activeDrillTopic, setActiveDrillTopic] = useState<string | null>(null);

  const selectedTopic = useMemo(() => {
    return (
      topics.find((t) => t.id === selectedTopicId) ||
      topics[0] || {
        id: "",
        title: "No indexed topic",
        mastery_score: 0,
        recall: undefined,
      }
    );
  }, [topics, selectedTopicId]);

  const visibleStudyEvents = useMemo(() => {
    const cutoff = Date.now() + (calendarView === "week" ? 7 : 31) * 86_400_000;
    return studyEvents.filter(
      (event) => new Date(event.scheduled_at).getTime() <= cutoff,
    );
  }, [calendarView, studyEvents]);

  // Forecast from completed assessments; scheduled reviews do not imply improvement.
  const retentionData = useMemo(() => {
    return selectedTopic.recall?.curve ?? [];
  }, [selectedTopic]);

  return (
    <div className="space-y-9">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">
            Spaced-Repetition Study Plan
          </h1>
          <p className="text-xs text-muted-foreground">
            Suggested reviews based on completed assessments and estimated
            recall.
          </p>
        </div>

        {/* Calendar View Toggle */}
        <div className="flex items-center gap-2">
          <div className="flex rounded-md border border-border bg-surface p-0.5 text-xs">
            <button
              onClick={() => setCalendarView("week")}
              className={`rounded px-3 py-1 font-medium transition ${
                calendarView === "week"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Week View
            </button>
            <button
              onClick={() => setCalendarView("month")}
              className={`rounded px-3 py-1 font-medium transition ${
                calendarView === "month"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Month View
            </button>
          </div>
        </div>
      </div>

      {/* Main Grid: Calendar Timeline (2 cols) & Retention Curve (1 col) */}
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-destructive/30 bg-destructive/8 p-4 text-xs text-destructive"
        >
          {error instanceof Error
            ? error.message
            : "Your study plan could not be loaded."}
        </div>
      )}
      {activeDrillTopic && (
        <Panel className="border-primary/40 p-5">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <p className="label-xs text-primary">Scheduled practice</p>
              <h2 className="text-base font-semibold">{activeDrillTopic}</h2>
            </div>
            <button
              onClick={() => setActiveDrillTopic(null)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Close
            </button>
          </div>
          <QuizGenerator
            topicTitle={activeDrillTopic}
            masteryScore={
              topics.find((topic) => topic.title === activeDrillTopic)
                ?.mastery_score ?? 0
            }
          />
        </Panel>
      )}
      <div className="grid grid-cols-1 gap-7 xl:grid-cols-3">
        {/* Calendar Events Timeline */}
        <Panel className="lg:col-span-2">
          <PanelHeader
            title="Scheduled Retrieval Events"
            subtitle="Color-coded: Review Reminders (Primary), Quiz Sessions (Accent), Deep Study Blocks (Warn)"
          />
          <div className="divide-y divide-border p-4">
            {isLoading &&
              [0, 1, 2].map((item) => (
                <div
                  key={item}
                  className="my-2 h-14 animate-pulse rounded-lg bg-surface-2"
                />
              ))}
            {!isLoading && visibleStudyEvents.length === 0 && (
              <div className="px-4 py-12 text-center">
                <Calendar className="mx-auto h-6 w-6 text-muted-foreground" />
                <p className="mt-3 text-sm font-semibold">
                  No scheduled reviews yet
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Capture a learning source to generate an adaptive review
                  schedule.
                </p>
              </div>
            )}
            {visibleStudyEvents.map((evt) => {
              const topicObj = topics.find((t) => t.id === evt.topic_id);
              const meta = STUDY_EVENT_META[evt.event_type] || {
                label: "Study Event",
                color: "text-primary",
                dot: "bg-primary",
              };
              const isCompleted = evt.status === "completed";
              const dateStr = new Date(evt.scheduled_at).toLocaleDateString(
                "en-US",
                {
                  weekday: "short",
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                },
              );

              return (
                <div
                  key={evt.id}
                  className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex items-center gap-3">
                    <div className={`h-2.5 w-2.5 rounded-full ${meta.dot}`} />
                    <div>
                      <div className="text-xs font-semibold text-foreground">
                        {topicObj?.title || "Topic Module"}{" "}
                        <span
                          className={`text-[11px] font-normal ${meta.color}`}
                        >
                          · {meta.label}
                        </span>
                      </div>
                      <div className="num text-[11px] text-muted-foreground">
                        {dateStr}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {isCompleted ? (
                      <span className="inline-flex items-center gap-1 rounded bg-positive/15 px-2 py-0.5 text-[10px] font-medium text-positive">
                        <CheckCircle2 className="h-3 w-3" /> Done
                      </span>
                    ) : (
                      <button
                        onClick={() =>
                          topicObj && setActiveDrillTopic(topicObj.title)
                        }
                        disabled={!topicObj}
                        className="inline-flex items-center gap-1.5 rounded bg-primary/12 px-2.5 py-1 text-[10px] font-semibold text-primary transition hover:bg-primary/20 disabled:opacity-40"
                      >
                        <Sparkles className="h-3 w-3" /> Start session
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>

        {/* Google Calendar Connection Card */}
        <div className="space-y-6">
          <Panel className="p-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="grid h-7 w-7 place-items-center rounded bg-primary/10 text-primary">
                  <CalendarCheck className="h-4 w-4" />
                </div>
                <h3 className="text-xs font-semibold text-foreground">
                  Calendar export
                </h3>
              </div>
              <button
                onClick={() => downloadCalendar(visibleStudyEvents, topics)}
                disabled={visibleStudyEvents.length === 0}
                className="num rounded-full bg-primary/12 px-2.5 py-1 text-[10px] font-semibold text-primary transition hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Download .ics
              </button>
            </div>

            <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
              Download the visible study schedule and open it with Google
              Calendar, Outlook, Apple Calendar, or another calendar app.
            </p>

            <div className="mt-4 border-t border-border pt-3 text-[11px] text-muted-foreground">
              <span className="num text-foreground">Current view:</span>{" "}
              {visibleStudyEvents.length} scheduled event
              {visibleStudyEvents.length === 1 ? "" : "s"}
            </div>
          </Panel>

          {/* Interactive Ebbinghaus Forgetting Curve */}
          <Panel className="p-5">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-foreground">
                Estimated Assessment Recall
              </h3>
              <select
                value={selectedTopicId || topics[0]?.id || ""}
                onChange={(e) => setSelectedTopicId(e.target.value)}
                className="max-w-[130px] truncate rounded border border-border bg-surface-2 px-2 py-1 text-[10px] text-foreground focus:border-primary"
              >
                {topics.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.title}
                  </option>
                ))}
              </select>
            </div>

            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
              {selectedTopic.recall?.method === "fitted_assessment_model"
                ? "Estimated from past assessment outcomes; predictive accuracy has not been independently validated."
                : selectedTopic.recall?.method === "cold_start_heuristic"
                  ? "A provisional decay estimate from your latest assessment. More completed quizzes are needed to fit a model."
                  : "Complete an assessment to see a recall estimate."}
            </p>

            <div className="mt-4 h-[180px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={retentionData}
                  margin={{ top: 5, right: 10, left: -20, bottom: 5 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="var(--border)"
                    opacity={0.5}
                  />
                  <XAxis
                    dataKey="day"
                    {...chartAxis}
                    tickFormatter={(d) => `D${d}`}
                  />
                  <YAxis
                    domain={[0, 100]}
                    {...chartAxis}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const d = payload[0]?.payload;
                      return (
                        <div className="rounded border border-border bg-popover p-2 text-[11px] shadow-md">
                          <p className="font-semibold">Day {d.day}</p>
                          <p className="num text-primary">
                            Estimated recall: {d.retention}%
                          </p>
                        </div>
                      );
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="retention"
                    stroke="var(--primary)"
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function downloadCalendar(events: StudyEvent[], topics: Topic[]) {
  if (!events.length) return;
  const formatUtc = (value: Date) =>
    value
      .toISOString()
      .replace(/[-:]/g, "")
      .replace(/\.\d{3}Z$/, "Z");
  const escape = (value: string) =>
    value
      .replace(/\\/g, "\\\\")
      .replace(/,/g, "\\,")
      .replace(/;/g, "\\;")
      .replace(/\n/g, "\\n");
  const now = formatUtc(new Date());
  const calendar = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//ChaiGaram//Study Plan//EN",
    "CALSCALE:GREGORIAN",
    ...events.flatMap((event) => {
      const start = new Date(event.scheduled_at);
      const end = new Date(start.getTime() + 30 * 60_000);
      const topic =
        topics.find((item) => item.id === event.topic_id)?.title ||
        "Learning topic";
      return [
        "BEGIN:VEVENT",
        `UID:${event.id}@chaigaram.local`,
        `DTSTAMP:${now}`,
        `DTSTART:${formatUtc(start)}`,
        `DTEND:${formatUtc(end)}`,
        `SUMMARY:${escape(`ChaiGaram: ${topic}`)}`,
        `DESCRIPTION:${escape(`${STUDY_EVENT_META[event.event_type]?.label || "Study session"} generated from your learning history.`)}`,
        "END:VEVENT",
      ];
    }),
    "END:VCALENDAR",
  ].join("\r\n");
  const href = URL.createObjectURL(
    new Blob([calendar], { type: "text/calendar;charset=utf-8" }),
  );
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = "chaigaram-study-plan.ics";
  anchor.click();
  URL.revokeObjectURL(href);
}
