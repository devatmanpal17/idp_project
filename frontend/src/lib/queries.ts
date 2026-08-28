/** React Query options backed entirely by FastAPI learning telemetry. */

import { queryOptions } from "@tanstack/react-query";
import type { ActivityEntry, Course, Quiz, Recommendation, StudyEvent, Topic } from "./types";

type LearningData = {
  courses: Course[];
  topics: Topic[];
  quizzes: Quiz[];
  study_events: StudyEvent[];
  recommendations: Recommendation[];
  activity_log: ActivityEntry[];
};

async function fetchLearningData(): Promise<LearningData> {
  const response = await fetch("/api/learning/data");
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Learning data request failed (${response.status})`);
  }
  return response.json();
}

const base = {
  queryFn: fetchLearningData,
  staleTime: 5_000,
  refetchInterval: 15_000,
};

export const learningDataQuery = queryOptions({ ...base, queryKey: ["learning-data"] });
export const coursesQuery = queryOptions({
  ...base,
  queryKey: ["learning-data", "courses"],
  select: (data) => data.courses,
});
export const topicsQuery = queryOptions({
  ...base,
  queryKey: ["learning-data", "topics"],
  select: (data) => data.topics,
});
export const quizzesQuery = queryOptions({
  ...base,
  queryKey: ["learning-data", "quizzes"],
  select: (data) => data.quizzes,
});
export const studyEventsQuery = queryOptions({
  ...base,
  queryKey: ["learning-data", "study-events"],
  select: (data) => data.study_events,
});
export const recommendationsQuery = queryOptions({
  ...base,
  queryKey: ["learning-data", "recommendations"],
  select: (data) => data.recommendations,
});
export const activityQuery = queryOptions({
  ...base,
  queryKey: ["learning-data", "activity"],
  select: (data) => data.activity_log,
});
