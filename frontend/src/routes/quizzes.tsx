import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronRight,
  Clock,
  FileQuestion,
  HelpCircle,
  ListChecks,
  RotateCcw,
  Sparkles,
  Wand2,
  XCircle,
} from "lucide-react";
import { quizzesQuery, topicsQuery, coursesQuery, relativeTime, type Quiz } from "@/lib/chaigaram";
import { Panel, PanelHeader, MasteryPill } from "@/components/chaigaram/primitives";
import { QuizGenerator } from "@/components/chaigaram/QuizGenerator";

export const Route = createFileRoute("/quizzes")({
  head: () => ({
    meta: [
      { title: "Quizzes | ChaiGaram" },
      { name: "description", content: "AI RAG quiz generation, history, and assessment review" },
    ],
  }),
  component: QuizzesScreen,
});

function QuizzesScreen() {
  const { data: quizzes = [] } = useQuery(quizzesQuery);
  const { data: topics = [] } = useQuery(topicsQuery);
  const { data: courses = [] } = useQuery(coursesQuery);

  const [selectedQuiz, setSelectedQuiz] = useState<Quiz | null>(quizzes[0] || null);
  const [generatorOpen, setGeneratorOpen] = useState(false);
  const [quizTopic, setQuizTopic] = useState("Support Vector Machines");

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">
            Assessment Quizzes & RAG Generator
          </h1>
          <p className="text-xs text-muted-foreground">
            Active retrieval practice powered by lecture vector embeddings, difficulty calibration,
            and structured LLM validation.
          </p>
        </div>

        <button
          onClick={() => setGeneratorOpen(true)}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-3.5 py-2 text-xs font-medium text-primary-foreground shadow-sm transition hover:bg-primary/90"
        >
          <Wand2 className="h-4 w-4" />
          Generate New AI Practice Quiz
        </button>
      </div>

      {/* Generator Banner / Modal */}
      {generatorOpen && (
        <Panel className="border-primary/50 bg-surface p-6 shadow-xl ring-1 ring-primary/20">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <span className="label-xs text-primary">RETRIEVAL-AUGMENTED GENERATION</span>
              <h2 className="font-display text-base font-bold text-foreground">
                Generate Adaptive Practice Quiz
              </h2>
            </div>

            <div className="flex items-center gap-3">
              <select
                value={quizTopic}
                onChange={(e) => setQuizTopic(e.target.value)}
                className="rounded-md border border-border bg-surface-2 px-3 py-1.5 text-xs text-foreground focus:border-primary focus:outline-none"
              >
                {topics.map((t) => (
                  <option key={t.id} value={t.title}>
                    {t.title}
                  </option>
                ))}
              </select>

              <button
                onClick={() => setGeneratorOpen(false)}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Close
              </button>
            </div>
          </div>

          <QuizGenerator
            topicTitle={quizTopic}
            masteryScore={topics.find((t) => t.title === quizTopic)?.mastery_score ?? 45}
            onMasteryUpdated={(newScore) => {
              console.log("Mastery updated to:", newScore);
            }}
          />
        </Panel>
      )}

      {/* Main Grid: Quiz History (1 col) + Assessment Review Report (2 cols) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Quiz History List */}
        <Panel>
          <PanelHeader title="Past Assessments" subtitle={`${quizzes.length} completed sessions`} />
          <div className="divide-y divide-border p-2">
            {quizzes.map((quiz) => {
              const topicObj = topics.find((t) => t.id === quiz.topic_id);
              const courseObj = courses.find((c) => c.id === quiz.course_id);
              const isSelected = selectedQuiz?.id === quiz.id;

              return (
                <div
                  key={quiz.id}
                  onClick={() => setSelectedQuiz(quiz)}
                  className={`cursor-pointer rounded-md p-3 transition-colors ${
                    isSelected ? "border border-primary/40 bg-primary/10" : "hover:bg-surface-2"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-foreground">
                      {topicObj?.title || "Topic Assessment"}
                    </span>
                    <span
                      className={`num rounded px-2 py-0.5 text-[11px] font-bold ${
                        quiz.score >= 70
                          ? "bg-positive/15 text-positive"
                          : quiz.score >= 40
                            ? "bg-primary/15 text-primary"
                            : "bg-warn/15 text-warn"
                      }`}
                    >
                      {quiz.score}%
                    </span>
                  </div>

                  <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>{courseObj?.title || "Course"}</span>
                    <span className="num">{relativeTime(quiz.completed_at)}</span>
                  </div>

                  <div className="mt-2 flex items-center justify-between text-[10px] text-muted-foreground">
                    <span className="capitalize">{quiz.question_type} format</span>
                    <span>{quiz.questions?.length || 2} questions</span>
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>

        {/* Selected Quiz Assessment Review Report (2 cols) */}
        <Panel className="lg:col-span-2">
          <PanelHeader
            title="Assessment Report & LLM Explanations"
            subtitle="Pedagogical breakdown with cited context reasoning"
            action={
              selectedQuiz && (
                <span className="num text-xs font-semibold text-primary">
                  Score: {selectedQuiz.score}%
                </span>
              )
            }
          />

          {selectedQuiz ? (
            <div className="space-y-4 p-5">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
                <div>
                  <h3 className="font-display text-sm font-bold text-foreground">
                    {topics.find((t) => t.id === selectedQuiz.topic_id)?.title || "Assessment"}
                  </h3>
                  <p className="text-[11px] text-muted-foreground">
                    Completed {relativeTime(selectedQuiz.completed_at)} · Type:{" "}
                    {selectedQuiz.question_type}
                  </p>
                </div>

                <button
                  onClick={() => {
                    setQuizTopic(
                      topics.find((t) => t.id === selectedQuiz.topic_id)?.title ||
                        "Support Vector Machines",
                    );
                    setGeneratorOpen(true);
                  }}
                  className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                >
                  <RotateCcw className="h-3.5 w-3.5" /> Retake adaptive version
                </button>
              </div>

              {/* Questions Breakdown */}
              <div className="space-y-4">
                {selectedQuiz.questions.map((q, idx) => (
                  <div
                    key={idx}
                    className="rounded-lg border border-border bg-surface-2 p-4 space-y-2.5"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-2">
                        <span className="num text-xs font-bold text-muted-foreground">
                          {String(idx + 1).padStart(2, "0")}.
                        </span>
                        <p className="text-xs font-semibold text-foreground">{q.q}</p>
                      </div>
                      {q.correct ? (
                        <span className="inline-flex items-center gap-1 rounded bg-positive/15 px-2 py-0.5 text-[10px] font-semibold text-positive">
                          <CheckCircle2 className="h-3 w-3" /> Correct
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded bg-warn/15 px-2 py-0.5 text-[10px] font-semibold text-warn">
                          <XCircle className="h-3 w-3" /> Incorrect
                        </span>
                      )}
                    </div>

                    {/* Choices if any */}
                    {q.choices && (
                      <div className="grid gap-1 pl-4">
                        {q.choices.map((c) => (
                          <div
                            key={c}
                            className={`rounded border px-2.5 py-1 text-[11px] ${
                              c === q.answer
                                ? "border-positive/40 bg-positive/10 text-positive font-medium"
                                : c === q.given && !q.correct
                                  ? "border-warn/40 bg-warn/10 text-warn"
                                  : "border-border text-muted-foreground"
                            }`}
                          >
                            {c} {c === q.answer && " ✓ (Correct)"}{" "}
                            {c === q.given && !q.correct && " ✗ (Given Answer)"}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Short Answer Display */}
                    {!q.choices && (
                      <div className="space-y-1 pl-4 text-xs">
                        <p className="text-muted-foreground">
                          <span className="font-medium text-foreground">Your answer:</span>{" "}
                          {q.given}
                        </p>
                        <p className="text-positive">
                          <span className="font-medium">Model answer:</span> {q.answer}
                        </p>
                      </div>
                    )}

                    {/* LLM Explanation Box */}
                    <div className="rounded border border-border/60 bg-surface p-2.5 text-[11px] leading-relaxed text-muted-foreground">
                      <span className="font-semibold text-foreground">LLM Explanation:</span>{" "}
                      {q.explanation}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="p-8 text-center text-xs text-muted-foreground">
              Select a quiz from history to view full assessment report.
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
