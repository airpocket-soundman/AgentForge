import { useEffect, useState } from "react";
import type { User } from "firebase/auth";
import { isFirebaseConfigured, onAuthChange, signInWithGoogle } from "./firebase";
import { AppShell } from "./shell/AppShell";

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => onAuthChange((u) => { setUser(u); setAuthReady(true); }), []);

  if (!authReady && isFirebaseConfigured()) {
    return <div className="centered">読み込み中…</div>;
  }

  if (isFirebaseConfigured() && authReady && !user) {
    return (
      <div className="centered">
        <h1>AgentForge</h1>
        <p className="muted">DevOps AI Agent Workbench</p>
        <button className="login" onClick={() => void signInWithGoogle().catch((e) => setError(String(e)))}>
          Google でログイン
        </button>
        {error && <div className="error">{error}</div>}
      </div>
    );
  }

  return <AppShell user={user} />;
}
