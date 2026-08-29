import { useEffect, useState, type FormEvent } from "react";
import { createFileRoute } from "@tanstack/react-router";
import {
  CheckCircle2,
  LogOut,
  Save,
  ShieldCheck,
  Sparkles,
  UserRound,
} from "lucide-react";

import { useAuth, type ProfileUpdates } from "@/components/auth/AuthProvider";
import {
  PageHeader,
  Panel,
  PanelHeader,
} from "@/components/chaigaram/primitives";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export const Route = createFileRoute("/profile")({
  head: () => ({ meta: [{ title: "Profile | ChaiGaram" }] }),
  component: ProfileScreen,
});

const EMPTY_PROFILE: ProfileUpdates = {
  displayName: "",
  bio: "",
  learningGoal: "",
  preferredLanguage: "English",
};

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M21.6 12.2c0-.7-.1-1.5-.2-2.2H12v4h5.4a4.7 4.7 0 0 1-2 3v2.6h3.3c1.9-1.8 2.9-4.4 2.9-7.4Z"
      />
      <path
        fill="#34A853"
        d="M12 22c2.7 0 5-.9 6.7-2.4L15.4 17c-.9.6-2.1 1-3.4 1a5.9 5.9 0 0 1-5.5-4.1H3.1v2.7A10 10 0 0 0 12 22Z"
      />
      <path
        fill="#FBBC05"
        d="M6.5 13.9A6 6 0 0 1 6.2 12c0-.7.1-1.3.3-1.9V7.4H3.1A10 10 0 0 0 2 12c0 1.7.4 3.2 1.1 4.6l3.4-2.7Z"
      />
      <path
        fill="#EA4335"
        d="M12 6c1.5 0 2.8.5 3.9 1.5l2.9-2.9A9.8 9.8 0 0 0 12 2a10 10 0 0 0-8.9 5.4l3.4 2.7A5.9 5.9 0 0 1 12 6Z"
      />
    </svg>
  );
}

