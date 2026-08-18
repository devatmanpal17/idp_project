/**
 * ChaiGaram — React Query Options
 */

import { queryOptions } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import type {
  Course,
  Topic,
  Quiz,
  StudyEvent,
  Recommendation,
  ActivityEntry,
} from "./types";

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
