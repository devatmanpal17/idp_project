import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/quizzes")({
  head: () => ({
    meta: [
      { title: "Quizzes | Cognivue" },
      { name: "description", content: "Take quizzes to test your knowledge" },
    ]
  }),
  component: Quizzes,
});

function Quizzes() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Quizzes</h1>
        <p className="text-muted-foreground">Test your knowledge with personalized quizzes.</p>
      </div>
      <div className="panel p-6">
        <p className="text-muted-foreground">Quiz generation and history will appear here.</p>
      </div>
    </div>
  );
}
