import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import {
  ArrowLeft,
  BookOpen,
  Clock,
  ExternalLink,
  Flame,
  RotateCcw,
  Sparkles,
  Wand2,
} from "lucide-react";
import { coursesQuery, topicsQuery, PLATFORM_TINT } from "@/lib/cognivue";
import {
  Panel,
  PanelHeader,
  MasteryPill,
  SignalBar,
  Meter,
  TrendArrow,
  chartAxis,
} from "@/components/cognivue/primitives";
import { QuizGenerator } from "@/components/cognivue/QuizGenerator";

export const Route = createFileRoute("/courses/$courseId")({
  head: () => ({
    meta: [
      { title: "Course Details | Cognivue Insight" },
      { name: "description", content: "Course module telemetry, signals, and mastery breakdown" },
    ],
  }),
  component: CourseDetail,
});

function CourseDetail() {
  const { courseId } = Route.useParams();
  const { data: courses = [] } = useQuery(coursesQuery);
  const { data: topics = [] } = useQuery(topicsQuery);

  const [selectedTopicForQuiz, setSelectedTopicForQuiz] = useState<string | null>(null);

  const course = courses.find((c) => c.id === courseId) || courses[0];
  const courseTopics = topics.filter((t) => t.course_id === (course?.id || courseId));

  const platformColor = course ? PLATFORM_TINT[course.platform] || "text-primary" : "text-primary";

  // Time on section chart data
  const timeChartData = courseTopics.map((t) => ({
    name: t.title.length > 16 ? t.title.substring(0, 14) + "…" : t.title,
    fullTitle: t.title,
    minutes: t.minutes_on_section,
    revisits: t.revisits,
    mastery: t.mastery_score,
  }));

  if (!course) {
    return (
      <div className="p-8 text-center">
        <p className="text-muted-foreground">Course not found.</p>
        <Link to="/courses" className="mt-4 inline-block text-xs text-primary hover:underline">
          &larr; Back to courses
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb & Navigation */}
      <div>
        <Link
          to="/courses"
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to courses
        </Link>
      </div>

      {/* Header Banner */}
      <Panel className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1">
            <span className={`text-xs font-semibold uppercase tracking-wider ${platformColor}`}>
              {course.platform} Telemetry Active
            </span>
            <h1 className="font-display text-2xl font-bold text-foreground">{course.title}</h1>
            <p className="text-xs text-muted-foreground">
              {courseTopics.length} tracked modules · High-resolution DOM dwell & transcript parsing
              enabled.
            </p>
          </div>

          <div className="flex items-center gap-4">
            <div className="rounded-lg border border-border bg-surface-2 p-3 text-center">
              <span className="text-[10px] text-muted-foreground">VIDEO WATCHED</span>
              <div className="num text-xl font-bold text-accent">{course.completion_pct}%</div>
            </div>
            <div className="rounded-lg border border-border bg-surface-2 p-3 text-center">
              <span className="text-[10px] text-muted-foreground">VERIFIED MASTERY</span>
              <div className="num text-xl font-bold text-primary">{course.overall_mastery}%</div>
            </div>
          </div>
        </div>
      </Panel>

      {/* Grid: Time Chart & Module Breakdown */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Module Breakdown Table (2 cols) */}
        <Panel className="lg:col-span-2">
          <PanelHeader
            title="Module Telemetry & Weighted Signals"
            subtitle="Formula: 40% Quiz Perf + 35% Dwell Time + 25% Revisit Frequency"
          />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-border bg-surface-2 text-[11px] text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Module / Topic</th>
                  <th className="px-3 py-2.5 font-medium">Dwell Time</th>
                  <th className="px-3 py-2.5 font-medium">Revisits</th>
                  <th className="px-3 py-2.5 font-medium">Signals (Q/T/R)</th>
                  <th className="px-3 py-2.5 font-medium">Mastery</th>
                  <th className="px-3 py-2.5 font-medium">Trend</th>
                  <th className="px-4 py-2.5 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {courseTopics.map((topic) => (
                  <tr key={topic.id} className="hover:bg-surface-2/50">
                    <td className="px-4 py-3 font-semibold text-foreground">{topic.title}</td>
                    <td className="num px-3 py-3 text-muted-foreground">
                      {topic.minutes_on_section}m
                    </td>
                    <td className="num px-3 py-3 text-muted-foreground">{topic.revisits}x</td>
                    <td className="w-24 px-3 py-3">
                      <SignalBar
                        quiz={topic.quiz_perf_pct}
                        time={topic.time_on_section_pct}
                        revisit={topic.revisit_frequency_pct}
                      />
                    </td>
                    <td className="px-3 py-3">
                      <MasteryPill score={topic.mastery_score} />
                    </td>
                    <td className="px-3 py-3">
                      <TrendArrow delta={topic.trend_delta} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => setSelectedTopicForQuiz(topic.title)}
                        className="inline-flex items-center gap-1 rounded bg-primary/10 px-2 py-1 text-[11px] font-medium text-primary hover:bg-primary/20"
                      >
                        <Sparkles className="h-3 w-3" /> Drill
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        {/* Time-on-Section Chart (1 col) */}
        <Panel>
          <PanelHeader title="Dwell Time Distribution" subtitle="Minutes spent per module" />
          <div className="p-4">
            <div className="h-[260px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={timeChartData}
                  layout="vertical"
                  margin={{ top: 5, right: 10, left: 10, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.5} />
                  <XAxis type="number" {...chartAxis} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    {...chartAxis}
                    width={75}
                    tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const data = payload[0]?.payload;
                      return (
                        <div className="rounded-md border border-border bg-popover p-2 text-xs shadow-md">
                          <p className="font-semibold text-foreground">{data.fullTitle}</p>
                          <p className="num mt-1 text-primary">{data.minutes} minutes dwell</p>
                          <p className="num text-muted-foreground">{data.revisits} revisits</p>
                        </div>
                      );
                    }}
                  />
                  <Bar dataKey="minutes" fill="var(--primary)" radius={[0, 4, 4, 0]} barSize={14} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </Panel>
      </div>

      {/* Selected Topic RAG Quiz Section */}
      {selectedTopicForQuiz && (
        <Panel className="border-primary/40 p-5">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="font-display text-sm font-bold text-foreground">
                AI RAG Assessment · {selectedTopicForQuiz}
              </h3>
              <p className="text-xs text-muted-foreground">
                Dynamic RAG pipeline analyzing transcript chunks & calibrating question difficulty.
              </p>
            </div>
            <button
              onClick={() => setSelectedTopicForQuiz(null)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Close
            </button>
          </div>

          <QuizGenerator
            topicTitle={selectedTopicForQuiz}
            masteryScore={
              courseTopics.find((t) => t.title === selectedTopicForQuiz)?.mastery_score ?? 50
            }
          />
        </Panel>
      )}
    </div>
  );
}
