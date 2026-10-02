import { useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ExternalLink,
  FileText,
  History as HistoryIcon,
  Search,
  Trash2,
  Video,
} from "lucide-react";

import {
  EmptyState,
  PageHeader,
  Panel,
} from "@/components/chaigaram/primitives";
import { Input } from "@/components/ui/input";
import { deleteHistoryEntry, historyQuery } from "@/lib/queries";

export const Route = createFileRoute("/history")({
  head: () => ({
    meta: [
      { title: "Visit History | ChaiGaram" },
      {
        name: "description",
        content: "Learning websites, topics, and indexed source controls",
      },
    ],
  }),
  component: HistoryScreen,
});

function HistoryScreen() {
  const queryClient = useQueryClient();
  const { data: history = [], isLoading, error } = useQuery(historyQuery);
  const [search, setSearch] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    if (!needle) return history;
    return history.filter((entry) =>
      [entry.title, entry.domain, entry.platform, ...entry.topics]
        .join(" ")
        .toLocaleLowerCase()
        .includes(needle),
    );
  }, [history, search]);

  const removeEntry = useMutation({
    mutationFn: deleteHistoryEntry,
    onSuccess: async (result) => {
      setMessage(
        `Removed ${result.removed_chunks} indexed passage${result.removed_chunks === 1 ? "" : "s"}. This source will no longer be used for quizzes.`,
      );
      await queryClient.invalidateQueries({ queryKey: ["learning-data"] });
      await queryClient.invalidateQueries({ queryKey: ["mistakes"] });
    },
    onSettled: () => setDeletingId(null),
  });

  function confirmDelete(id: string, title: string) {
    const confirmed = window.confirm(
      `Delete “${title}” from ChaiGaram?\n\nIts indexed passages will be removed and will no longer be available to quizzes or recommendations.`,
    );
    if (!confirmed) return;
    setMessage(null);
    setDeletingId(id);
    removeEntry.mutate(id);
  }

  return (
    <div className="space-y-7">
      <PageHeader
        eyebrow="Your learning trail"
        title="Visit history"
        description="See the pages and videos captured by the extension. Delete a source to remove its indexed content from future quizzes, mastery, and recommendations."
        action={
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search sites or topics"
              className="pl-9"
            />
          </div>
        }
      />

      {message && (
        <div className="rounded-lg border border-positive/30 bg-positive/8 px-4 py-3 text-xs text-positive">
          {message}
        </div>
      )}
      {(error || removeEntry.error) && (
        <div
          role="alert"
          className="rounded-lg border border-destructive/30 bg-destructive/8 px-4 py-3 text-xs text-destructive"
        >
          {(error || removeEntry.error) instanceof Error
            ? (error || removeEntry.error)?.message
            : "History could not be updated."}
        </div>
      )}

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {[0, 1, 2, 3].map((item) => (
            <div
              key={item}
              className="h-44 animate-pulse rounded-xl bg-surface"
            />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Panel>
          <EmptyState
            icon={<HistoryIcon className="h-5 w-5" />}
            title={
              history.length
                ? "No history matches that search"
                : "No captured visits yet"
            }
            hint={
              history.length
                ? "Try a website name, course title, or topic."
                : "Open a learning page with the extension and capture its page text or video captions."
            }
          />
        </Panel>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {filtered.map((entry) => {
            const SourceIcon = entry.source_type === "video" ? Video : FileText;
            const deleting = deletingId === entry.id;
            return (
              <Panel key={entry.id} className="flex min-w-0 flex-col p-5">
                <div className="flex items-start gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                    <SourceIcon className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      <span>{entry.platform}</span>
                      <span>•</span>
                      <span className="truncate normal-case tracking-normal">
                        {entry.domain}
                      </span>
                    </div>
                    <h2 className="mt-1 line-clamp-2 text-sm font-semibold leading-5">
                      {entry.title}
                    </h2>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-1.5">
                  {entry.topics.map((topic) => (
                    <span
                      key={topic}
                      className="max-w-full truncate rounded-full bg-surface-2 px-2.5 py-1 text-[10px] text-muted-foreground"
                    >
                      {topic}
                    </span>
                  ))}
                </div>

                <div className="mt-4 grid grid-cols-3 gap-2 border-y border-border py-3 text-center">
                  <HistoryStat
                    label="Last visit"
                    value={formatDate(entry.last_visited_at)}
                  />
                  <HistoryStat
                    label="Captures"
                    value={String(entry.visit_count)}
                  />
                  <HistoryStat
                    label="Passages"
                    value={String(entry.indexed_chunks)}
                  />
                </div>

                <div className="mt-auto flex items-center justify-between gap-3 pt-4">
                  {entry.page_url ? (
                    <a
                      href={entry.page_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
                    >
                      Visit again <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      Saved document
                    </span>
                  )}
                  <button
                    type="button"
                    disabled={deleting}
                    onClick={() => confirmDelete(entry.id, entry.title)}
                    className="inline-flex items-center gap-1.5 rounded-md border border-destructive/30 px-3 py-1.5 text-xs font-medium text-destructive transition hover:bg-destructive/10 disabled:opacity-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />{" "}
                    {deleting ? "Deleting…" : "Delete"}
                  </button>
                </div>
              </Panel>
            );
          })}
        </div>
      )}
    </div>
  );
}

function HistoryStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[9px] uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 truncate text-[11px] font-semibold text-foreground">
        {value}
      </p>
    </div>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Unknown";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
  }).format(date);
}
