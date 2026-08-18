import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/courses/")({
  head: () => ({
    meta: [
      { title: "Courses | Cognivue" },
      { name: "description", content: "List of your courses in Cognivue" },
    ]
  }),
  component: CoursesIndex,
});

function CoursesIndex() {
  return (
    <div className="panel p-6">
      <p className="text-muted-foreground">Select a course to view details.</p>
    </div>
  );
}
