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
  BookOpen,
  Calendar,
  CheckCircle2,
  Clock,
  Compass,
  Flame,
  GraduationCap,
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
} from "@/lib/cognivue";
import {
  Panel,
  PanelHeader,
  StatCard,
  MasteryPill,
  chartAxis,
  ChartTooltipBox,
} from "@/components/cognivue/primitives";
import { QuizGenerator } from "@/components/cognivue/QuizGenerator";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Overview | Cognivue Insight" },
      { name: "description", content: "Cognivue Insight - Extension Control Room Overview" },
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
      ? Math.round(topics.reduce((acc, t) => acc + Number(t.mastery_score), 0) / topics.length)
      : 64;
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
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">
            Learning Telemetry Control Room
          </h1>
          <p className="text-xs text-muted-foreground">
            Synthesizing DOM interaction signals into real-time topic mastery & spaced-repetition
            RAG.
          </p>
        </div>
        <button
          onClick={() => setActiveQuizTopic("Support Vector Machines")}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-3.5 py-2 text-xs font-medium text-primary-foreground shadow-sm transition hover:bg-primary/90"
        >
          <Wand2 className="h-4 w-4" />
          Launch AI RAG Drill
        </button>
      </div>

      {/* Top 4 Stat Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="ACTIVE COURSES"
          value={activeCoursesCount}
          icon={<BookOpen className="h-4 w-4" />}
          hint="Tracked across Udemy, Coursera & edX"
          tone="primary"
        />
        <StatCard
          label="OVERALL MASTERY"
          value={avgMastery}
          suffix="%"
          icon={<GraduationCap className="h-4 w-4" />}
          hint="Weighted avg across 20 subtopics"
          tone={avgMastery >= 70 ? "positive" : "warn"}
        />
        <StatCard
          label="QUIZZES COMPLETED"
          value={completedQuizzesCount}
          icon={<CheckCircle2 className="h-4 w-4" />}
          hint="Target: 8 quizzes / week"
          tone="default"
        />
        <StatCard
          label="NEXT SCHEDULED REVIEW"
          raw={nextScheduledEvent ? "Today, 18:00" : "None scheduled"}
          icon={<Calendar className="h-4 w-4" />}
          hint="Dynamic Programming · Spaced repetition"
          tone="warn"
        />
      </div>

      {/* Main Grid: Chart & Learn Next */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Completion vs Mastery Gap Chart (2 cols) */}
        <Panel className="lg:col-span-2">
          <PanelHeader
            title="Completion vs. Mastery Gap"
            subtitle="Video watch percentage vs. verified conceptual comprehension (the core Cognivue insight)"
          />
          <div className="p-4">
            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.6} />
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
                          <p className="text-xs font-semibold text-foreground">{data.fullTitle}</p>
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
                              <span className="num font-semibold">-{data.gap}%</span>
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
                        {val === "completion" ? "Video Completion %" : "Verified Mastery %"}
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
          </div>
        </Panel>

        {/* Learn Next / AI Recommendations (1 col) */}
        <Panel>
          <PanelHeader
            title="Learn Next · AI Ranked"
            subtitle="Top high-yield review opportunities"
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
            {recommendations.slice(0, 3).map((rec) => {
              const topicObj = topics.find((t) => t.id === rec.topic_id);
              const title = topicObj?.title || "Dynamic Programming";
              return (
                <div key={rec.id} className="space-y-1.5 p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-foreground">{title}</span>
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
            })}
          </div>
        </Panel>
      </div>

      {/* Bottom Grid: Recent Activity Feed & Live RAG Generator Modal/Drawer */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Recent Activity Feed */}
        <Panel className="lg:col-span-2">
          <PanelHeader
            title="Real-Time Learning Activity Feed"
            subtitle="DOM capture signals, quiz completions, and mastery recalculations"
          />
          <div className="divide-y divide-border p-2">
            {activityLog.slice(0, 5).map((act) => {
              const meta = act.metadata as Record<string, string | number | undefined>;
              const topicName = (meta.topic as string) || "Core Module";
              return (
                <div key={act.id} className="flex items-center justify-between gap-3 p-3">
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
                        <span className="font-normal text-muted-foreground">{topicName}</span>
                      </div>
                      <div className="num text-[10px] text-muted-foreground">
                        {meta.score !== undefined && `Score: ${meta.score}%  · `}
                        {meta.revisits !== undefined && `Revisits: ${meta.revisits}  · `}
                        {meta.delta !== undefined && `Mastery Δ: +${meta.delta}%  · `}
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
            })}
          </div>
        </Panel>

        {/* Quick Quiz Generator Panel */}
        <Panel className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">Live AI Practice Drill</h3>
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
              masteryScore={41}
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
              <p className="mt-3 text-xs font-medium text-foreground">Select a topic to drill</p>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Retrieves lecture transcript chunks, calibrates difficulty, and generates questions.
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-1.5">
                {["Support Vector Machines", "React Hooks", "Dynamic Programming"].map((t) => (
                  <button
                    key={t}
                    onClick={() => setActiveQuizTopic(t)}
                    className="rounded border border-border bg-surface-2 px-2.5 py-1 text-[11px] text-foreground transition hover:border-primary hover:text-primary"
                  >
                    {t}
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
