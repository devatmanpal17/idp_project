import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import {
  ArrowRight,
  BrainCircuit,
  BookOpen,
  Calendar,
  CheckCircle2,
  Chrome,
  Clock,
  FileText,
  GraduationCap,
  Layers3,
  LockKeyhole,
  Sparkles,
  TrendingUp,
  Wand2,
} from "lucide-react";
import {
  coursesQuery,
  topicsQuery,
  quizzesQuery,
  studyEventsQuery,
  recommendationsQuery,
  activityQuery,
  EVENT_LABEL,
  relativeTime,
} from "@/lib/chaigaram";
import {
  Panel,
  PanelHeader,
  StatCard,
  MasteryPill,
  chartAxis,
  ChartTooltipBox,
  EmptyState,
} from "@/components/chaigaram/primitives";
import { QuizGenerator } from "@/components/chaigaram/QuizGenerator";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Overview | ChaiGaram" },
      {
        name: "description",
        content: "ChaiGaram - Extension Control Room Overview",
      },
    ],
  }),
  component: OverviewScreen,
});

function OverviewScreen() {
  const { data: courses = [] } = useQuery(coursesQuery);
  const { data: topics = [] } = useQuery(topicsQuery);
  const { data: quizzes = [] } = useQuery(quizzesQuery);
  const { data: studyEvents = [] } = useQuery(studyEventsQuery);
  const { data: recommendations = [] } = useQuery(recommendationsQuery);
  const { data: activityLog = [] } = useQuery(activityQuery);

  const [activeQuizTopic, setActiveQuizTopic] = useState<string | null>(null);

  // Computed metrics
  const activeCoursesCount = courses.length;
  const avgMastery =
    topics.length > 0
      ? Math.round(
          topics.reduce((acc, t) => acc + Number(t.mastery_score), 0) /
            topics.length,
        )
      : 0;
  const completedQuizzesCount = quizzes.length;
  const nextScheduledEvent = studyEvents.find((e) => e.status === "scheduled");

  // Chart data: Completion vs Mastery Gap
  const chartData = courses.map((c) => ({
    name: c.title.length > 18 ? c.title.substring(0, 16) + "…" : c.title,
    fullTitle: c.title,
    completion: Number(c.completion_pct),
    mastery: Number(c.overall_mastery),
    gap: Number(c.completion_pct) - Number(c.overall_mastery),
  }));

  return (
    <div className="space-y-14 sm:space-y-16 lg:space-y-20">
      <section className="relative overflow-hidden rounded-[28px] border border-border bg-surface px-6 py-12 sm:px-10 sm:py-16 lg:grid lg:grid-cols-[1.15fr_.85fr] lg:items-center lg:gap-14 lg:px-14 lg:py-20">
        <div className="relative z-10">
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-border bg-background/60 px-3 py-1.5 text-[11px] font-medium text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            Your private learning layer
          </div>
          <h1 className="max-w-3xl font-display text-[clamp(2.65rem,7vw,5.8rem)] font-semibold leading-[.94] tracking-[-0.065em] text-foreground">
            The web teaches.
            <br />
            <span className="text-muted-foreground">
              ChaiGaram makes it stick.
            </span>
          </h1>
          <p className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
            Capture any lesson, article, documentation page, or video. Turn it
            into grounded answers, adaptive practice, and a clear picture of
            what you actually know.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Link
              to="/simulator"
              className="inline-flex items-center justify-center gap-2 rounded-full bg-primary px-5 py-3 text-sm font-medium text-primary-foreground transition hover:brightness-110"
            >
              Set up the extension <ArrowRight className="h-4 w-4" />
            </Link>
            <button
              onClick={() => topics[0] && setActiveQuizTopic(topics[0].title)}
              disabled={topics.length === 0}
              className="inline-flex items-center justify-center gap-2 rounded-full border border-border bg-background/40 px-5 py-3 text-sm font-medium text-foreground transition hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-45"
            >
              <Wand2 className="h-4 w-4" />
              Start a quick drill
            </button>
          </div>
        </div>

        <div className="relative mt-12 lg:mt-0">
          <div className="absolute inset-8 rounded-full bg-primary/20 blur-[90px]" />
          <div className="relative rounded-[24px] border border-border bg-background/75 p-5 shadow-float backdrop-blur-xl sm:p-7">
            <div className="flex items-center justify-between border-b border-border pb-5">
              <div>
                <p className="text-xs font-medium text-muted-foreground">
                  Learning snapshot
                </p>
                <p className="mt-1 text-lg font-semibold">Your real progress</p>
              </div>
              <span className="h-2.5 w-2.5 rounded-full bg-positive shadow-[0_0_16px_var(--positive)]" />
            </div>
            <div className="grid grid-cols-2 gap-3 py-5">
              <div className="rounded-2xl bg-surface-2 p-4">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Indexed topics
                </p>
                <p className="mt-4 text-3xl font-semibold tracking-tight">
                  {topics.length}
                </p>
              </div>
              <div className="rounded-2xl bg-surface-2 p-4">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Verified mastery
                </p>
                <p className="mt-4 text-3xl font-semibold tracking-tight">
                  {avgMastery}%
                </p>
              </div>
            </div>
            <div className="rounded-2xl border border-border p-4">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">
                  Latest captured source
                </span>
                <Layers3 className="h-4 w-4 text-primary" />
              </div>
              <p className="mt-3 truncate text-sm font-medium">
                {courses[0]?.title ?? "Capture your first learning page"}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Top 4 Stat Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="ACTIVE COURSES"
          value={activeCoursesCount}
          icon={<BookOpen className="h-4 w-4" />}
          hint="Derived from indexed extension captures"
          tone="primary"
        />
        <StatCard
          label="OVERALL MASTERY"
          value={avgMastery}
          suffix="%"
          icon={<GraduationCap className="h-4 w-4" />}
          hint={`Average across ${topics.length} indexed topic${topics.length === 1 ? "" : "s"}`}
          tone={avgMastery >= 70 ? "positive" : "warn"}
        />
        <StatCard
          label="QUIZZES COMPLETED"
          value={completedQuizzesCount}
          icon={<CheckCircle2 className="h-4 w-4" />}
          hint="Persisted server-side attempts"
          tone="default"
        />
        <StatCard
          label="NEXT SCHEDULED REVIEW"
          raw={
            nextScheduledEvent
              ? new Date(nextScheduledEvent.scheduled_at).toLocaleString()
              : "None scheduled"
          }
          icon={<Calendar className="h-4 w-4" />}
          hint="Calculated from actual review events"
          tone="warn"
        />
      </div>

      <section>
        <div className="mx-auto mb-9 max-w-2xl text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
            One continuous study loop
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-[-0.045em] sm:text-4xl">
            From browsing to understanding.
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground sm:text-base">
            No uploading folders or reorganizing notes. Keep learning where you
            already learn.
          </p>
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          <div className="rounded-[24px] border border-border bg-surface p-6 sm:p-7">
            <span className="grid h-11 w-11 place-items-center rounded-2xl bg-primary/10 text-primary">
              <Chrome className="h-5 w-5" />
            </span>
            <p className="mt-8 text-xs font-medium text-muted-foreground">01</p>
            <h3 className="mt-2 text-xl font-semibold">Capture anything</h3>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Use any course, article, documentation site, or video. Save a
              page, a selection, or live captions.
            </p>
          </div>
          <div className="rounded-[24px] border border-border bg-surface p-6 sm:p-7">
            <span className="grid h-11 w-11 place-items-center rounded-2xl bg-primary/10 text-primary">
              <FileText className="h-5 w-5" />
            </span>
            <p className="mt-8 text-xs font-medium text-muted-foreground">02</p>
            <h3 className="mt-2 text-xl font-semibold">Ask with evidence</h3>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Your local model retrieves the most relevant captured passages
              before answering, with sources attached.
            </p>
          </div>
          <div className="rounded-[24px] border border-border bg-surface p-6 sm:p-7">
            <span className="grid h-11 w-11 place-items-center rounded-2xl bg-primary/10 text-primary">
              <BrainCircuit className="h-5 w-5" />
            </span>
            <p className="mt-8 text-xs font-medium text-muted-foreground">03</p>
            <h3 className="mt-2 text-xl font-semibold">Prove it stuck</h3>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Adaptive quizzes turn recall into verified mastery and reveal the
              concepts worth revisiting.
            </p>
          </div>
        </div>
        <div className="mt-5 flex flex-col items-start justify-between gap-4 rounded-[20px] border border-border bg-surface/60 p-5 sm:flex-row sm:items-center">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-positive/10 text-positive">
              <LockKeyhole className="h-4 w-4" />
            </span>
            <div>
              <p className="text-sm font-medium">Private by default</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Llama, ChromaDB, and your learning history stay on your machine.
              </p>
            </div>
          </div>
          <Link
            to="/settings"
            className="inline-flex shrink-0 items-center gap-1.5 text-xs font-medium text-primary"
          >
            View local setup <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </section>

      <section>
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
              Your knowledge
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em] sm:text-3xl">
              Topics taking shape.
            </h2>
          </div>
          <Link
            to="/mastery"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary"
          >
            Explore mastery <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
        {topics.length ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {topics.slice(0, 6).map((topic) => (
              <button
                key={topic.id}
                onClick={() => setActiveQuizTopic(topic.title)}
                className="group rounded-[20px] border border-border bg-surface p-5 text-left transition hover:border-border-strong hover:bg-surface-2"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {topic.title}
                    </p>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      {topic.indexed_chunks ?? 0} indexed passages
                    </p>
                  </div>
                  <span className="text-2xl font-semibold tracking-tight">
                    {Math.round(topic.mastery_score)}%
                  </span>
                </div>
                <div className="mt-5 h-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{
                      width: `${Math.max(0, Math.min(100, topic.mastery_score))}%`,
                    }}
                  />
                </div>
                <p className="mt-3 text-[11px] text-primary opacity-0 transition-opacity group-hover:opacity-100">
                  Start a practice drill →
                </p>
              </button>
            ))}
          </div>
        ) : (
          <div className="rounded-[24px] border border-dashed border-border bg-surface/50 px-6 py-12 text-center">
            <Layers3 className="mx-auto h-6 w-6 text-muted-foreground" />
            <p className="mt-4 text-sm font-medium">
              Your knowledge map starts with one page.
            </p>
            <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-muted-foreground">
              Install the extension and capture something you are learning. Real
              topics will appear here automatically.
            </p>
            <Link
              to="/simulator"
              className="mt-5 inline-flex items-center gap-1.5 text-xs font-medium text-primary"
            >
              Open extension setup <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        )}
      </section>

      {/* Main Grid: Chart & Learn Next */}
      <div className="grid grid-cols-1 gap-7 xl:grid-cols-3">
        {/* Completion vs Mastery Gap Chart (2 cols) */}
        <Panel className="xl:col-span-2">
          <PanelHeader
            title="Watched isn't learned"
            subtitle="Course progress beside what you can actually recall"
          />
          <div className="p-4">
            {chartData.length ? (
              <div className="h-[280px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={chartData}
                    margin={{ top: 10, right: 10, left: -20, bottom: 20 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="var(--border)"
                      opacity={0.6}
                    />
                    <XAxis
                      dataKey="name"
                      {...chartAxis}
                      tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                      angle={-15}
                      textAnchor="end"
                      interval={0}
                    />
                    <YAxis
                      {...chartAxis}
                      domain={[0, 100]}
                      tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                    />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (!active || !payload?.length) return null;
                        const data = payload[0]?.payload;
                        return (
                          <div className="rounded-md border border-border bg-popover p-2.5 shadow-md">
                            <p className="text-xs font-semibold text-foreground">
                              {data.fullTitle}
                            </p>
                            <div className="mt-1.5 space-y-1 text-xs">
                              <div className="flex justify-between gap-4 text-muted-foreground">
                                <span>Video Completion:</span>
                                <span className="num font-semibold text-foreground">
                                  {data.completion}%
                                </span>
                              </div>
                              <div className="flex justify-between gap-4 text-muted-foreground">
                                <span>Verified Mastery:</span>
                                <span className="num font-semibold text-primary">
                                  {data.mastery}%
                                </span>
                              </div>
                              <div className="flex justify-between gap-4 border-t border-border pt-1 text-warn">
                                <span>Comprehension Gap:</span>
                                <span className="num font-semibold">
                                  -{data.gap}%
                                </span>
                              </div>
                            </div>
                          </div>
                        );
                      }}
                    />
                    <Legend
                      wrapperStyle={{ fontSize: "12px", paddingTop: "10px" }}
                      formatter={(val) => (
                        <span className="text-xs text-muted-foreground">
                          {val === "completion"
                            ? "Video Completion %"
                            : "Verified Mastery %"}
                        </span>
                      )}
                    />
                    <Bar
                      dataKey="completion"
                      name="completion"
                      fill="var(--accent)"
                      radius={[4, 4, 0, 0]}
                      barSize={18}
                    />
                    <Bar
                      dataKey="mastery"
                      name="mastery"
                      fill="var(--primary)"
                      radius={[4, 4, 0, 0]}
                      barSize={18}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyState
                icon={<BookOpen className="h-5 w-5" />}
                title="No learning progress yet"
                hint="Capture a course or video with the extension to build this comparison."
                action={
                  <Link
                    to="/simulator"
                    className="mt-2 text-xs font-medium text-primary"
                  >
                    Set up extension
                  </Link>
                }
              />
            )}
          </div>
        </Panel>

        {/* Learn Next / AI Recommendations (1 col) */}
        <Panel>
          <PanelHeader
            title="Worth your next 20 minutes"
            subtitle="The biggest gains hiding in your own study history"
            action={
              <Link
                to="/recommendations"
                className="text-[11px] font-medium text-primary hover:underline"
              >
                View all
              </Link>
            }
          />
          <div className="divide-y divide-border p-2">
            {recommendations.length === 0 ? (
              <EmptyState
                icon={<Sparkles className="h-5 w-5" />}
                title="Nothing to review yet"
                hint="Recommendations appear after your first assessed topic."
              />
            ) : (
              recommendations.slice(0, 3).map((rec) => {
                const topicObj = topics.find((t) => t.id === rec.topic_id);
                const title = topicObj?.title;
                if (!title) return null;
                return (
                  <div key={rec.id} className="space-y-1.5 p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-foreground">
                        {title}
                      </span>
                      <span className="num rounded bg-warn/15 px-1.5 py-0.5 text-[10px] font-medium text-warn">
                        {rec.impact_score} impact
                      </span>
                    </div>
                    <p className="line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
                      {rec.reasoning}
                    </p>
                    <div className="flex items-center justify-between pt-1">
                      <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {rec.estimated_minutes} min drill
                      </span>
                      <button
                        onClick={() => setActiveQuizTopic(title)}
                        className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
                      >
                        <Sparkles className="h-3 w-3" />
                        Start Quiz
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </Panel>
      </div>

      {/* Bottom Grid: Recent Activity Feed & Live RAG Generator Modal/Drawer */}
      <div className="grid grid-cols-1 gap-7 xl:grid-cols-3">
        {/* Recent Activity Feed */}
        <Panel className="xl:col-span-2">
          <PanelHeader
            title="The study trail"
            subtitle="Fresh captures, finished quizzes, and mastery changes"
          />
          <div className="divide-y divide-border p-2">
            {activityLog.length === 0 ? (
              <EmptyState
                icon={<Clock className="h-5 w-5" />}
                title="Your study trail is empty"
                hint="Captured pages and completed quizzes will appear here."
              />
            ) : (
              activityLog.slice(0, 5).map((act) => {
                const meta = (act.metadata ?? {}) as Record<
                  string,
                  string | number | undefined
                >;
                const topicName = meta["topic"] as string;
                return (
                  <div
                    key={act.id}
                    className="flex items-center justify-between gap-3 p-3"
                  >
                    <div className="flex items-center gap-3">
                      <div className="grid h-8 w-8 shrink-0 place-items-center rounded bg-surface-2 text-primary">
                        {act.event_type === "quiz_completed" ? (
                          <CheckCircle2 className="h-4 w-4 text-positive" />
                        ) : act.event_type === "topic_revisit" ? (
                          <TrendingUp className="h-4 w-4 text-warn" />
                        ) : (
                          <Clock className="h-4 w-4 text-accent" />
                        )}
                      </div>
                      <div>
                        <div className="text-xs font-semibold text-foreground">
                          {EVENT_LABEL[act.event_type] || act.event_type} ·{" "}
                          <span className="font-normal text-muted-foreground">
                            {topicName}
                          </span>
                        </div>
                        <div className="num text-[10px] text-muted-foreground">
                          {meta["score"] !== undefined &&
                            `Score: ${meta["score"]}%  · `}
                          {meta["revisits"] !== undefined &&
                            `Revisits: ${meta["revisits"]}  · `}
                          {meta["delta"] !== undefined &&
                            `Mastery Δ: +${meta["delta"]}%  · `}
                          {relativeTime(act.created_at)}
                        </div>
                      </div>
                    </div>

                    <button
                      onClick={() => setActiveQuizTopic(topicName)}
                      className="shrink-0 rounded border border-border bg-surface px-2 py-1 text-[11px] text-muted-foreground hover:border-primary/50 hover:text-foreground"
                    >
                      Quiz
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </Panel>

        {/* Quick Quiz Generator Panel */}
        <Panel className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">
              Quick practice drill
            </h3>
            {activeQuizTopic && (
              <button
                onClick={() => setActiveQuizTopic(null)}
                className="text-[11px] text-muted-foreground hover:text-foreground"
              >
                Reset
              </button>
            )}
          </div>
          {activeQuizTopic ? (
            <QuizGenerator
              topicTitle={activeQuizTopic}
              masteryScore={
                topics.find((topic) => topic.title === activeQuizTopic)
                  ?.mastery_score ?? 0
              }
              compact={true}
              onMasteryUpdated={(newScore) => {
                console.log("Mastery updated to:", newScore);
              }}
            />
          ) : (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <div className="grid h-10 w-10 place-items-center rounded-full bg-primary/10 text-primary">
                <Wand2 className="h-5 w-5" />
              </div>
              <p className="mt-3 text-xs font-medium text-foreground">
                Select a topic to drill
              </p>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Retrieves lecture transcript chunks, calibrates difficulty, and
                generates questions.
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-1.5">
                {topics.slice(0, 3).map((topic) => (
                  <button
                    key={topic.id}
                    onClick={() => setActiveQuizTopic(topic.title)}
                    className="rounded border border-border bg-surface-2 px-2.5 py-1 text-[11px] text-foreground transition hover:border-primary hover:text-primary"
                  >
                    {topic.title}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
