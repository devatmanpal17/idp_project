/**
 * ChaiGaram AI / RAG Types
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

export type SimilarityChartPoint = {
  chunk_id: string;
  similarity: number;
  timestamp: string;
  topic: string;
  token_count: number;
};

export type IRTCurvePoint = {
  mastery: number;
  success_probability: number;
  current_learner: boolean;
};

export type CognitiveDimension = {
  dimension: string;
  weight: number;
  target: number;
};

export type ConceptGraphData = {
  nodes: Array<{
    id: string;
    label: string;
    group: string;
    similarity?: number;
    size: number;
  }>;
  links: Array<{
    source: string;
    target: string;
    value: number;
  }>;
};

export type MasteryShiftPoint = {
  metric: string;
  value: number;
  fill: string;
};

export type RAGQuizResponse = {
  quiz_id: string;
  topic: string;
  mastery_score: number;
  active_provider?: string;
  calibration: {
    difficulty: number;
    target_success_rate: number;
    target_level: string;
    mix: Record<string, number>;
    formula: string;
  };
  telemetry_steps: TelemetryStep[];
  questions: Array<{
    question_id: string;
    q: string;
    choices: string[];
    citations: string[];
    bloom_level: string;
  }>;
  graphs?: {
    similarity_chart: SimilarityChartPoint[];
    irt_curve: IRTCurvePoint[];
    cognitive_dimensions: CognitiveDimension[];
    concept_graph: ConceptGraphData;
  };
  total_time_ms: number;
};

export type QuizEvaluationResult = {
  attempt_id: number;
  score: number;
  correct_count: number;
  total_questions: number;
  evaluations: Array<{
    question: string;
    given_answer: string;
    expected_answer: string;
    is_correct: boolean;
    explanation: string;
    citations: string[];
    bloom_level: string;
  }>;
  previous_mastery: number;
  new_mastery: number;
  mastery_delta: number;
  feedback_summary: string;
  mastery_shift_chart?: MasteryShiftPoint[];
  mastery_history?: Array<{
    id: number;
    completed_at: string;
    score: number;
    previous_mastery: number;
    new_mastery: number;
  }>;
};
