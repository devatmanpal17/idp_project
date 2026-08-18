import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Check,
  Cpu,
  Database,
  Gauge,
  Loader2,
  Sparkles,
  Wand2,
  CheckCircle2,
  XCircle,
  RotateCcw,
  SendHorizontal,
  BarChart3,
  TrendingUp,
  BrainCircuit,
  Network,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import {
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from "recharts";
import { cn } from "@/lib/utils";
import { Panel } from "./primitives";
import {
  generateRAGQuiz,
  evaluateRAGQuiz,
  type RAGQuizResponse,
  type QuizEvaluationResult,
} from "@/lib/ai-client";

export type GeneratedQuestion = {
  q: string;
  choices: string[];
  answer: string;
  why: string;
};

const STEP_ICONS: Record<string, typeof Database> = {
  retrieve: Database,
  signals: Gauge,
  calibrate: Cpu,
  generate: Sparkles,
};

export function QuizGenerator({
  topicTitle,
  masteryScore = 41,
  compact = false,
  onDone,
  onMasteryUpdated,
}: {
  topicTitle: string;
  masteryScore?: number;
  compact?: boolean | undefined;
  onDone?: (() => void) | undefined;
  onMasteryUpdated?: ((newMastery: number) => void) | undefined;
}) {
  const [loading, setLoading] = useState(true);
  const [quizData, setQuizData] = useState<RAGQuizResponse | null>(null);
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<"generating" | "answering" | "results">("generating");
  const [activeGraphTab, setActiveGraphTab] = useState<"similarity" | "irt" | "bloom" | "concept">("similarity");
  const [showGraphs, setShowGraphs] = useState(true);

  // User responses
  const [userAnswers, setUserAnswers] = useState<string[]>([]);
  const [evaluation, setEvaluation] = useState<QuizEvaluationResult | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Fetch from Python RAG backend
  useEffect(() => {
    let isMounted = true;
    async function load() {
      setLoading(true);
      setStep(0);
      setMode("generating");
      setUserAnswers([]);
      setEvaluation(null);

      try {
        const data = await generateRAGQuiz({
          topic: topicTitle,
          mastery_score: masteryScore,
        });
        if (isMounted) {
          setQuizData(data);
          setUserAnswers(new Array(data.questions.length).fill(""));
        }
      } catch (err) {
        console.error("Quiz RAG generation error:", err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    load();
    return () => {
      isMounted = false;
    };
  }, [topicTitle, masteryScore]);

  // Step ticker animation
  const totalSteps = quizData?.telemetry_steps.length ?? 4;
  const isStepsDone = step >= totalSteps;

  useEffect(() => {
    if (loading || !quizData) return;
    if (isStepsDone) {
      onDone?.();
      return;
    }
    const t = setTimeout(() => setStep((s) => s + 1), 600);
    return () => clearTimeout(t);
  }, [step, isStepsDone, loading, quizData, onDone]);

  const visibleSteps = useMemo(() => {
    if (!quizData) return [];
    return quizData.telemetry_steps.slice(0, Math.min(step + 1, totalSteps));
  }, [quizData, step, totalSteps]);

  const handleSelectChoice = (qIndex: number, choice: string) => {
    setUserAnswers((prev) => {
      const next = [...prev];
      next[qIndex] = choice;
      return next;
    });
  };

  const handleSubmitQuiz = async () => {
    if (!quizData) return;
    setSubmitting(true);
    try {
      const res = await evaluateRAGQuiz({
        topic: topicTitle,
        questions: quizData.questions,
        given_answers: userAnswers,
        current_mastery: masteryScore,
      });
      setEvaluation(res);
      setMode("results");
      onMasteryUpdated?.(res.new_mastery);
    } catch (err) {
      console.error("Evaluation error:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={cn("space-y-3.5", compact ? "text-[11px]" : "text-xs")}>
      {/* Top Header & Engine Status */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Wand2 className="h-4 w-4 text-primary animate-pulse" />
          <span className="font-semibold text-foreground">
            Adaptive RAG Quiz · {topicTitle}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {quizData && (
            <>
              <span className="num rounded bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                {quizData.active_provider || "OpenAI GPT-4o-mini / RAG"}
              </span>
              <span className="num rounded bg-surface-2 px-2 py-0.5 text-[10px] text-muted-foreground">
                diff: {quizData.calibration.difficulty}
              </span>
              <span className="num rounded bg-surface-2 px-2 py-0.5 text-[10px] text-muted-foreground">
                {quizData.total_time_ms}ms
              </span>
            </>
          )}
        </div>
      </div>

      {/* RAG Telemetry Execution Pipeline */}
      <div className="space-y-1.5">
        {visibleSteps.map((s, i) => {
          const complete = i < step;
          const Icon = STEP_ICONS[s.step] || Database;
          return (
            <motion.div
              key={s.step}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className={cn(
                "rounded-md border border-border bg-surface-2 px-3 py-2",
                !complete && "border-primary/50 shadow-sm ring-1 ring-primary/20",
              )}
            >
              <div className="flex items-center gap-2">
                {complete ? (
                  <Check className="h-3.5 w-3.5 text-positive" />
                ) : (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                )}
                <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="font-medium text-foreground">{s.label}</span>
                <span className="num ml-auto text-[10px] text-muted-foreground">{s.detail}</span>
              </div>
              <AnimatePresence>
                {(complete || i === step) && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    className="num mt-1.5 space-y-0.5 overflow-hidden pl-6 text-[10px] leading-relaxed text-muted-foreground"
                  >
                    {s.lines.map((l, idx) => (
                      <div key={idx} className="truncate">
                        {l}
                      </div>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>

      {/* Dynamic Graphs & RAG Intelligence Panel */}
      {isStepsDone && quizData?.graphs && (
        <Panel className="overflow-hidden border border-border/80 bg-surface/80 p-3">
          <div className="flex items-center justify-between border-b border-border/60 pb-2">
            <div className="flex items-center gap-2">
              <BrainCircuit className="h-3.5 w-3.5 text-accent" />
              <span className="text-[11px] font-semibold text-foreground">
                RAG & Educational Assessment Graphs
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setShowGraphs(!showGraphs)}
                className="flex items-center gap-1 rounded px-2 py-0.5 text-[10px] text-muted-foreground hover:bg-surface-2 hover:text-foreground"
              >
                {showGraphs ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                {showGraphs ? "Collapse" : "Expand"}
              </button>
            </div>
          </div>

          {showGraphs && (
            <div className="mt-2 space-y-3">
              {/* Tab Selector */}
              <div className="flex flex-wrap gap-1 border-b border-border/40 pb-2 text-[10px]">
                <button
                  type="button"
                  onClick={() => setActiveGraphTab("similarity")}
                  className={cn(
                    "flex items-center gap-1 rounded px-2 py-1 font-medium transition",
                    activeGraphTab === "similarity"
                      ? "bg-primary text-primary-foreground"
                      : "bg-surface-2 text-muted-foreground hover:text-foreground",
                  )}
                >
                  <BarChart3 className="h-3 w-3" />
                  Vector Similarities
                </button>
                <button
                  type="button"
                  onClick={() => setActiveGraphTab("irt")}
                  className={cn(
                    "flex items-center gap-1 rounded px-2 py-1 font-medium transition",
                    activeGraphTab === "irt"
                      ? "bg-primary text-primary-foreground"
                      : "bg-surface-2 text-muted-foreground hover:text-foreground",
                  )}
                >
                  <TrendingUp className="h-3 w-3" />
                  IRT Mastery Curve
                </button>
                <button
                  type="button"
                  onClick={() => setActiveGraphTab("bloom")}
                  className={cn(
                    "flex items-center gap-1 rounded px-2 py-1 font-medium transition",
                    activeGraphTab === "bloom"
                      ? "bg-primary text-primary-foreground"
                      : "bg-surface-2 text-muted-foreground hover:text-foreground",
                  )}
                >
                  <BrainCircuit className="h-3 w-3" />
                  Bloom Cognitive Load
                </button>
                <button
                  type="button"
                  onClick={() => setActiveGraphTab("concept")}
                  className={cn(
                    "flex items-center gap-1 rounded px-2 py-1 font-medium transition",
                    activeGraphTab === "concept"
                      ? "bg-primary text-primary-foreground"
                      : "bg-surface-2 text-muted-foreground hover:text-foreground",
                  )}
                >
                  <Network className="h-3 w-3" />
                  Knowledge Graph
                </button>
              </div>

              {/* Tab 1: Vector Cosine Similarities Chart */}
              {activeGraphTab === "similarity" && (
                <div>
                  <div className="mb-1 flex items-center justify-between text-[10px] text-muted-foreground">
                    <span>Retrieved Lecture Transcript Chunks (TF-IDF Cosine Match %)</span>
                    <span className="font-mono text-primary">Top Match: {quizData.graphs.similarity_chart[0]?.similarity}%</span>
                  </div>
                  <div className="h-28 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={quizData.graphs.similarity_chart} margin={{ top: 5, right: 10, left: -25, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                        <XAxis dataKey="chunk_id" stroke="#71717a" fontSize={10} />
                        <YAxis domain={[50, 100]} stroke="#71717a" fontSize={10} />
                        <Tooltip
                          contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: "6px", fontSize: "11px" }}
                          formatter={(value: any) => [`${value}% match`, "Cosine Similarity"]}
                        />
                        <Bar dataKey="similarity" fill="#3b82f6" radius={[4, 4, 0, 0]}>
                          {quizData.graphs.similarity_chart.map((_, index) => (
                            <Cell key={`cell-${index}`} fill={index === 0 ? "#60a5fa" : "#3b82f6"} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Tab 2: IRT Characteristic Curve */}
              {activeGraphTab === "irt" && (
                <div>
                  <div className="mb-1 flex items-center justify-between text-[10px] text-muted-foreground">
                    <span>Item Response Theory (2PL) Characteristic Curve — P(Success | Mastery)</span>
                    <span className="font-mono text-warn">Target Difficulty: {quizData.calibration.difficulty}</span>
                  </div>
                  <div className="h-28 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={quizData.graphs.irt_curve} margin={{ top: 5, right: 10, left: -25, bottom: 0 }}>
                        <defs>
                          <linearGradient id="irtGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                            <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                        <XAxis dataKey="mastery" stroke="#71717a" fontSize={10} label={{ value: "Mastery Score", position: "insideBottom", offset: -2, fontSize: 9, fill: "#71717a" }} />
                        <YAxis domain={[0, 100]} stroke="#71717a" fontSize={10} />
                        <Tooltip
                          contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: "6px", fontSize: "11px" }}
                          formatter={(value: any) => [`${value}%`, "Expected Success Probability"]}
                        />
                        <Area type="monotone" dataKey="success_probability" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#irtGrad)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Tab 3: Bloom's Cognitive Load */}
              {activeGraphTab === "bloom" && (
                <div>
                  <div className="mb-1 flex items-center justify-between text-[10px] text-muted-foreground">
                    <span>Cognitive Demand Level Distribution (Bloom's Taxonomy)</span>
                    <span className="font-semibold text-foreground">{quizData.calibration.target_level}</span>
                  </div>
                  <div className="h-28 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={quizData.graphs.cognitive_dimensions} layout="vertical" margin={{ top: 0, right: 20, left: 10, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" horizontal={false} />
                        <XAxis type="number" domain={[0, 50]} stroke="#71717a" fontSize={10} />
                        <YAxis type="category" dataKey="dimension" stroke="#71717a" fontSize={10} width={65} />
                        <Tooltip
                          contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: "6px", fontSize: "11px" }}
                          formatter={(val: any) => [`${val}% weight`, "Cognitive Proportion"]}
                        />
                        <Bar dataKey="weight" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Tab 4: Concept Knowledge Graph */}
              {activeGraphTab === "concept" && (
                <div>
                  <div className="mb-1.5 text-[10px] text-muted-foreground">
                    Grounded Knowledge Nodes & Vector Associations
                  </div>
                  <div className="flex flex-wrap gap-2 pt-1">
                    {quizData.graphs.concept_graph.nodes.map((node) => (
                      <div
                        key={node.id}
                        className={cn(
                          "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px]",
                          node.group === "core"
                            ? "border-primary bg-primary/20 text-primary font-semibold"
                            : "border-border bg-surface-2 text-foreground",
                        )}
                      >
                        <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                        <span>{node.label}</span>
                        {node.similarity !== undefined && (
                          <span className="num text-[9px] text-muted-foreground">
                            {node.similarity}%
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </Panel>
      )}

      {/* Questions Section */}
      <AnimatePresence>
        {isStepsDone && quizData && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-3 pt-1"
          >
            <div className="flex items-center justify-between">
              <div className="label-xs font-semibold text-foreground">
                {mode === "results" ? "AI Evaluation & Score Breakdown" : "Generated Assessment Questions"}
              </div>
              <div className="text-[11px] text-muted-foreground">
                {quizData.questions.length} questions generated
              </div>
            </div>

            {/* Questions List */}
            <div className="space-y-2.5">
              {quizData.questions.map((question, qIdx) => {
                const evalItem = evaluation?.evaluations[qIdx];
                const selectedChoice = userAnswers[qIdx];

                return (
                  <Panel key={qIdx} className="p-3.5">
                    <div className="flex gap-2.5">
                      <span className="num text-[11px] font-semibold text-muted-foreground">
                        {String(qIdx + 1).padStart(2, "0")}
                      </span>
                      <div className="min-w-0 flex-1 space-y-2">
                        <p className="text-[13px] font-medium leading-snug text-foreground">
                          {question.q}
                        </p>

                        {/* Choices */}
                        {question.choices && question.choices.length > 0 ? (
                          <div className="grid gap-1.5">
                            {question.choices.map((c) => {
                              const isSelected = selectedChoice === c;
                              const isCorrect = evalItem?.expected_answer === c;
                              const isWrong = evalItem && isSelected && !evalItem.is_correct;

                              let choiceClass =
                                "border-border bg-surface hover:border-primary/50 text-foreground";
                              if (mode === "results") {
                                if (isCorrect) {
                                  choiceClass =
                                    "border-positive/50 bg-positive/10 text-positive font-medium";
                                } else if (isWrong) {
                                  choiceClass = "border-warn/50 bg-warn/10 text-warn";
                                } else {
                                  choiceClass = "border-border/50 opacity-60 text-muted-foreground";
                                }
                              } else if (isSelected) {
                                choiceClass =
                                  "border-primary bg-primary/10 text-primary font-medium";
                              }

                              return (
                                <button
                                  key={c}
                                  type="button"
                                  disabled={mode === "results"}
                                  onClick={() => handleSelectChoice(qIdx, c)}
                                  className={cn(
                                    "flex w-full items-start gap-2 rounded border px-3 py-2 text-left text-[11px] transition-all",
                                    choiceClass,
                                  )}
                                >
                                  <span className="num mt-0.5 text-[10px] opacity-70">
                                    {String.fromCharCode(65 + question.choices.indexOf(c))}.
                                  </span>
                                  <span className="flex-1">{c}</span>
                                  {mode === "results" && isCorrect && (
                                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-positive" />
                                  )}
                                  {mode === "results" && isWrong && (
                                    <XCircle className="h-3.5 w-3.5 shrink-0 text-warn" />
                                  )}
                                </button>
                              );
                            })}
                          </div>
                        ) : (
                          // Short Answer input
                          <div className="space-y-1">
                            <input
                              type="text"
                              disabled={mode === "results"}
                              value={selectedChoice || ""}
                              onChange={(e) => handleSelectChoice(qIdx, e.target.value)}
                              placeholder="Type your explanation or answer..."
                              className="w-full rounded border border-border bg-surface px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
                            />
                            {mode === "results" && (
                              <div className="rounded border border-positive/30 bg-positive/5 p-2 text-[11px] text-positive">
                                <span className="font-semibold">Model Answer:</span>{" "}
                                {question.answer}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Explanation in results mode */}
                        {mode === "results" && question.why && (
                          <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            className="rounded-md border border-border/80 bg-surface-2 p-2 text-[11px] leading-relaxed text-muted-foreground"
                          >
                            <span className="font-semibold text-foreground">
                              Pedagogical Grounding:
                            </span>{" "}
                            {question.why}
                          </motion.div>
                        )}
                      </div>
                    </div>
                  </Panel>
                );
              })}
            </div>

            {/* Results / Submit Actions */}
            {mode !== "results" ? (
              <div className="flex items-center justify-between pt-1">
                <span className="text-[11px] text-muted-foreground">
                  {userAnswers.filter(Boolean).length} of {quizData.questions.length} answered
                </span>
                <button
                  onClick={handleSubmitQuiz}
                  disabled={submitting || userAnswers.filter(Boolean).length === 0}
                  className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-xs font-medium text-primary-foreground shadow transition hover:bg-primary/90 disabled:opacity-50"
                >
                  {submitting ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <SendHorizontal className="h-3.5 w-3.5" />
                  )}
                  Submit for AI Evaluation
                </button>
              </div>
            ) : (
              evaluation && (
                <Panel className="border-primary/30 bg-primary/5 p-4 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="num text-2xl font-bold text-foreground">
                          {evaluation.score}%
                        </span>
                        <span className="num text-xs text-muted-foreground">
                          ({evaluation.correct_count}/{evaluation.total_questions} correct)
                        </span>
                        <span
                          className={cn(
                            "num rounded px-2 py-0.5 text-xs font-semibold",
                            evaluation.mastery_delta >= 0
                              ? "bg-positive/20 text-positive"
                              : "bg-warn/20 text-warn",
                          )}
                        >
                          {evaluation.mastery_delta >= 0 ? "+" : ""}
                          {evaluation.mastery_delta} Mastery
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {evaluation.feedback_summary}
                      </p>
                    </div>

                    <button
                      onClick={() => {
                        setMode("answering");
                        setUserAnswers(new Array(quizData.questions.length).fill(""));
                        setEvaluation(null);
                      }}
                      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-medium text-foreground hover:bg-surface-2"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      Retake Quiz
                    </button>
                  </div>

                  {/* Post-Quiz Bayesian Mastery Shift Graph */}
                  {evaluation.mastery_shift_chart && (
                    <div className="rounded-md border border-border bg-surface-2 p-3">
                      <div className="mb-1 flex items-center justify-between text-[10px] text-muted-foreground">
                        <span>Bayesian Mastery Shift & Trajectory Comparison</span>
                        <span className="font-semibold text-positive">
                          {evaluation.previous_mastery} → {evaluation.new_mastery}
                        </span>
                      </div>
                      <div className="h-24 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={evaluation.mastery_shift_chart} margin={{ top: 5, right: 10, left: -25, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                            <XAxis dataKey="metric" stroke="#71717a" fontSize={10} />
                            <YAxis domain={[0, 100]} stroke="#71717a" fontSize={10} />
                            <Tooltip
                              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: "6px", fontSize: "11px" }}
                              formatter={(value: any) => [`${value}`, "Score / Level"]}
                            />
                            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                              {evaluation.mastery_shift_chart.map((entry, index) => (
                                <Cell key={`shift-${index}`} fill={index === 0 ? "#818cf8" : index === 1 ? "#34d399" : "#38bdf8"} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}
                </Panel>
              )
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
