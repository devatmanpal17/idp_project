import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpenCheck,
  Check,
  Clock,
  LockKeyhole,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import {
  mistakesQuery,
  reviewMistake,
  type MistakeCard,
} from "@/lib/chaigaram";
import { Panel } from "@/components/chaigaram/primitives";

export const Route = createFileRoute("/mistakes")({
  head: () => ({ meta: [{ title: "Mistake Notebook | ChaiGaram" }] }),
  component: MistakeNotebookScreen,
});

function MistakeNotebookScreen() {
  const client = useQueryClient();
  const [includeScheduled, setIncludeScheduled] = useState(false);
  const [offset, setOffset] = useState(0);
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState("");
  const { data, error, isPending, isFetching, refetch } = useQuery(
    mistakesQuery(includeScheduled, offset),
  );
  const mutation = useMutation({
    mutationFn: ({
      card,
      outcome,
    }: {
      card: MistakeCard;
      outcome: "again" | "remembered";
    }) => reviewMistake(card.id, outcome, card.version),
    onSuccess: (card) => {
      setRevealed((previous) => {
        const next = new Set(previous);
        next.delete(card.id);
        return next;
      });
      setMessage(
        `Review saved. Next review: ${new Date(card.due_at).toLocaleString()}.`,
      );
      setOffset(0);
      void client.invalidateQueries({ queryKey: ["mistakes"] });
    },
    onError: () => {
      void client.invalidateQueries({ queryKey: ["mistakes"] });
    },
  });
  const changeView = (all: boolean) => {
    setIncludeScheduled(all);
    setOffset(0);
    setRevealed(new Set());
    setMessage("");
  };

  return (
    <div className="space-y-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="label-xs mb-2 text-primary">LEARN FROM YOUR MISTAKES</p>
          <h1 className="font-display text-2xl font-bold tracking-tight">
            Mistake Notebook
          </h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Missed quiz questions, ready for another try. Recall your answer
            before revealing the feedback.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-2 rounded-full border border-border px-4 py-2 text-xs disabled:opacity-50"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`}
          />{" "}
          Refresh
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          ["Due for review", data?.summary.due],
          ["Saved mistakes", data?.summary.total],
          ["Cards reviewed", data?.summary.reviewed],
        ].map(([label, count]) => (
          <Panel key={String(label)} className="p-5">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="mt-2 font-display text-2xl font-semibold">
              {count ?? "—"}
            </p>
          </Panel>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          className="flex rounded-full border border-border p-1"
          aria-label="Review filter"
        >
          {(
            [
              [false, "Due now"],
              [true, "All cards"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={String(label)}
              type="button"
              aria-pressed={includeScheduled === value}
              onClick={() => changeView(Boolean(value))}
              className={`rounded-full px-4 py-1.5 text-xs ${includeScheduled === value ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          Self-review schedules practice; it does not change quiz mastery.
        </p>
      </div>

      {message && (
        <p
          role="status"
          className="rounded-xl border border-positive/30 bg-positive/5 p-4 text-sm text-positive"
        >
          {message}
        </p>
      )}
      {(error || mutation.error) && (
        <div
          role="alert"
          className="rounded-xl border border-warn/30 p-4 text-sm text-warn"
        >
          {(error || mutation.error)?.message}
        </div>
      )}
      {isPending && (
        <p className="text-sm text-muted-foreground">
          Loading your review cards…
        </p>
      )}
      {data && data.total === 0 && (
        <Panel className="p-8 text-center">
          <BookOpenCheck className="mx-auto mb-4 h-8 w-8 text-primary" />
          <h2 className="font-display text-lg font-semibold">
            {data.summary.total
              ? "You're up to date"
              : "Your next mistake can become progress"}
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            {data.summary.total
              ? "No reviews are due. Open All cards to revisit saved feedback."
              : "Complete a practice quiz. Missed questions appear here automatically, with the original feedback."}
          </p>
          <Link
            to="/quizzes"
            className="mt-5 inline-flex rounded-full bg-primary px-5 py-2 text-sm text-primary-foreground"
          >
            Start a practice quiz
          </Link>
        </Panel>
      )}

      <div className="space-y-4">
        {data?.items.map((card) => (
          <Panel
            key={`${card.id}-${card.version}`}
            className="overflow-hidden p-5 sm:p-6"
            data-review-card={card.id}
          >
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <span className="font-semibold text-primary">{card.topic}</span>
              <span className="inline-flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" />
                {new Date(card.due_at).getTime() <=
                new Date(data.server_time).getTime()
                  ? "Due now"
                  : `Due ${new Date(card.due_at).toLocaleDateString()}`}
                {card.review_count > 0 &&
                  ` · ${card.review_count} review${card.review_count === 1 ? "" : "s"}`}
              </span>
            </div>
            {card.locked ? (
              <div className="flex items-center gap-3 text-sm text-muted-foreground">
                <LockKeyhole className="h-5 w-5 shrink-0" /> This material is
                held by an open quiz. Submit or abandon that quiz to review it.
              </div>
            ) : (
              <>
                <h2 className="whitespace-pre-wrap break-words text-base font-semibold">
                  {card.question}
                </h2>
                {revealed.has(card.id) ? (
                  <>
                    <div className="mt-5 space-y-3 rounded-xl border border-border bg-surface-2 p-4 text-sm">
                      <p className="break-words">
                        <span className="text-muted-foreground">
                          Your quiz answer:{" "}
                        </span>
                        {card.given_answer || "No answer"}
                      </p>
                      <p className="break-words">
                        <span className="font-semibold text-positive">
                          Expected answer:{" "}
                        </span>
                        {card.expected_answer}
                      </p>
                      <p className="whitespace-pre-wrap break-words text-muted-foreground">
                        {card.explanation}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Saved quiz feedback
                        {card.bloom_level ? ` · ${card.bloom_level}` : ""}
                        {card.citation_count
                          ? ` · ${card.citation_count} source reference${card.citation_count === 1 ? "" : "s"}`
                          : ""}
                      </p>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-3">
                      <button
                        type="button"
                        disabled={mutation.isPending}
                        onClick={() =>
                          mutation.mutate({ card, outcome: "again" })
                        }
                        className="inline-flex items-center gap-2 rounded-full border border-border px-4 py-2 text-xs disabled:opacity-50"
                      >
                        <RotateCcw className="h-3.5 w-3.5" /> Again · 10 minutes
                      </button>
                      <button
                        type="button"
                        disabled={mutation.isPending}
                        onClick={() =>
                          mutation.mutate({ card, outcome: "remembered" })
                        }
                        className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-xs text-primary-foreground disabled:opacity-50"
                      >
                        <Check className="h-3.5 w-3.5" /> Remembered
                      </button>
                    </div>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() =>
                      setRevealed((previous) => new Set(previous).add(card.id))
                    }
                    className="mt-5 rounded-full border border-primary/40 px-4 py-2 text-xs text-primary"
                  >
                    Reveal feedback
                  </button>
                )}
              </>
            )}
          </Panel>
        ))}
      </div>

      {data && data.total > data.limit && (
        <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => {
              setOffset(Math.max(0, offset - data.limit));
              setRevealed(new Set());
            }}
            className="rounded-full border border-border px-4 py-2 disabled:opacity-40"
          >
            Previous
          </button>
          <span>
            {offset + 1}–{Math.min(offset + data.limit, data.total)} of{" "}
            {data.total}
          </span>
          <button
            type="button"
            disabled={offset + data.limit >= data.total}
            onClick={() => {
              setOffset(offset + data.limit);
              setRevealed(new Set());
            }}
            className="rounded-full border border-border px-4 py-2 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
