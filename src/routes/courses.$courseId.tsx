import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/courses/$courseId")({
  head: () => ({
    meta: [
      { title: "Course Details | Cognivue" },
      { name: "description", content: "Details for the selected course" },
    ]
  }),
  component: CourseDetail,
});

function CourseDetail() {
  const { courseId } = Route.useParams();
  
  return (
    <div className="panel p-6">
      <h2 className="text-xl font-semibold mb-4">Course {courseId}</h2>
      <p className="text-muted-foreground">Course details will appear here.</p>
    </div>
  );
}
