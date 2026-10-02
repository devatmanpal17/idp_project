/** Check external payloads before they enter rendering state. */
import { z } from "zod";

const number = z.number().finite();
const strings = z.array(z.string());

export const quizContract = z.object({
  quiz_id: z.string().min(1),
  topic: z.string(),
  mastery_score: number,
  active_provider: z.string().optional(),
  calibration: z.object({
    difficulty: number,
    target_success_rate: number,
    target_level: z.string(),
    mix: z.record(number),
    formula: z.string(),
  }),
  telemetry_steps: z.array(
    z.object({
      step: z.string(),
      label: z.string(),
      detail: z.string(),
      lines: strings,
    }),
  ),
  questions: z
    .array(
      z.object({
        question_id: z.string().min(1),
        q: z.string().min(1),
        choices: strings.min(2),
        citations: strings,
        bloom_level: z.string(),
      }),
    )
    .min(1),
  graphs: z
    .object({
      similarity_chart: z.array(
        z.object({
          chunk_id: z.string(),
          similarity: number,
          timestamp: z.string(),
          topic: z.string(),
          token_count: number,
        }),
      ),
      irt_curve: z.array(
        z.object({
          mastery: number,
          success_probability: number,
          current_learner: z.boolean(),
        }),
      ),
      cognitive_dimensions: z.array(
        z.object({ dimension: z.string(), weight: number, target: number }),
      ),
      concept_graph: z.object({
        nodes: z.array(
          z.object({
            id: z.string(),
            label: z.string(),
            group: z.string(),
            size: number,
            similarity: number.optional(),
          }),
        ),
        links: z.array(
          z.object({ source: z.string(), target: z.string(), value: number }),
        ),
      }),
    })
    .optional(),
  total_time_ms: number,
});

export const evaluationContract = z.object({
  attempt_id: number,
  score: number,
  correct_count: number,
  total_questions: number,
  evaluations: z.array(
    z.object({
      question: z.string(),
      given_answer: z.string(),
      expected_answer: z.string(),
      is_correct: z.boolean(),
      explanation: z.string(),
      citations: strings,
      bloom_level: z.string(),
    }),
  ),
  previous_mastery: number,
  new_mastery: number,
  mastery_delta: number,
  feedback_summary: z.string(),
  mastery_shift_chart: z
    .array(z.object({ metric: z.string(), value: number, fill: z.string() }))
    .optional(),
  mastery_history: z
    .array(
      z.object({
        id: number,
        completed_at: z.string(),
        score: number,
        previous_mastery: number,
        new_mastery: number,
      }),
    )
    .optional(),
});

export const answerContract = z.object({
  answer: z.string(),
  sources: z.array(
    z.object({
      chunk_id: z.string(),
      topic: z.string().optional(),
      course: z.string().optional(),
    }),
  ),
});

export function checkedPayload<T>(
  value: T,
  schema: z.ZodTypeAny,
  label: string,
): T {
  if (!schema.safeParse(value).success) {
    throw new Error(
      `The API returned an invalid ${label} response. Refresh and check the backend version.`,
    );
  }
  return value;
}