function ProfileScreen() {
  const {
    user,
    profile,
    loading,
    configured,
    error,
    signInWithGoogle,
    signOut,
    saveProfile,
    clearError,
  } = useAuth();
  const [form, setForm] = useState<ProfileUpdates>(EMPTY_PROFILE);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!profile) return;
    setForm({
      displayName: profile.displayName,
      bio: profile.bio,
      learningGoal: profile.learningGoal,
      preferredLanguage: profile.preferredLanguage,
    });
  }, [profile]);

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setSaved(false);
    try {
      await saveProfile(form);
      setSaved(true);
    } catch {
      // The auth provider exposes the user-friendly error message.
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl space-y-5" aria-busy="true">
        <div className="h-20 animate-pulse rounded-xl bg-surface" />
        <div className="h-80 animate-pulse rounded-xl bg-surface" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-4xl">
        <PageHeader
          eyebrow="Your account"
          title="Make ChaiGaram yours"
          description="Sign in to keep a secure profile for your learning goals and dashboard identity."
        />
        <div className="grid overflow-hidden rounded-2xl border border-border bg-surface shadow-panel lg:grid-cols-[1.1fr_0.9fr]">
          <div className="p-7 sm:p-10">
            <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/12 text-primary">
              <UserRound className="h-6 w-6" />
            </div>
            <h2 className="mt-7 font-display text-2xl font-semibold tracking-tight">
              Sign in with Google
            </h2>
            <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
              Use one Google account to access your profile. Your editable
              profile is saved in your private Firebase user document.
            </p>
            <button
              type="button"
              disabled={!configured}
              onClick={() => {
                clearError();
                void signInWithGoogle().catch(() => undefined);
              }}
              className="mt-7 inline-flex h-11 w-full max-w-sm items-center justify-center gap-3 rounded-lg bg-foreground px-5 text-sm font-semibold text-background transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
            >
              <span className="grid h-6 w-6 place-items-center rounded-full bg-white">
                <GoogleMark />
              </span>
              Continue with Google
            </button>
            {!configured && (
              <div className="mt-4 max-w-lg rounded-lg border border-warn/30 bg-warn/8 p-4 text-xs leading-5 text-muted-foreground">
                Firebase setup is required before sign-in can start. Follow{" "}
                <code className="text-foreground">
                  frontend/FIREBASE_SETUP.md
                </code>
                , add the values only to{" "}
                <code className="text-foreground">frontend/.env.local</code>,
                then restart the dashboard.
              </div>
            )}
            {error && (
              <div
                role="alert"
                className="mt-4 max-w-lg rounded-lg border border-destructive/30 bg-destructive/8 p-3 text-xs text-destructive"
              >
                {error}
              </div>
            )}
          </div>
          <div className="border-t border-border bg-surface-2 p-7 sm:p-10 lg:border-l lg:border-t-0">
            <p className="label-xs">What you get</p>
            <div className="mt-5 space-y-5">
              <Benefit
                icon={<ShieldCheck />}
                title="Firebase-secured profile"
                text="Only the signed-in user can read or change their profile document."
              />
              <Benefit
                icon={<Sparkles />}
                title="Personal learning goals"
                text="Save a bio, goal, and preferred learning language for your dashboard."
              />
              <Benefit
                icon={<CheckCircle2 />}
                title="Persistent session"
                text="Stay signed in across refreshes on this device until you sign out."
              />
            </div>
          </div>
        </div>
      </div>
    );
  }

  const displayName =
    profile?.displayName || user.displayName || "ChaiGaram learner";
  const initial = (displayName || user.email || "U").charAt(0).toUpperCase();

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        eyebrow="Your account"
        title="Profile"
        description="Manage the identity and learning preferences connected to your dashboard."
      />
      <div className="grid gap-7 lg:grid-cols-[300px_1fr]">
        <Panel className="h-fit overflow-hidden">
          <div className="h-20 bg-[radial-gradient(circle_at_top_left,var(--primary),transparent_70%)] opacity-50" />
          <div className="px-6 pb-6">
            <Avatar className="-mt-10 h-20 w-20 border-4 border-surface shadow-panel">
              <AvatarImage
                src={user.photoURL ?? undefined}
                alt={displayName}
                referrerPolicy="no-referrer"
              />
              <AvatarFallback className="bg-primary text-xl font-bold text-primary-foreground">
                {initial}
              </AvatarFallback>
            </Avatar>
            <h2 className="mt-4 truncate text-lg font-semibold">
              {displayName}
            </h2>
            <p className="mt-0.5 truncate text-xs text-muted-foreground">
              {user.email}
            </p>
            <div className="mt-5 space-y-2 border-t border-border pt-5 text-xs text-muted-foreground">
              <div className="flex items-center justify-between gap-3">
                <span>Provider</span>
                <span className="font-medium text-foreground">Google</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span>Member since</span>
                <span className="font-medium text-foreground">
                  {formatDate(user.metadata.creationTime)}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span>Last sign-in</span>
                <span className="font-medium text-foreground">
                  {formatDate(user.metadata.lastSignInTime)}
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => void signOut().catch(() => undefined)}
              className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-md border border-border px-4 py-2.5 text-xs font-semibold transition hover:bg-surface-2"
            >
              <LogOut className="h-3.5 w-3.5" /> Sign out
            </button>
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            title="Profile details"
            subtitle="These values are saved to your private Firestore profile."
          />
          <form onSubmit={handleSave} className="space-y-6 p-6">
            <Field label="Display name" hint="Shown in your dashboard header.">
              <Input
                value={form.displayName}
                maxLength={80}
                required
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    displayName: event.target.value,
                  }))
                }
              />
            </Field>
            <Field label="About you" hint={`${form.bio.length}/500 characters`}>
              <Textarea
                value={form.bio}
                maxLength={500}
                rows={4}
                placeholder="What are you learning right now?"
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    bio: event.target.value,
                  }))
                }
              />
            </Field>
            <Field
              label="Learning goal"
              hint="A short outcome you are working toward."
            >
              <Input
                value={form.learningGoal}
                maxLength={200}
                placeholder="For example: master React fundamentals"
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    learningGoal: event.target.value,
                  }))
                }
              />
            </Field>
            <Field
              label="Preferred learning language"
              hint="Quiz generation remains English-only as requested."
            >
              <Input
                value={form.preferredLanguage}
                maxLength={40}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    preferredLanguage: event.target.value,
                  }))
                }
              />
            </Field>
            {error && (
              <div
                role="alert"
                className="rounded-lg border border-destructive/30 bg-destructive/8 p-3 text-xs text-destructive"
              >
                {error}
              </div>
            )}
            <div className="flex flex-wrap items-center gap-3 border-t border-border pt-5">
              <button
                disabled={saving || !form.displayName.trim()}
                type="submit"
                className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2.5 text-xs font-semibold text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Save className="h-3.5 w-3.5" />{" "}
                {saving ? "Saving…" : "Save profile"}
              </button>
              {saved && (
                <span className="inline-flex items-center gap-1.5 text-xs text-positive">
                  <CheckCircle2 className="h-4 w-4" /> Profile saved
                </span>
              )}
            </div>
          </form>
        </Panel>
      </div>
    </div>
  );
}

function Benefit({
  icon,
  title,
  text,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
}) {
  return (
    <div className="flex gap-3">
      <span className="mt-0.5 text-primary [&>svg]:h-4 [&>svg]:w-4">
        {icon}
      </span>
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{text}</p>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-end justify-between gap-3">
        <Label>{label}</Label>
        <span className="text-[10px] text-muted-foreground">{hint}</span>
      </div>
      {children}
    </div>
  );
}

function formatDate(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? "—"
    : new Intl.DateTimeFormat("en", {
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(date);
}
