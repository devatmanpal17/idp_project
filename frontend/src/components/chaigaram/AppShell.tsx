import { useEffect, useState, type ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import { BookOpen, CalendarClock, Compass, History, LayoutGrid, ListChecks, Menu, MonitorSmartphone, Moon, Radar, Settings2, Sun, UserRound, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { checkAIHealth, type AIHealth } from "@/lib/ai-client";
import { useAuth } from "@/components/auth/AuthProvider";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutGrid },
  { to: "/courses", label: "Courses", icon: BookOpen },
  { to: "/mastery", label: "Mastery", icon: Radar },
  { to: "/quizzes", label: "Practice", icon: ListChecks },
  { to: "/study-plan", label: "Plan", icon: CalendarClock },
  { to: "/recommendations", label: "Next up", icon: Compass },
  { to: "/history", label: "History", icon: History },
  { to: "/simulator", label: "Extension", icon: MonitorSmartphone },
  { to: "/profile", label: "Profile", icon: UserRound },
  { to: "/settings", label: "Settings", icon: Settings2 },
] as const;

function useTheme() {
  const [light, setLight] = useState(false);
  useEffect(() => {
    const isLight = window.localStorage.getItem("chaigaram-theme") === "light";
    setLight(isLight);
    document.documentElement.classList.toggle("light", isLight);
  }, []);
  const toggle = () => setLight((previous) => {
    const next = !previous;
    document.documentElement.classList.toggle("light", next);
    window.localStorage.setItem("chaigaram-theme", next ? "light" : "dark");
    return next;
  });
  return { light, toggle };
}

export function AppShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const { light, toggle } = useTheme();
  const { user, profile, loading: authLoading } = useAuth();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const [health, setHealth] = useState<AIHealth | null>(null);

  useEffect(() => {
    let active = true;
    const refresh = () => checkAIHealth().then((result) => active && setHealth(result)).catch(() => active && setHealth(null));
    refresh();
    const timer = window.setInterval(refresh, 15_000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  useEffect(() => setMenuOpen(false), [pathname]);

  const ready = health?.status === "ready";
  const isActive = (to: string) => to === "/" ? pathname === "/" : pathname.startsWith(to);

  return (
    <div className="app-canvas min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-50 border-b border-border bg-background/75 backdrop-blur-2xl">
        <div className="mx-auto flex h-16 max-w-[1480px] items-center gap-5 px-4 sm:px-6 lg:px-8">
          <Link to="/" className="flex shrink-0 items-center gap-2.5" aria-label="ChaiGaram home">
            <span className="grid h-8 w-8 place-items-center rounded-[10px] bg-foreground text-[10px] font-bold text-background">CG</span>
            <span className="font-display text-[15px] font-semibold tracking-[-0.035em]">ChaiGaram</span>
          </Link>

          <nav className="mx-auto hidden items-center gap-1 xl:flex" aria-label="Primary navigation">
            {NAV.map((item) => <Link key={item.to} to={item.to} className={cn("rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors", isActive(item.to) ? "bg-surface-2 text-foreground" : "text-muted-foreground hover:text-foreground")}>{item.label}</Link>)}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <div className="hidden items-center gap-2 rounded-full border border-border bg-surface/70 px-3 py-1.5 text-[10px] text-muted-foreground sm:flex"><span className={cn("h-1.5 w-1.5 rounded-full", ready ? "bg-positive" : "bg-warn")} />{ready ? `${String(health?.indexed_chunks ?? 0)} notes indexed` : "Engine offline"}</div>
            <button onClick={toggle} className="grid h-8 w-8 place-items-center rounded-full text-muted-foreground transition hover:bg-surface-2 hover:text-foreground" title="Change theme">{light ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}</button>
            <Link
              to="/profile"
              className={cn(
                "flex h-9 items-center gap-2 rounded-full border border-border bg-surface/70 transition hover:border-primary/40 hover:bg-surface-2",
                user ? "p-0.5 pr-2.5" : "px-3 text-[11px] font-semibold",
              )}
              aria-label={user ? "Open your profile" : "Sign in"}
            >
              {user ? (
                <>
                  <Avatar className="h-8 w-8 border border-border">
                    <AvatarImage src={user.photoURL ?? undefined} alt="" referrerPolicy="no-referrer" />
                    <AvatarFallback className="bg-primary/15 text-[11px] font-bold text-primary">
                      {(profile?.displayName || user.displayName || user.email || "U").charAt(0).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <span className="hidden max-w-24 truncate text-[11px] font-semibold sm:block">
                    {profile?.displayName || user.displayName || "Profile"}
                  </span>
                </>
              ) : (
                <><UserRound className="h-3.5 w-3.5" />{authLoading ? "Loading" : "Sign in"}</>
              )}
            </Link>
            <button onClick={() => setMenuOpen((open) => !open)} className="grid h-9 w-9 place-items-center rounded-full text-foreground transition hover:bg-surface-2 xl:hidden" aria-label="Toggle navigation" aria-expanded={menuOpen}>{menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}</button>
          </div>
        </div>

        {menuOpen && <nav className="border-t border-border bg-background/95 px-4 py-4 backdrop-blur-2xl xl:hidden" aria-label="Mobile navigation"><div className="mx-auto grid max-w-xl grid-cols-2 gap-2 sm:grid-cols-4">{NAV.map((item) => { const Icon = item.icon; return <Link key={item.to} to={item.to} className={cn("flex items-center gap-2.5 rounded-xl px-3 py-3 text-[12px] font-medium", isActive(item.to) ? "bg-primary/12 text-primary" : "bg-surface text-muted-foreground")}><Icon className="h-4 w-4" />{item.label}</Link>; })}</div></nav>}
      </header>

      <main className="mx-auto min-w-0 max-w-[1480px] px-4 py-8 sm:px-6 sm:py-10 lg:px-8 lg:py-14 xl:px-12">{children}</main>
    </div>
  );
}
