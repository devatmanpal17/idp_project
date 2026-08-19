import { useEffect, useState, type ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  Hexagon,
  BookOpen,
  CalendarClock,
  ChevronsLeft,
  ChevronsRight,
  Compass,
  LayoutGrid,
  ListChecks,
  Moon,
  MonitorSmartphone,
  Radar,
  Settings2,
  Sun,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutGrid },
  { to: "/courses", label: "Courses", icon: BookOpen },
  { to: "/mastery", label: "Topic Mastery", icon: Radar },
  { to: "/quizzes", label: "Quizzes", icon: ListChecks },
  { to: "/study-plan", label: "Study Plan", icon: CalendarClock },
  { to: "/recommendations", label: "Recommendations", icon: Compass },
  { to: "/simulator", label: "Extension Simulator", icon: MonitorSmartphone },
  { to: "/settings", label: "Settings", icon: Settings2 },
] as const;

function useTheme() {
  const [light, setLight] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem("chaigaram-theme");
    const isLight = stored === "light";
    setLight(isLight);
    document.documentElement.classList.toggle("light", isLight);
  }, []);

  const toggle = () => {
    setLight((prev) => {
      const next = !prev;
      document.documentElement.classList.toggle("light", next);
      window.localStorage.setItem("chaigaram-theme", next ? "light" : "dark");
      return next;
    });
  };

  return { light, toggle };
}

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const { light, toggle } = useTheme();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  useEffect(() => {
    setCollapsed(window.localStorage.getItem("chaigaram-nav") === "collapsed");
  }, []);

  const toggleNav = () =>
    setCollapsed((prev) => {
      window.localStorage.setItem("chaigaram-nav", prev ? "expanded" : "collapsed");
      return !prev;
    });

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside
        className={cn(
          "sticky top-0 flex h-screen shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200",
          collapsed ? "w-[62px]" : "w-[236px]",
        )}
      >
        <div className="flex h-14 items-center gap-2.5 px-4">
          <div className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-surface-2 text-foreground border border-border">
            <Hexagon className="h-4 w-4" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="font-display text-sm font-semibold tracking-tight">ChaiGaram</div>
              <div className="num text-[10px] text-muted-foreground">v0.9.2 · build 431</div>
            </div>
          )}
        </div>

        <nav className="flex-1 space-y-0.5 px-2 py-2">
          {NAV.map((item) => {
            const active =
              item.to === "/" ? pathname === "/" : pathname.startsWith(item.to as string);
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                title={item.label}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] transition-colors",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                )}
              >
                <Icon
                  className={cn("h-4 w-4 shrink-0", active ? "text-primary" : "text-current")}
                />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        <div className="space-y-1 border-t border-sidebar-border p-2">
          <button
            onClick={toggle}
            className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-foreground"
          >
            {light ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
            {!collapsed && <span>{light ? "Dark mode" : "Light mode"}</span>}
          </button>
          <button
            onClick={toggleNav}
            className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-foreground"
          >
            {collapsed ? (
              <ChevronsRight className="h-4 w-4" />
            ) : (
              <ChevronsLeft className="h-4 w-4" />
            )}
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-4 border-b border-border bg-background/80 px-6 backdrop-blur">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="live-dot h-1.5 w-1.5 rounded-full bg-positive" />
            <span>Extension connected</span>
            <span className="text-border-strong">·</span>
            <span className="num">3 signals/min</span>
          </div>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="hidden num sm:inline">RAG index: 12,480 chunks</span>
            <span className="hidden h-4 w-px bg-border sm:inline-block" />
            <div className="flex items-center gap-2">
              <div className="grid h-6 w-6 place-items-center rounded-full bg-primary/15 text-[10px] font-semibold text-primary">
                DP
              </div>
              <span className="hidden sm:inline">devatman@chaigaram.io</span>
            </div>
          </div>
        </header>
        <main className="min-w-0 flex-1 px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
