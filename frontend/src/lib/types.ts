/**
 * ChaiGaram — Domain Type Definitions
 */

export type Course = {
  id: string;
  title: string;
  platform: string;
  thumbnail_url: string | null;
  source_url: string;
  last_visited_at: string;
  visit_count: number;
  completion_pct: number;
  overall_mastery: number;
  created_at: string;
};

export type Topic = {
  id: string;
  course_id: string;
  title: string;
  mastery_score: number;
  assessment_mastery?: number;
  quiz_perf_pct: number;
  time_on_section_pct: number;
  revisit_frequency_pct: number;
  trend_delta: number;
  minutes_on_section: number;
  revisits: number;
  last_updated: string;
  indexed_chunks?: number;
  assessed?: boolean;
  recall?: {
    method: "unassessed" | "cold_start_heuristic" | "fitted_assessment_model";
    probability: number | null;
    review_in_days: number;
    curve: Array<{ day: number; retention: number; review: boolean }>;
  };
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

export type HistoryEntry = {
  id: string;
  title: string;
  topics: string[];
  page_url: string;
  domain: string;
  platform: string;
  source_type: "document" | "video";
  first_visited_at: string;
  last_visited_at: string;
  visit_count: number;
  indexed_chunks: number;
  word_count: number;
  progress_pct: number;
};
