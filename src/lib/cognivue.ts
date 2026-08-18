import { queryOptions } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";

export type Course = {
  id: string;
  title: string;
  platform: string;
  thumbnail_url: string | null;
  completion_pct: number;
  overall_mastery: number;
  created_at: string;
};

export type Topic = {
  id: string;
  course_id: string;
  title: string;
  mastery_score: number;
  quiz_perf_pct: number;
  time_on_section_pct: number;
  revisit_frequency_pct: number;
  trend_delta: number;
  minutes_on_section: number;
  revisits: number;
  last_updated: string;
};

export type QuizQuestion = {
  q: string;
  choices?: string[];
  answer: string;
  given: string;
  correct: boolean;
  explanation: string;
};

export type Quiz = {
  id: string;
  topic_id: string | null;
  course_id: string | null;
  question_type: string;
  questions: QuizQuestion[];
  score: number;
  completed_at: string;
};

export type StudyEvent = {
  id: string;
  topic_id: string | null;
  event_type: "review" | "quiz" | "study_block";
  scheduled_at: string;
  status: string;
};

export type Recommendation = {
  id: string;
  topic_id: string | null;
  type: string;
  impact_score: number;
  estimated_minutes: number;
  reasoning: string;
  created_at: string;
};

export type ActivityEntry = {
  id: string;
  course_id: string | null;
  event_type: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

const table = (name: string) => supabase.from(name as never);

async function fetchAll<T>(name: string, order: string, ascending = true): Promise<T[]> {
  const { data, error } = await table(name).select("*").order(order, { ascending });
  if (error) throw new Error(error.message);
  return (data ?? []) as T[];
}

export const coursesQuery = queryOptions({
  queryKey: ["courses"],
  queryFn: () => fetchAll<Course>("courses", "created_at"),
});

export const topicsQuery = queryOptions({
  queryKey: ["topics"],
  queryFn: () => fetchAll<Topic>("topics", "title"),
});

export const quizzesQuery = queryOptions({
  queryKey: ["quizzes"],
  queryFn: () => fetchAll<Quiz>("quizzes", "completed_at", false),
});

export const studyEventsQuery = queryOptions({
  queryKey: ["study_events"],
  queryFn: () => fetchAll<StudyEvent>("study_events", "scheduled_at"),
});

export const recommendationsQuery = queryOptions({
  queryKey: ["recommendations"],
  queryFn: () => fetchAll<Recommendation>("recommendations", "impact_score", false),
});

export const activityQuery = queryOptions({
  queryKey: ["activity_log"],
  queryFn: () => fetchAll<ActivityEntry>("activity_log", "created_at", false),
});

/* ---------- domain helpers ---------- */

export const SIGNAL_WEIGHTS = {
  quiz: 0.4,
  time: 0.35,
  revisit: 0.25,
} as const;

export function masteryBand(score: number) {
  if (score >= 75) return { label: "Strong", tone: "positive" as const };
  if (score >= 50) return { label: "Developing", tone: "primary" as const };
  return { label: "At risk", tone: "warn" as const };
}

export const PLATFORM_TINT: Record<string, string> = {
  Udemy: "text-warn",
  Coursera: "text-accent",
  edX: "text-primary",
};

export const EVENT_LABEL: Record<string, string> = {
  quiz_completed: "Quiz completed",
  topic_revisit: "Topic revisited",
  mastery_updated: "Mastery recalculated",
  calendar_event_created: "Calendar event created",
  transcript_captured: "Transcript captured",
};

export const STUDY_EVENT_META: Record<
  StudyEvent["event_type"],
  { label: string; color: string; dot: string }
> = {
  review: { label: "Review reminder", color: "text-primary", dot: "bg-primary" },
  quiz: { label: "Quiz session", color: "text-accent", dot: "bg-accent" },
  study_block: { label: "Study block", color: "text-warn", dot: "bg-warn" },
};

export function relativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60000);
  if (Math.abs(mins) < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (Math.abs(hours) < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/** Ebbinghaus-style retention decay: stronger mastery decays slower. */
export function retentionCurve(mastery: number, days: number, reviews: number[] = []) {
  const points: { day: number; retention: number }[] = [];
  let strength = 1 + mastery / 40;
  let lastReview = 0;
  for (let d = 0; d <= days; d++) {
    if (reviews.includes(d)) {
      strength += 1.4;
      lastReview = d;
    }
    const elapsed = d - lastReview;
    const retention = 100 * Math.exp(-elapsed / (strength * 2.2));
    points.push({ day: d, retention: Math.round(retention * 10) / 10 });
  }
  return points;
}
