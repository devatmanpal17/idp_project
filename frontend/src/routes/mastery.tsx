import { useState, useMemo } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  Calculator,
  ChevronDown,
  ChevronUp,
  HelpCircle,
  Info,
  Radar as RadarIcon,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";
import { coursesQuery, topicsQuery, SIGNAL_WEIGHTS, type Topic } from "@/lib/cognivue";
import {
  Panel,
  PanelHeader,
  MasteryPill,
  SignalBar,
  TrendArrow,
  chartAxis,
} from "@/components/cognivue/primitives";
import { QuizGenerator } from "@/components/cognivue/QuizGenerator";

export const Route = createFileRoute("/mastery")({
  head: () => ({
    meta: [
      { title: "Topic Mastery | Cognivue Insight" },
      {
        name: "description",
        content:
          "Radar visualization, weighted signal decomposition, and mastery formula breakdown",
      },
    ],
  }),
  component: TopicMasteryScreen,
});

function TopicMasteryScreen() {
  const { data: courses = [] } = useQuery(coursesQuery);
  const { data: topics = [] } = useQuery(topicsQuery);

  const [selectedCourseId, setSelectedCourseId] = useState<string>("all");
  const [sortField, setSortField] = useState<keyof Topic>("mastery_score");
  const [sortAsc, setSortAsc] = useState(false);
  const [inspectTopic, setInspectTopic] = useState<Topic | null>(null);

  // Filter topics
  const filteredTopics = useMemo(() => {
    const list =
      selectedCourseId === "all" ? topics : topics.filter((t) => t.course_id === selectedCourseId);
    return [...list].sort((a, b) => {
      const valA = a[sortField];
      const valB = b[sortField];
      if (typeof valA === "number" && typeof valB === "number") {
        return sortAsc ? valA - valB : valB - valA;
      }
      return sortAsc
        ? String(valA).localeCompare(String(valB))
        : String(valB).localeCompare(String(valA));
    });
  }, [topics, selectedCourseId, sortField, sortAsc]);

  // Radar Chart Data (take top 6-8 topics for clarity)
  const radarData = useMemo(() => {
    const subset = filteredTopics.slice(0, 8);
    return subset.map((t) => ({
      topic: t.title.length > 14 ? t.title.substring(0, 12) + "…" : t.title,
      fullTopic: t.title,
      mastery: Number(t.mastery_score),
      quiz: Number(t.quiz_perf_pct),
      time: Number(t.time_on_section_pct),
    }));
  }, [filteredTopics]);

  const handleSort = (field: keyof Topic) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">
            Topic Mastery & Decomposition
          </h1>
          <p className="text-xs text-muted-foreground">
            Multi-signal synthesis evaluating comprehension across quiz accuracy, dwell time, and
            revisit intervals.
          </p>
        </div>

        {/* Course Filter Selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Course filter:</span>
          <select
            value={selectedCourseId}
            onChange={(e) => setSelectedCourseId(e.target.value)}
            className="rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-foreground focus:border-primary focus:outline-none"
          >
            <option value="all">All Tracked Courses ({topics.length} topics)</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Main Grid: Radar Chart (Centerpiece) + Formula Breakdown */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Radar Chart Centerpiece */}
        <Panel className="lg:col-span-2">
          <PanelHeader
            title="Topic Strength & Weakness Radar"
            subtitle="Polar representation of verified comprehension scores across course domains"
          />
          <div className="p-4">
            <div className="h-[320px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart cx="50%" cy="50%" outerRadius="80%" data={radarData}>
                  <PolarGrid stroke="var(--border)" opacity={0.6} />
                  <PolarAngleAxis
                    dataKey="topic"
                    tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                  />
                  <PolarRadiusAxis
                    angle={30}
                    domain={[0, 100]}
                    stroke="var(--border)"
                    tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const d = payload[0]?.payload;
                      return (
                        <div className="rounded-md border border-border bg-popover p-2.5 text-xs shadow-md">
                          <p className="font-semibold text-foreground">{d.fullTopic}</p>
                          <div className="mt-1 space-y-0.5 text-muted-foreground">
                            <p>
                              Mastery Score:{" "}
                              <span className="num font-semibold text-primary">{d.mastery}%</span>
                            </p>
                            <p>
                              Quiz Accuracy:{" "}
                              <span className="num font-semibold text-foreground">{d.quiz}%</span>
                            </p>
                            <p>
                              Time on Section:{" "}
                              <span className="num font-semibold text-foreground">{d.time}%</span>
                            </p>
                          </div>
                        </div>
                      );
                    }}
                  />
                  <Radar
                    name="Mastery Score"
                    dataKey="mastery"
                    stroke="var(--primary)"
                    fill="var(--primary)"
                    fillOpacity={0.25}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </Panel>

        {/* Signal Weights Explanation Panel */}
        <Panel className="flex flex-col justify-between p-5">
          <div>
            <div className="flex items-center gap-2">
              <div className="grid h-7 w-7 place-items-center rounded bg-primary/10 text-primary">
                <Calculator className="h-4 w-4" />
              </div>
              <h3 className="text-sm font-semibold text-foreground">Cognivue Mastery Formula</h3>
            </div>

            <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
              Unlike video completion alone, Cognivue computes true retention through continuous
              Bayesian updates combining 3 weighted DOM signals:
            </p>

            <div className="mt-4 space-y-3">
              <div className="rounded-md border border-border bg-surface-2 p-3">
                <div className="flex justify-between text-xs font-semibold text-foreground">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-primary" /> Quiz Performance
                  </span>
                  <span className="num text-primary">40% Weight</span>
                </div>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Accuracy on active retrieval drills & schema-validated questions.
                </p>
              </div>

              <div className="rounded-md border border-border bg-surface-2 p-3">
                <div className="flex justify-between text-xs font-semibold text-foreground">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-accent" /> Dwell Time-on-Section
                  </span>
                  <span className="num text-accent">35% Weight</span>
                </div>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Normalized duration spent reading transcript sections and code snippets.
                </p>
              </div>

              <div className="rounded-md border border-border bg-surface-2 p-3">
                <div className="flex justify-between text-xs font-semibold text-foreground">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-warn" /> Revisit Interval
                  </span>
                  <span className="num text-warn">25% Weight</span>
                </div>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Frequency of returning to concepts aligned with the Ebbinghaus forgetting curve.
                </p>
              </div>
            </div>
          </div>

          <div className="mt-4 rounded border border-primary/20 bg-primary/5 p-2.5 text-[11px] text-muted-foreground">
            <span className="font-semibold text-foreground">Formula:</span>{" "}
            <span className="num">Mastery = 0.40×Quiz + 0.35×Time + 0.25×Revisit</span>
          </div>
        </Panel>
      </div>

      {/* Sortable Topics Table */}
      <Panel>
        <PanelHeader
          title="All Subtopics Telemetry Table"
          subtitle="Click column headers to sort · Click any row to inspect mathematical derivation"
        />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-border bg-surface-2 text-[11px] text-muted-foreground">
              <tr>
                <th
                  onClick={() => handleSort("title")}
                  className="cursor-pointer px-4 py-3 font-medium hover:text-foreground"
                >
                  Topic Name {sortField === "title" && (sortAsc ? "▲" : "▼")}
                </th>
                <th
                  onClick={() => handleSort("quiz_perf_pct")}
                  className="cursor-pointer px-3 py-3 font-medium hover:text-foreground"
                >
                  Quiz (40%) {sortField === "quiz_perf_pct" && (sortAsc ? "▲" : "▼")}
                </th>
                <th
                  onClick={() => handleSort("time_on_section_pct")}
                  className="cursor-pointer px-3 py-3 font-medium hover:text-foreground"
                >
                  Time (35%) {sortField === "time_on_section_pct" && (sortAsc ? "▲" : "▼")}
                </th>
                <th
                  onClick={() => handleSort("revisit_frequency_pct")}
                  className="cursor-pointer px-3 py-3 font-medium hover:text-foreground"
                >
                  Revisit (25%) {sortField === "revisit_frequency_pct" && (sortAsc ? "▲" : "▼")}
                </th>
                <th className="w-32 px-3 py-3 font-medium">Signal Composition</th>
                <th
                  onClick={() => handleSort("mastery_score")}
                  className="cursor-pointer px-3 py-3 font-medium hover:text-foreground"
                >
                  Mastery Score {sortField === "mastery_score" && (sortAsc ? "▲" : "▼")}
                </th>
                <th
                  onClick={() => handleSort("trend_delta")}
                  className="cursor-pointer px-3 py-3 font-medium hover:text-foreground"
                >
                  Weekly Trend {sortField === "trend_delta" && (sortAsc ? "▲" : "▼")}
                </th>
                <th className="px-4 py-3 text-right font-medium">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredTopics.map((topic) => (
                <tr
                  key={topic.id}
                  onClick={() => setInspectTopic(topic)}
                  className="cursor-pointer transition-colors hover:bg-surface-2/60"
                >
                  <td className="px-4 py-3 font-semibold text-foreground">{topic.title}</td>
                  <td className="num px-3 py-3 text-muted-foreground">{topic.quiz_perf_pct}%</td>
                  <td className="num px-3 py-3 text-muted-foreground">
                    {topic.time_on_section_pct}%
                  </td>
                  <td className="num px-3 py-3 text-muted-foreground">
                    {topic.revisit_frequency_pct}%
                  </td>
                  <td className="px-3 py-3">
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
                      onClick={(e) => {
                        e.stopPropagation();
                        setInspectTopic(topic);
                      }}
                      className="rounded border border-border bg-surface px-2.5 py-1 text-[11px] text-muted-foreground hover:border-primary hover:text-foreground"
                    >
                      Formula
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Inspect Topic Formula Drawer / Modal */}
      {inspectTopic && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm">
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-border bg-surface p-6 shadow-2xl">
            <div className="flex items-start justify-between">
              <div>
                <span className="label-xs text-primary">TOPIC TELEMETRY BREAKDOWN</span>
                <h2 className="font-display text-xl font-bold text-foreground">
                  {inspectTopic.title}
                </h2>
              </div>
              <button
                onClick={() => setInspectTopic(null)}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-surface-2 hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-5 space-y-4">
              {/* Formula Calculation Box */}
              <div className="rounded-lg border border-primary/30 bg-primary/5 p-4">
                <div className="text-xs font-semibold text-foreground">
                  Calculated Formula Verification:
                </div>
                <div className="num mt-2 font-mono text-xs leading-relaxed text-muted-foreground">
                  (0.40 × {inspectTopic.quiz_perf_pct}) + (0.35 × {inspectTopic.time_on_section_pct}
                  ) + (0.25 × {inspectTopic.revisit_frequency_pct})
                  <br />={" "}
                  <span className="font-semibold text-foreground">
                    {(0.4 * inspectTopic.quiz_perf_pct).toFixed(1)} +{" "}
                    {(0.35 * inspectTopic.time_on_section_pct).toFixed(1)} +{" "}
                    {(0.25 * inspectTopic.revisit_frequency_pct).toFixed(1)}
                  </span>
                  <br />={" "}
                  <span className="text-base font-bold text-primary">
                    {inspectTopic.mastery_score} Mastery Score
                  </span>
                </div>
              </div>

              {/* RAG Practice Quiz on this Topic */}
              <div className="border-t border-border pt-4">
                <h3 className="mb-3 text-xs font-semibold text-foreground">
                  Live AI RAG Practice Drill
                </h3>
                <QuizGenerator
                  topicTitle={inspectTopic.title}
                  masteryScore={inspectTopic.mastery_score}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
