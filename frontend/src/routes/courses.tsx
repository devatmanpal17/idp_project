import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/courses")({
  component: CoursesLayout,
});

function CoursesLayout() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Courses</h1>
        <p className="text-muted-foreground">Manage and view your courses.</p>
      </div>
      <Outlet />
    </div>
  );
}
