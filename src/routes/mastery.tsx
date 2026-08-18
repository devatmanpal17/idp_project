import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/mastery")({
  head: () => ({
    meta: [
      { title: "Topic Mastery | Cognivue" },
      { name: "description", content: "Track your mastery across topics" },
    ]
  }),
  component: Mastery,
});

function Mastery() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Topic Mastery</h1>
        <p className="text-muted-foreground">Track your understanding and progress on various topics.</p>
      </div>
      <div className="panel p-6">
        <p className="text-muted-foreground">Mastery visualizations will appear here.</p>
      </div>
    </div>
  );
}
