import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/recommendations")({
  head: () => ({
    meta: [
      { title: "Recommendations | Cognivue" },
      { name: "description", content: "Smart recommendations for your learning journey" },
    ]
  }),
  component: Recommendations,
});

function Recommendations() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Recommendations</h1>
        <p className="text-muted-foreground">Suggested resources based on your progress.</p>
      </div>
      <div className="panel p-6">
        <p className="text-muted-foreground">Smart recommendations will appear here.</p>
      </div>
    </div>
  );
}
