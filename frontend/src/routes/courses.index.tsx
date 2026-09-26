import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, ChevronRight, ExternalLink, History } from "lucide-react";
import { coursesQuery, topicsQuery, PLATFORM_TINT } from "@/lib/chaigaram";
import { Panel, MasteryPill, Meter } from "@/components/chaigaram/primitives";

export const Route = createFileRoute("/courses/")({
  head: () => ({
    meta: [
      { title: "Courses | ChaiGaram" },
      {
        name: "description",
        content: "Active courses and video-comprehension tracking",
      },
    ],
  }),
  component: CoursesIndex,
});

function CoursesIndex() {
  const { data: courses = [], isLoading, error } = useQuery(coursesQuery);
  const { data: topics = [] } = useQuery(topicsQuery);

  return (
    <div className="space-y-9">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">
            Tracked Courses
          </h1>
          <p className="text-xs text-muted-foreground">
            DOM telemetry active across 5 course platforms · Monitoring video
            completion vs verified comprehension.
          </p>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-destructive/30 bg-destructive/8 p-4 text-xs text-destructive"
        >
          {error instanceof Error
            ? error.message
            : "Courses could not be loaded."}
        </div>
      )}

      {isLoading ? (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((item) => (
            <div
              key={item}
              className="h-64 animate-pulse rounded-xl bg-surface"
            />
          ))}
        </div>
      ) : courses.length === 0 ? (
        <Panel className="p-10 text-center">
          <BookOpen className="mx-auto h-6 w-6 text-muted-foreground" />
          <p className="mt-4 text-sm font-semibold">No visited courses yet</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Capture a course, article, or video with the extension and it will
            appear here.
          </p>
        </Panel>
      ) : (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
          {courses.map((course) => {
            const courseTopics = topics.filter(
              (t) => t.course_id === course.id,
            );
            const platformColor =
              PLATFORM_TINT[course.platform] || "text-primary";

            return (
              <Panel
                key={course.id}
                className="group flex h-full flex-col justify-between p-5 transition-all hover:-translate-y-0.5 hover:border-primary/50"
              >
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

                  <Link
                    to="/courses/$courseId"
                    params={{ courseId: course.id }}
                    className="mt-2 block text-base font-semibold text-foreground group-hover:text-primary"
                  >
                    {course.title}
                  </Link>
                  <div className="mt-2 flex items-center gap-1.5 text-[10px] text-muted-foreground">
                    <History className="h-3 w-3" /> Last visited{" "}
                    {relativeDate(course.last_visited_at)} ·{" "}
                    {course.visit_count} capture
                    {course.visit_count === 1 ? "" : "s"}
                  </div>

                  <div className="mt-4 space-y-3">
                    {/* Completion */}
                    <div>
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Video Watched</span>
                        <span className="num font-medium text-foreground">
                          {course.completion_pct}%
                        </span>
                      </div>
                      <Meter
                        value={course.completion_pct}
                        tone="accent"
                        className="mt-1"
                      />
                    </div>

                    {/* Mastery */}
                    <div>
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Comprehension Mastery</span>
                        <span className="num font-medium text-primary">
                          {course.overall_mastery}%
                        </span>
                      </div>
                      <Meter
                        value={course.overall_mastery}
                        tone="primary"
                        className="mt-1"
                      />
                    </div>
                  </div>
                </div>

                <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3 text-xs text-muted-foreground">
                  <MasteryPill score={course.overall_mastery} />
                  <Link
                    to="/courses/$courseId"
                    params={{ courseId: course.id }}
                    className="inline-flex items-center gap-1 text-primary hover:underline"
                  >
                    View telemetry <ChevronRight className="h-3.5 w-3.5" />
                  </Link>
                  {course.source_url && (
                    <a
                      href={course.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                    >
                      Open course <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  )}
                </div>
              </Panel>
            );
          })}
        </div>
      )}
    </div>
  );
}

function relativeDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "recently";
  const days = Math.max(
    0,
    Math.floor((Date.now() - date.getTime()) / 86_400_000),
  );
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  return `${days} days ago`;
}
