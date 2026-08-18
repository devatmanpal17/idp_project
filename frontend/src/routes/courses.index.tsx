import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, ChevronRight, Clock, Flame, GraduationCap } from "lucide-react";
import { coursesQuery, topicsQuery, PLATFORM_TINT } from "@/lib/chaigaram";
import { Panel, MasteryPill, Meter } from "@/components/chaigaram/primitives";

export const Route = createFileRoute("/courses/")({
  head: () => ({
    meta: [
      { title: "Courses | ChaiGaram" },
      { name: "description", content: "Active courses and video-comprehension tracking" },
    ],
  }),
  component: CoursesIndex,
});

function CoursesIndex() {
  const { data: courses = [] } = useQuery(coursesQuery);
  const { data: topics = [] } = useQuery(topicsQuery);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">
            Tracked Courses
          </h1>
          <p className="text-xs text-muted-foreground">
            DOM telemetry active across 5 course platforms · Monitoring video completion vs verified
            comprehension.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {courses.map((course) => {
          const courseTopics = topics.filter((t) => t.course_id === course.id);
          const platformColor = PLATFORM_TINT[course.platform] || "text-primary";

          return (
            <Link
              key={course.id}
              to="/courses/$courseId"
              params={{ courseId: course.id }}
              className="group block transition-transform hover:-translate-y-0.5"
            >
              <Panel className="flex h-full flex-col justify-between p-5 transition-colors group-hover:border-primary/50">
                <div>
                  <div className="flex items-center justify-between">
                    <span
                      className={`text-[11px] font-semibold uppercase tracking-wider ${platformColor}`}
                    >
                      {course.platform}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {courseTopics.length} modules
                    </span>
                  </div>

                  <h3 className="mt-2 text-base font-semibold text-foreground group-hover:text-primary">
                    {course.title}
                  </h3>

                  <div className="mt-4 space-y-3">
                    {/* Completion */}
                    <div>
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Video Watched</span>
                        <span className="num font-medium text-foreground">
                          {course.completion_pct}%
                        </span>
                      </div>
                      <Meter value={course.completion_pct} tone="accent" className="mt-1" />
                    </div>

                    {/* Mastery */}
                    <div>
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Comprehension Mastery</span>
                        <span className="num font-medium text-primary">
                          {course.overall_mastery}%
                        </span>
                      </div>
                      <Meter value={course.overall_mastery} tone="primary" className="mt-1" />
                    </div>
                  </div>
                </div>

                <div className="mt-5 flex items-center justify-between border-t border-border pt-3 text-xs text-muted-foreground">
                  <MasteryPill score={course.overall_mastery} />
                  <span className="inline-flex items-center gap-1 text-primary group-hover:underline">
                    View telemetry <ChevronRight className="h-3.5 w-3.5" />
                  </span>
                </div>
              </Panel>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
