/** HTTP client for the FastAPI ChromaDB + Ollama pipeline. */

import type { QuizEvaluationResult, RAGChunk, RAGQuizResponse } from "./types";
import { apiJSON } from "../api";

export interface AIHealth {
  status?: string;
  indexed_chunks?: number;
  active_ai_provider?: string;
  llm_service?: {
    model?: string;
    model_ready?: boolean;
  };
  embedding_service?: {
    embedding_model?: string;
    embedding_model_ready?: boolean;
  };
}

async function requestJSON<T>(path: string, init?: RequestInit): Promise<T> {
  return apiJSON<T>(path, init);
}

export function checkAIHealth() {
  return requestJSON<AIHealth>("/health");
}

export async function fetchIndexedTopics(): Promise<string[]> {
  const result = await requestJSON<{ topics: string[] }>("/rag/topics");
  return result.topics;
}

export function fetchTopicState(topic: string) {
  return requestJSON<{
    title: string;
    mastery_score: number;
    quiz_perf_pct: number;
    trend_delta: number;
    minutes_on_section: number;
    revisits: number;
    indexed_chunks: number;
    assessed: boolean;
  }>(`/learning/topic-state?topic=${encodeURIComponent(topic)}`);
}

export function ingestRAGDocument(params: {
  title: string;
  topic: string;
  course?: string;
  content: string;
}) {
  return requestJSON<{
    status: string;
    document_id: string;
    chunks_indexed: number;
    total_chunks: number;
  }>("/rag/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

export async function retrieveRAGChunks(
  topic: string,
  query = "",
  topK = 6,
): Promise<RAGChunk[]> {
  const result = await requestJSON<{ chunks: RAGChunk[] }>("/rag/retrieve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, query, top_k: topK }),
  });
  return result.chunks;
}

export function askRAGAssistant(params: {
  question: string;
  topic?: string;
  topK?: number;
  history?: Array<{ role: "user" | "assistant"; content: string }>;
  signal?: AbortSignal;
}) {
  return requestJSON<{
    answer: string;
    active_provider?: string;
    sources: RAGChunk[];
  }>("/rag/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: params.question,
      topic: params.topic || null,
      top_k: params.topK ?? 5,
      history: params.history ?? [],
    }),
    ...(params.signal ? { signal: params.signal } : {}),
  });
}

export function generateRAGQuiz(params: {
  topic: string;
  mastery_score?: number;
  quiz_perf_pct?: number;
  time_on_section_pct?: number;
  revisit_frequency_pct?: number;
  recent_errors?: string[];
  question_count?: number;
}): Promise<RAGQuizResponse> {
  return requestJSON<RAGQuizResponse>("/rag/generate-quiz", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      topic: params.topic,
      mastery_score: params.mastery_score ?? 0,
      quiz_perf_pct: params.quiz_perf_pct ?? 0,
      time_on_section_pct: params.time_on_section_pct ?? 0,
      revisit_frequency_pct: params.revisit_frequency_pct ?? 0,
      recent_errors: params.recent_errors ?? [],
      question_count: params.question_count ?? 3,
    }),
  });
}

export function evaluateRAGQuiz(params: {
  quiz_id: string;
  topic: string;
  given_answers: string[];
  current_mastery?: number;
}): Promise<QuizEvaluationResult> {
  return requestJSON<QuizEvaluationResult>("/rag/evaluate-quiz", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      quiz_id: params.quiz_id,
      topic: params.topic,
      given_answers: params.given_answers,
      current_mastery: params.current_mastery ?? 0,
    }),
  });
}

export function streamSimulatorTranscript(params: {
  video_title: string;
  timestamp: string;
  transcript_segment: string;
  current_topic: string;
  dwell_seconds?: number;
}) {
  return requestJSON<Record<string, unknown>>("/rag/stream-transcript", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

export async function fetchSmartRecommendations() {
  const result = await requestJSON<{ recommendations: unknown[] }>(
    "/recommendations/smart",
  );
  return result.recommendations;
}

export function updateAIConfig(params: {
  provider: string;
  api_key?: string;
  model?: string;
}) {
  return requestJSON<Record<string, unknown>>("/settings/ai-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}
