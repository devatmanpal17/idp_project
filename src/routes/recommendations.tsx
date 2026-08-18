import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Compass,
  Flame,
  HelpCircle,
  Lightbulb,
  Sparkles,
  TrendingDown,
  Wand2,
} from "lucide-react";
import { recommendationsQuery, topicsQuery, coursesQuery } from "@/lib/cognivue";
import { Panel, PanelHeader, MasteryPill } from "@/components/cognivue/primitives";
import { QuizGenerator } from "@/components/cognivue/QuizGenerator";

export const Route = createFileRoute("/recommendations")({
  head: () => ({
    meta: [
      { title: "Recommendations | Cognivue Insight" },
      {
        name: "description",
        content: "AI-ranked smart recommendations and high-yield retrieval targets",
      },
    ],
  }),
  component: RecommendationsScreen,
});

function RecommendationsScreen() {
  const { data: recommendations = [] } = useQuery(recommendationsQuery);
  const { data: topics = [] } = useQuery(topicsQuery);
  const { data: courses = [] } = useQuery(coursesQuery);

  const [activeDrillTopic, setActiveDrillTopic] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">
            Smart Recommendations Engine
          </h1>
          <p className="text-xs text-muted-foreground">
            Ranked by expected mastery lift · Identifying compounding prerequisite weaknesses before
            advancing.
          </p>
        </div>
      </div>

      {/* Active Drill Generator Drawer/Banner */}
      {activeDrillTopic && (
        <Panel className="border-primary/50 bg-surface p-6 shadow-xl ring-1 ring-primary/20">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <span className="label-xs text-primary">RECOMMENDATION ACTION DRILL</span>
              <h2 className="font-display text-base font-bold text-foreground">
                Targeted Remediation · {activeDrillTopic}
              </h2>
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
            masteryScore={topics.find((t) => t.title === activeDrillTopic)?.mastery_score ?? 40}
          />
        </Panel>
      )}

      {/* Recommendations Cards Grid */}
      <div className="space-y-4">
        {recommendations.map((rec, index) => {
          const topicObj = topics.find((t) => t.id === rec.topic_id);
          const courseObj = courses.find((c) => c.id === topicObj?.course_id);
          const topicTitle = topicObj?.title || "Dynamic Programming";
          const courseTitle = courseObj?.title || "Data Structures & Algorithms";

          const isTopPriority = index === 0;

          return (
            <Panel
              key={rec.id}
              className={`p-5 transition-all ${
                isTopPriority ? "border-primary/50 shadow-md ring-1 ring-primary/20" : ""
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="num font-bold text-xs text-muted-foreground">
                      #{index + 1}
                    </span>
                    <span className="rounded bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary uppercase tracking-wide">
                      {rec.type.replace(/_/g, " ")}
                    </span>
                    {isTopPriority && (
                      <span className="flex items-center gap-1 rounded bg-warn/15 px-2 py-0.5 text-[10px] font-semibold text-warn">
                        <Flame className="h-3 w-3" /> Critical Priority
                      </span>
                    )}
                  </div>

                  <h3 className="font-display text-base font-bold text-foreground">{topicTitle}</h3>
                  <p className="text-xs text-muted-foreground">{courseTitle}</p>
                </div>

                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <span className="text-[10px] text-muted-foreground">IMPACT SCORE</span>
                    <div className="num text-xl font-bold text-warn">{rec.impact_score}/100</div>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] text-muted-foreground">ESTIMATED TIME</span>
                    <div className="num flex items-center justify-end gap-1 text-sm font-semibold text-foreground">
                      <Clock className="h-3.5 w-3.5 text-muted-foreground" />{" "}
                      {rec.estimated_minutes}m
                    </div>
                  </div>
                </div>
              </div>

              {/* Reasoning Box */}
              <div className="mt-4 rounded-md border border-border/80 bg-surface-2 p-3 text-xs leading-relaxed text-muted-foreground">
                <span className="font-semibold text-foreground">AI Pedagogical Rationale:</span>{" "}
                {rec.reasoning}
              </div>

              {/* Action Button */}
              <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
                {topicObj && <MasteryPill score={topicObj.mastery_score} />}
                <button
                  onClick={() => setActiveDrillTopic(topicTitle)}
                  className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition hover:bg-primary/90"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  Launch Practice Drill
                </button>
              </div>
            </Panel>
          );
        })}
      </div>
    </div>
  );
}
