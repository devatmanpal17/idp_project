import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  GoogleAuthProvider,
  browserLocalPersistence,
  getRedirectResult,
  onAuthStateChanged,
  setPersistence,
  signInWithPopup,
  signInWithRedirect,
  signOut as firebaseSignOut,
  updateProfile as updateFirebaseProfile,
  type User,
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
  loading: boolean;
  configured: boolean;
  error: string | null;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  saveProfile: (updates: ProfileUpdates) => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({ prompt: "select_account" });

function errorMessage(error: unknown) {
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
  if (!services) return profileFrom(user);

  const profileRef = doc(services.db, "users", user.uid);
  const snapshot = await getDoc(profileRef);
  const existing = snapshot.exists() ? snapshot.data() : undefined;
  const profile = profileFrom(user, existing);

  await setDoc(
    profileRef,
    {
      uid: user.uid,
      displayName: profile.displayName,
      email: user.email ?? "",
      photoURL: user.photoURL ?? "",
      bio: profile.bio,
      learningGoal: profile.learningGoal,
      preferredLanguage: profile.preferredLanguage,
      ...(snapshot.exists() ? {} : { createdAt: serverTimestamp() }),
      lastLoginAt: serverTimestamp(),
      updatedAt: serverTimestamp(),
    },
    { merge: true },
  );

  return profile;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const services = getFirebaseServices();
    if (!services) {
      setLoading(false);
      return;
    }

    void setPersistence(services.auth, browserLocalPersistence).catch(
      (reason: unknown) => {
        setError(errorMessage(reason));
      },
    );
    void getRedirectResult(services.auth).catch((reason: unknown) => {
      setError(errorMessage(reason));
    });

    return onAuthStateChanged(services.auth, (nextUser) => {
      setUser(nextUser);
      setError(null);
      if (!nextUser) {
        setProfile(null);
        setLoading(false);
        return;
      }

      setLoading(true);
      void syncUserProfile(nextUser)
        .then(setProfile)
        .catch((reason: unknown) => setError(errorMessage(reason)))
        .finally(() => setLoading(false));
    });
  }, []);

  const signInWithGoogle = useCallback(async () => {
    const services = getFirebaseServices();
    if (!services) {
      setError(
        "Firebase is not configured yet. Add the VITE_FIREBASE_* values and restart the dashboard.",
      );
      return;
    }

    setError(null);
    try {
      await setPersistence(services.auth, browserLocalPersistence);
      const useRedirect = window.matchMedia("(max-width: 767px)").matches;
      if (useRedirect) await signInWithRedirect(services.auth, googleProvider);
      else await signInWithPopup(services.auth, googleProvider);
    } catch (reason) {
      setError(errorMessage(reason));
      throw reason;
    }
  }, []);

  const signOut = useCallback(async () => {
    const services = getFirebaseServices();
    if (!services) return;
    setError(null);
    try {
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

      setError(null);
      try {
        const clean = {
          displayName: updates.displayName.trim().slice(0, 80),
          bio: updates.bio.trim().slice(0, 500),
          learningGoal: updates.learningGoal.trim().slice(0, 200),
          preferredLanguage:
            updates.preferredLanguage.trim().slice(0, 40) || "English",
        };
        await updateFirebaseProfile(user, { displayName: clean.displayName });
        await setDoc(
          doc(services.db, "users", user.uid),
          {
            uid: user.uid,
            ...clean,
            email: user.email ?? "",
            photoURL: user.photoURL ?? "",
            updatedAt: serverTimestamp(),
          },
          { merge: true },
        );
        setProfile((current) => ({
          ...(current ?? profileFrom(user)),
          ...clean,
        }));
      } catch (reason) {
        setError(errorMessage(reason));
        throw reason;
      }
    },
    [user],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      profile,
      loading,
      configured: isFirebaseConfigured,
      error,
      signInWithGoogle,
      signOut,
      saveProfile,
      clearError: () => setError(null),
    }),
    [error, loading, profile, saveProfile, signInWithGoogle, signOut, user],
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
