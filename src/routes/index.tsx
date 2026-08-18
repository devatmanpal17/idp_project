import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Overview | Cognivue" },
      { name: "description", content: "Overview dashboard for Cognivue Insight" },
    ]
  }),
  component: Index,
});

function Index() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Overview</h1>
        <p className="text-muted-foreground">Your learning activity at a glance.</p>
      </div>
      <div className="panel p-6">
        <p className="text-muted-foreground">Overview content will appear here.</p>
      </div>
    </div>
  );
}
