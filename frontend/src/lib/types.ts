/**
 * Cognivue — Domain Type Definitions
 */

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
