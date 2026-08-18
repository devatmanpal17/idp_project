/**
 * ChaiGaram — Domain Constants
 */

import type { StudyEvent } from "./types";

export const SIGNAL_WEIGHTS = {
  quiz: 0.4,
  time: 0.35,
  revisit: 0.25,
} as const;

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
