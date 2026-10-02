import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  GoogleAuthProvider,
  browserLocalPersistence,
  inMemoryPersistence,
  getRedirectResult,
  onAuthStateChanged,
  setPersistence,
  signInWithPopup,
  signOut as firebaseSignOut,
  updateProfile as updateFirebaseProfile,
  type User,
  type Auth,
} from "firebase/auth";
import {
  doc,
  getDoc,
  serverTimestamp,
  setDoc,
  type DocumentData,
} from "firebase/firestore";

import { getFirebaseServices, isFirebaseConfigured } from "@/lib/firebase";

export interface UserProfile {
  uid: string;
  displayName: string;
  email: string;
  photoURL: string;
  bio: string;
  learningGoal: string;
  preferredLanguage: string;
}

export interface ProfileUpdates {
  displayName: string;
  bio: string;
  learningGoal: string;
  preferredLanguage: string;
}

interface AuthContextValue {
  user: User | null;
  profile: UserProfile | null;
  profileLoaded: boolean;
  loading: boolean;
  configured: boolean;
  error: string | null;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  saveProfile: (updates: ProfileUpdates) => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const PROFILE_TIMEOUT_MS = 15_000;

async function withDeadline<T>(
  request: Promise<T>,
  message: string,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      request,
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () => reject(new Error(message)),
          PROFILE_TIMEOUT_MS,
        );
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

async function configurePersistence(auth: Auth) {
  try {
    await setPersistence(auth, browserLocalPersistence);
  } catch {
    // Sign-in can still work when the browser blocks durable storage.
    await setPersistence(auth, inMemoryPersistence);
  }
}

const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({ prompt: "select_account" });

function errorMessage(error: unknown) {
  if (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    error.code === "auth/unauthorized-domain"
  ) {
    return "This address is not authorized by Firebase. Use the configured dashboard address or add this domain in Firebase Authentication settings.";
  }
  if (error instanceof Error)
    return error.message.replace(/^Firebase:\s*/i, "");
  return "Something went wrong. Please try again.";
}

function profileFrom(user: User, data?: DocumentData): UserProfile {
  return {
    uid: user.uid,
    displayName:
      typeof data?.["displayName"] === "string"
        ? data["displayName"]
        : (user.displayName ?? ""),
    email: user.email ?? "",
    photoURL: user.photoURL ?? "",
    bio: typeof data?.["bio"] === "string" ? data["bio"] : "",
    learningGoal:
      typeof data?.["learningGoal"] === "string" ? data["learningGoal"] : "",
    preferredLanguage:
      typeof data?.["preferredLanguage"] === "string"
        ? data["preferredLanguage"]
        : "English",
  };
}

async function syncUserProfile(user: User) {
  const services = getFirebaseServices();
  if (!services) throw new Error("Firebase is not configured.");

  const profileRef = doc(services.db, "users", user.uid);
  const snapshot = await getDoc(profileRef);
  const existing = snapshot.exists() ? snapshot.data() : undefined;
  const profile = profileFrom(user, existing);

  return { profile, exists: snapshot.exists() };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [configured, setConfigured] = useState(isFirebaseConfigured);
  const session = useRef({
    active: false,
    generation: 0,
    uid: null as string | null,
  });
  const persistence = useRef<Promise<void> | null>(null);

  useEffect(() => {
    session.current.active = true;
    let unsubscribe: (() => void) | undefined;
    let initialTimer: ReturnType<typeof setTimeout> | undefined;
    const dispose = () => {
      session.current.active = false;
      session.current.generation++;
      session.current.uid = null;
      clearTimeout(initialTimer);
      unsubscribe?.();
    };
    try {
      const services = getFirebaseServices();
      if (!services) {
        setLoading(false);
        return dispose;
      }

      persistence.current = configurePersistence(services.auth);
      void persistence.current.catch((reason: unknown) => {
        if (session.current.active) setError(errorMessage(reason));
      });
      void getRedirectResult(services.auth).catch((reason: unknown) => {
        if (session.current.active) setError(errorMessage(reason));
      });

      initialTimer = setTimeout(() => {
        if (session.current.active) {
          setLoading(false);
          setError(
            "Sign-in state could not be checked in time. Reload and try again.",
          );
        }
      }, PROFILE_TIMEOUT_MS);

      unsubscribe = onAuthStateChanged(services.auth, (nextUser) => {
        clearTimeout(initialTimer);
        const generation = ++session.current.generation;
        session.current.uid = nextUser?.uid ?? null;
        const current = () =>
          session.current.active && session.current.generation === generation;
        setUser(nextUser);
        setProfileLoaded(false);
        setError(null);
        if (!nextUser) {
          setProfile(null);
          setLoading(false);
          return;
        }

        setLoading(true);
        setProfile(profileFrom(nextUser));
        void withDeadline(
          syncUserProfile(nextUser),
          "Your saved profile could not be loaded in time. Your Google identity is available; reload to try again.",
        )
          .then(({ profile: loadedProfile, exists }) => {
            if (!current()) return;
            setProfile(loadedProfile);
            setProfileLoaded(true);
            // A new document needs all fields required by firestore.rules;
            // the first explicit save creates it with a complete profile.
            if (!exists) return;
            // Login metadata must not block the form or overwrite editable fields
            // saved in another tab while this profile was being read.
            void withDeadline(
              setDoc(
                doc(services.db, "users", nextUser.uid),
                {
                  uid: nextUser.uid,
                  email: nextUser.email ?? "",
                  photoURL: nextUser.photoURL ?? "",
                  lastLoginAt: serverTimestamp(),
                },
                { merge: true },
              ),
              "Login details could not sync in time. Your profile is still available.",
            ).catch((reason: unknown) => {
              if (current()) setError(errorMessage(reason));
            });
          })
          .catch((reason: unknown) => {
            if (current()) setError(errorMessage(reason));
          })
          .finally(() => {
            if (current()) setLoading(false);
          });
      });
    } catch (reason) {
      clearTimeout(initialTimer);
      setConfigured(false);
      setError(errorMessage(reason));
      setLoading(false);
    }
    return dispose;
  }, []);

  const signInWithGoogle = useCallback(async () => {
    try {
      const services = getFirebaseServices();
      if (!services) {
        setError(
          "Firebase is not configured yet. Add the VITE_FIREBASE_* values and restart the dashboard.",
        );
        return;
      }

      setError(null);
      await withDeadline(
        persistence.current ?? configurePersistence(services.auth),
        "Sign-in setup timed out. Reload and try again.",
      );
      await signInWithPopup(services.auth, googleProvider);
    } catch (reason) {
      setError(errorMessage(reason));
      throw reason;
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      const services = getFirebaseServices();
      if (!services) return;
      setError(null);
      await firebaseSignOut(services.auth);
    } catch (reason) {
      setError(errorMessage(reason));
      throw reason;
    }
  }, []);

  const saveProfile = useCallback(
    async (updates: ProfileUpdates) => {
      const services = getFirebaseServices();
      if (!services || !user)
        throw new Error("Sign in before updating your profile.");
      const generation = session.current.generation;
      const current = () =>
        session.current.active &&
        session.current.generation === generation &&
        session.current.uid === user.uid;
      const requireCurrent = () => {
        if (!current())
          throw new Error(
            "Your account changed. Save again from your current profile.",
          );
      };

      setError(null);
      try {
        if (!profileLoaded)
          throw new Error(
            "Your saved profile is unavailable. Reload before editing to avoid replacing existing details.",
          );
        const clean = {
          displayName: updates.displayName.trim().slice(0, 80),
          bio: updates.bio.trim().slice(0, 500),
          learningGoal: updates.learningGoal.trim().slice(0, 200),
          preferredLanguage:
            updates.preferredLanguage.trim().slice(0, 40) || "English",
        };
        requireCurrent();
        await withDeadline(
          updateFirebaseProfile(user, { displayName: clean.displayName }),
          "Updating your Google display name timed out. Reload before retrying.",
        );
        requireCurrent();
        await withDeadline(
          setDoc(
            doc(services.db, "users", user.uid),
            {
              uid: user.uid,
              ...clean,
              email: user.email ?? "",
              photoURL: user.photoURL ?? "",
              updatedAt: serverTimestamp(),
            },
            { merge: true },
          ),
          "Saving your profile timed out. Changes may still sync when you reconnect. Reload before retrying.",
        );
        requireCurrent();
        setProfile((current) => ({
          ...(current?.uid === user.uid ? current : profileFrom(user)),
          ...clean,
        }));
      } catch (reason) {
        if (current()) setError(errorMessage(reason));
        throw reason;
      }
    },
    [profileLoaded, user],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      profile,
      profileLoaded,
      loading,
      configured,
      error,
      signInWithGoogle,
      signOut,
      saveProfile,
      clearError: () => setError(null),
    }),
    [
      configured,
      error,
      loading,
      profile,
      profileLoaded,
      saveProfile,
      signInWithGoogle,
      signOut,
      user,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// The provider and hook intentionally share one module so consumers use the same context instance.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}
