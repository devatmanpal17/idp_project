import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, Cpu, Database, Gauge, Loader2, Sparkles, Wand2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Panel } from "./primitives";

type Step = {
  key: string;
  label: string;
  detail: string;
  icon: typeof Database;
  lines: string[];
};

const STEPS: Step[] = [
  {
    key: "retrieve",
    label: "Retrieving context chunks",
    detail: "vector search · top_k=6 · cosine",
    icon: Database,
    lines: [
      "chunk_0417  sim=0.912  “…the kernel trick maps inputs implicitly…”",
      "chunk_0419  sim=0.887  “…support vectors define the margin…”",
      "chunk_0512  sim=0.841  “…soft-margin C controls tolerance…”",
      "chunk_0388  sim=0.803  “…RBF vs polynomial kernels…”",
    ],
  },
  {
    key: "signals",
    label: "Loading learner signals",
    detail: "mastery · error history · dwell time",
    icon: Gauge,
    lines: [
      "mastery_score      = 41",
      "quiz_perf_pct      = 36   (weight 0.40)",
      "time_on_section    = 48   (weight 0.35)",
      "revisit_frequency  = 40   (weight 0.25)",
      "recent_errors      = ['kernel_trick', 'margin_definition']",
    ],
  },
  {
    key: "calibrate",
    label: "Calibrating difficulty",
    detail: "target success rate 0.70",
    icon: Cpu,
    lines: [
      "difficulty = clamp(mastery/100 + 0.15, 0.25, 0.85) → 0.56",
      "mix        = { mcq: 3, short_answer: 1 }",
      "focus      = concepts with error_recency < 7d",
    ],
  },
  {
    key: "generate",
    label: "Generating questions",
    detail: "structured output · schema-validated",
    icon: Sparkles,
    lines: [
      "prompt_tokens = 2,184   context_chunks = 6",
      "streaming completion…",
      "validating against QuizSchema… ok",
    ],
  },
];

export type GeneratedQuestion = { q: string; choices: string[]; answer: string; why: string };

const DEFAULT_QUESTIONS: GeneratedQuestion[] = [
  {
    q: "In a soft-margin SVM, increasing C causes the model to…",
    choices: [
      "Tolerate more margin violations",
      "Penalise misclassification more heavily",
      "Increase the number of kernels",
      "Reduce the feature dimension",
    ],
    answer: "Penalise misclassification more heavily",
    why: "C is the inverse regularisation strength: a large C pushes the optimiser toward a narrow margin with fewer violations.",
  },
  {
    q: "Which statement about support vectors is true?",
    choices: [
      "Every training point is a support vector",
      "Only points on or inside the margin affect the boundary",
      "Support vectors are chosen at random",
      "They are removed before training",
    ],
    answer: "Only points on or inside the margin affect the boundary",
    why: "Removing non-support vectors leaves the learned hyperplane unchanged — that sparsity is the defining property of an SVM.",
  },
  {
    q: "Short answer: why is the RBF kernel a reasonable default?",
    choices: [],
    answer: "It can model non-linear boundaries with a single width hyperparameter and behaves well without domain knowledge.",
    why: "The RBF kernel corresponds to an infinite-dimensional feature space, so it can separate most datasets while exposing only gamma to tune.",
  },
];

export function QuizGenerator({
  topicTitle,
  compact = false,
  questions = DEFAULT_QUESTIONS,
  onDone,
}: {
  topicTitle: string;
  compact?: boolean | undefined;
  questions?: GeneratedQuestion[] | undefined;
  onDone?: (() => void) | undefined;
}) {
  const [step, setStep] = useState(0);
  const done = step >= STEPS.length;

  useEffect(() => {
    if (done) {
      onDone?.();
      return;
    }
    const t = setTimeout(() => setStep((s) => s + 1), 1150);
    return () => clearTimeout(t);
  }, [step, done, onDone]);

  const visible = useMemo(() => STEPS.slice(0, Math.min(step + 1, STEPS.length)), [step]);

  return (
    <div className={cn("space-y-3", compact ? "text-[11px]" : "text-xs")}>
      <div className="flex items-center gap-2 text-muted-foreground">
        <Wand2 className="h-3.5 w-3.5 text-primary" />
        <span>
          RAG pipeline · <span className="text-foreground">{topicTitle}</span>
        </span>
      </div>

      <div className="space-y-1.5">
        {visible.map((s, i) => {
          const complete = i < step;
          const Icon = s.icon;
          return (
            <motion.div
              key={s.key}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
              className={cn(
                "rounded-md border border-border bg-surface-2 px-2.5 py-2",
                !complete && "border-primary/30",
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
                    {s.lines.map((l) => (
                      <div key={l} className="truncate">
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

      <AnimatePresence>
        {done && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-2"
          >
            <div className="label-xs">Generated questions</div>
            {questions.map((question, i) => (
              <Panel key={i} className="p-3">
                <div className="flex gap-2">
                  <span className="num text-[10px] text-muted-foreground">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div className="min-w-0 flex-1 space-y-2">
                    <p className="text-[13px] font-medium leading-snug text-foreground">
                      {question.q}
                    </p>
                    {question.choices.length > 0 ? (
                      <ul className="space-y-1">
                        {question.choices.map((c) => (
                          <li
                            key={c}
                            className={cn(
                              "rounded border border-border px-2 py-1 text-[11px]",
                              c === question.answer
                                ? "border-positive/40 bg-positive/8 text-positive"
                                : "text-muted-foreground",
                            )}
                          >
                            {c}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="rounded border border-positive/40 bg-positive/8 px-2 py-1 text-[11px] text-positive">
                        {question.answer}
                      </div>
                    )}
                    <p className="text-[11px] leading-relaxed text-muted-foreground">
                      {question.why}
                    </p>
                  </div>
                </div>
              </Panel>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
