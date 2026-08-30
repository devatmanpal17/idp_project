/** React Query options backed entirely by FastAPI learning telemetry. */

import { queryOptions } from "@tanstack/react-query";
import { apiJSON } from "./api";
import type {
  ActivityEntry,
  Course,
  HistoryEntry,
  Quiz,
  Recommendation,
  StudyEvent,
  Topic,
} from "./types";

type LearningData = {
  courses: Course[];
  topics: Topic[];
  quizzes: Quiz[];
  study_events: StudyEvent[];
  recommendations: Recommendation[];
  activity_log: ActivityEntry[];
  history: HistoryEntry[];
};

async function fetchLearningData(): Promise<LearningData> {
  return apiJSON<LearningData>("/learning/data");
}

const base = {
  queryKey: ["learning-data"] as const,
  queryFn: fetchLearningData,
  staleTime: 5_000,
  refetchInterval: 15_000,
};

export const learningDataQuery = queryOptions(base);
export const coursesQuery = queryOptions({
  ...base,
  select: (data) => data.courses,
});
export const topicsQuery = queryOptions({
  ...base,
  select: (data) => data.topics,
});
export const quizzesQuery = queryOptions({
  ...base,
  select: (data) => data.quizzes,
});
export const studyEventsQuery = queryOptions({
  ...base,
  select: (data) => data.study_events,
});
export const recommendationsQuery = queryOptions({
  ...base,
  select: (data) => data.recommendations,
});
export const activityQuery = queryOptions({
  ...base,
  select: (data) => data.activity_log,
});
export const historyQuery = queryOptions({
  ...base,
  select: (data) => data.history,
});

export function deleteHistoryEntry(historyId: string) {
  return apiJSON<{
    status: string;
    removed_documents: number;
    removed_chunks: number;
    removed_topics: string[];
  }>(`/learning/history/${encodeURIComponent(historyId)}`, {
    method: "DELETE",
  });
}
