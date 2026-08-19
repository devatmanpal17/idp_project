/**
 * ChaiGaram — React Query Options
 */

import { queryOptions } from "@tanstack/react-query";
import type {
  Course,
  Topic,
  Quiz,
  StudyEvent,
  Recommendation,
  ActivityEntry,
} from "./types";
import {
  MOCK_COURSES,
  MOCK_TOPICS,
  MOCK_QUIZZES,
  MOCK_STUDY_EVENTS,
  MOCK_RECOMMENDATIONS,
  MOCK_ACTIVITY,
} from "./mockData";

// Simulate network delay for a more realistic feel
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

async function fetchMock<T>(data: T[]): Promise<T[]> {
  await delay(150);
  return data;
}

export const coursesQuery = queryOptions({
  queryKey: ["courses"],
  queryFn: () => fetchMock<Course>(MOCK_COURSES),
});

export const topicsQuery = queryOptions({
  queryKey: ["topics"],
  queryFn: () => fetchMock<Topic>(MOCK_TOPICS),
});

export const quizzesQuery = queryOptions({
  queryKey: ["quizzes"],
  queryFn: () => fetchMock<Quiz>(MOCK_QUIZZES),
});

export const studyEventsQuery = queryOptions({
  queryKey: ["study_events"],
  queryFn: () => fetchMock<StudyEvent>(MOCK_STUDY_EVENTS),
});

export const recommendationsQuery = queryOptions({
  queryKey: ["recommendations"],
  queryFn: () => fetchMock<Recommendation>(MOCK_RECOMMENDATIONS),
});

export const activityQuery = queryOptions({
  queryKey: ["activity_log"],
  queryFn: () => fetchMock<ActivityEntry>(MOCK_ACTIVITY),
});
