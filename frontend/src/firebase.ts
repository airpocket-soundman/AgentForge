// Firebase client init + Auth helpers (Phase 1).
// Config comes from Vite env vars (VITE_FIREBASE_*, see .env.local) so no values
// are hard-coded. The web API key is public (not a secret); access is governed by
// Firebase Auth + Firestore security rules.
import { initializeApp, type FirebaseApp } from "firebase/app";
import {
  GoogleAuthProvider,
  getAuth,
  onAuthStateChanged,
  signInWithPopup,
  signOut,
  type Auth,
  type User,
} from "firebase/auth";

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID ?? "agentforge-498808",
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

let app: FirebaseApp | undefined;
let authInstance: Auth | undefined;

const GUEST_KEY = "af_guest_access";

export function isFirebaseConfigured(): boolean {
  return Boolean(config.apiKey);
}

export function isGuestAccessEnabled(): boolean {
  return import.meta.env.VITE_GUEST_ACCESS_ENABLED === "true";
}

export function isGuestSession(): boolean {
  return isGuestAccessEnabled() && localStorage.getItem(GUEST_KEY) === "1";
}

export function startGuestSession(): void {
  if (!isGuestAccessEnabled()) return;
  localStorage.setItem(GUEST_KEY, "1");
}

export function clearGuestSession(): void {
  localStorage.removeItem(GUEST_KEY);
}

function getFirebaseApp(): FirebaseApp | undefined {
  if (!isFirebaseConfigured()) return undefined; // not configured -> auth disabled
  if (!app) app = initializeApp(config);
  return app;
}

export function getAuthInstance(): Auth | undefined {
  const a = getFirebaseApp();
  if (!a) return undefined;
  if (!authInstance) authInstance = getAuth(a);
  return authInstance;
}

export async function signInWithGoogle(): Promise<void> {
  const auth = getAuthInstance();
  if (!auth) throw new Error("Firebase が未設定です（.env.local を確認）");
  clearGuestSession();
  await signInWithPopup(auth, new GoogleAuthProvider());
}

export async function signOutUser(): Promise<void> {
  clearGuestSession();
  const auth = getAuthInstance();
  if (auth) await signOut(auth);
}

/** Subscribe to auth state. Returns an unsubscribe fn. */
export function onAuthChange(cb: (user: User | null) => void): () => void {
  const auth = getAuthInstance();
  if (!auth) {
    cb(null);
    return () => {};
  }
  return onAuthStateChanged(auth, cb);
}

/** Current user's Firebase ID token, for Authorization: Bearer headers. */
export async function getIdToken(): Promise<string | null> {
  if (isGuestSession()) return null;
  const user = getAuthInstance()?.currentUser;
  return user ? user.getIdToken() : null;
}
