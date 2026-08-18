import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/study-plan")({
  head: () => ({
    meta: [
      { title: "Study Plan | Cognivue" },
      { name: "description", content: "Your personalized study schedule" },
    ]
  }),
  component: StudyPlan,
});

function StudyPlan() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Study Plan</h1>
        <p className="text-muted-foreground">Your personalized path to mastery.</p>
      </div>
      <div className="panel p-6">
        <p className="text-muted-foreground">Study plan schedule will appear here.</p>
      </div>
    </div>
  );
}
