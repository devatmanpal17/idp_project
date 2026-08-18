/**
 * Cognivue AI / RAG Types
 */

export type RAGChunk = {
  chunk_id: string;
  topic: string;
  course: string;
  timestamp: string;
  snippet: string;
  similarity: number;
  token_count?: number;
};

export type TelemetryStep = {
  step: string;
  label: string;
  detail: string;
  lines: string[];
};

export type RAGQuizResponse = {
  topic: string;
  mastery_score: number;
  calibration: {
    difficulty: number;
    target_success_rate: number;
    target_level: string;
    mix: Record<string, number>;
    formula: string;
  };
  telemetry_steps: TelemetryStep[];
  questions: Array<{
    q: string;
    choices: string[];
    answer: string;
    why: string;
  }>;
  total_time_ms: number;
};

export type QuizEvaluationResult = {
  score: number;
  correct_count: number;
  total_questions: number;
  evaluations: Array<{
    question: string;
    given_answer: string;
    expected_answer: string;
    is_correct: boolean;
    explanation: string;
  }>;
  previous_mastery: number;
  new_mastery: number;
  mastery_delta: number;
  feedback_summary: string;
};
