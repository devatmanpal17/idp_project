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
import { studyEventsQuery, topicsQuery, STUDY_EVENT_META, retentionCurve } from "@/lib/chaigaram";
import { Panel, PanelHeader, MasteryPill, chartAxis } from "@/components/chaigaram/primitives";

export const Route = createFileRoute("/study-plan")({
  head: () => ({
    meta: [
      { title: "Study Plan | ChaiGaram" },
      {
        name: "description",
        content: "Spaced-repetition study schedule & Ebbinghaus retention decay curve",
      },
    ],
  }),
  component: StudyPlanScreen,
});

function StudyPlanScreen() {
  const { data: studyEvents = [] } = useQuery(studyEventsQuery);
  const { data: topics = [] } = useQuery(topicsQuery);

  const [calendarView, setCalendarView] = useState<"week" | "month">("week");
  const [selectedTopicId, setSelectedTopicId] = useState<string>(topics[0]?.id || "");
  const [googleCalendarConnected, setGoogleCalendarConnected] = useState(true);

  const selectedTopic = useMemo(() => {
    return (
      topics.find((t) => t.id === selectedTopicId) ||
      topics[0] || {
        title: "Support Vector Machines",
        mastery_score: 41,
      }
    );
  }, [topics, selectedTopicId]);

  // Compute Ebbinghaus retention decay curve data
  const retentionData = useMemo(() => {
    const score = Number(selectedTopic.mastery_score) || 45;
    // reviews at Day 2 and Day 6
    return retentionCurve(score, 14, [2, 6]);
  }, [selectedTopic]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">
            Spaced-Repetition Study Plan
          </h1>
          <p className="text-xs text-muted-foreground">
            Algorithmically scheduling active reviews at optimal intervals before memory decay falls
            below threshold.
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
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Calendar Events Timeline */}
        <Panel className="lg:col-span-2">
          <PanelHeader
            title="Scheduled Retrieval Events"
            subtitle="Color-coded: Review Reminders (Primary), Quiz Sessions (Accent), Deep Study Blocks (Warn)"
          />
          <div className="divide-y divide-border p-4">
            {studyEvents.map((evt) => {
              const topicObj = topics.find((t) => t.id === evt.topic_id);
              const meta = STUDY_EVENT_META[evt.event_type] || {
                label: "Study Event",
                color: "text-primary",
                dot: "bg-primary",
              };
              const isCompleted = evt.status === "completed";
              const dateStr = new Date(evt.scheduled_at).toLocaleDateString("en-US", {
                weekday: "short",
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              });

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
                        <span className={`text-[11px] font-normal ${meta.color}`}>
                          · {meta.label}
                        </span>
                      </div>
                      <div className="num text-[11px] text-muted-foreground">{dateStr}</div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {isCompleted ? (
                      <span className="inline-flex items-center gap-1 rounded bg-positive/15 px-2 py-0.5 text-[10px] font-medium text-positive">
                        <CheckCircle2 className="h-3 w-3" /> Done
                      </span>
                    ) : (
                      <span className="rounded border border-border bg-surface-2 px-2 py-0.5 text-[10px] text-muted-foreground">
                        Scheduled
                      </span>
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
                <h3 className="text-xs font-semibold text-foreground">Google Calendar Sync</h3>
              </div>
              <button
                onClick={() => setGoogleCalendarConnected(!googleCalendarConnected)}
                className={`num rounded-full px-2.5 py-0.5 text-[10px] font-semibold transition ${
                  googleCalendarConnected
                    ? "bg-positive/15 text-positive"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {googleCalendarConnected ? "Connected" : "Disconnected"}
              </button>
            </div>

            <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
              ChaiGaram automatically pushes spaced-repetition study blocks and practice quiz
              reminders directly to your primary calendar.
            </p>

            <div className="mt-4 border-t border-border pt-3 text-[11px] text-muted-foreground">
              <span className="num text-foreground">Next sync:</span> Instant on schedule generation
            </div>
          </Panel>

          {/* Interactive Ebbinghaus Forgetting Curve */}
          <Panel className="p-5">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-foreground">
                Ebbinghaus Retention Decay Model
              </h3>
              <select
                value={selectedTopicId}
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
              Simulated retention curve for{" "}
              <span className="font-semibold text-foreground">{selectedTopic.title}</span> (Mastery:{" "}
              <span className="num text-primary">{selectedTopic.mastery_score}%</span>). Dots mark
              scheduled active retrieval drills.
            </p>

            <div className="mt-4 h-[180px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={retentionData}
                  margin={{ top: 5, right: 10, left: -20, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.5} />
                  <XAxis dataKey="day" {...chartAxis} tickFormatter={(d) => `D${d}`} />
                  <YAxis domain={[0, 100]} {...chartAxis} tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const d = payload[0]?.payload;
                      return (
                        <div className="rounded border border-border bg-popover p-2 text-[11px] shadow-md">
                          <p className="font-semibold">Day {d.day}</p>
                          <p className="num text-primary">Retention: {d.retention}%</p>
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
