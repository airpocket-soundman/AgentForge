// Standalone ADMIN app — served on its own port/origin (dev: :5174/admin.html),
// intentionally NOT linked from the user app. Access is still enforced server-side
// (require_admin); this app just keeps the admin surface separate and unlinked.
import { useEffect, useState } from "react";
import type { User } from "firebase/auth";
import { getMe, type Me } from "../api";
import { completeRedirectSignIn, isFirebaseConfigured, onAuthChange, signInWithGoogle, signOutUser } from "../firebase";
import { AdminView } from "../views/AdminView";

export function AdminApp() {
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [meChecked, setMeChecked] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void completeRedirectSignIn().catch((e) => setError(String(e)));
    return onAuthChange((u) => { setUser(u); setAuthReady(true); });
  }, []);

  useEffect(() => {
    if (isFirebaseConfigured() && !user) return; // wait for login in prod
    getMe()
      .then((m) => { setMe(m); setMeChecked(true); })
      .catch(() => { setMe(null); setMeChecked(true); });
  }, [user]);

  if (!authReady && isFirebaseConfigured()) return <div className="centered">読み込み中…</div>;

  if (isFirebaseConfigured() && authReady && !user) {
    return (
      <div className="centered">
        <h1>AgentForge 管理</h1>
        <p className="muted">管理者のみ</p>
        <button className="login" onClick={() => void signInWithGoogle().catch((e) => setError(String(e)))}>
          Google でログイン
        </button>
        {error && <div className="error">{error}</div>}
      </div>
    );
  }

  if (!meChecked) return <div className="centered">確認中…</div>;

  if (!me?.is_admin) {
    return (
      <div className="centered">
        <h1>管理者のみ</h1>
        <p className="muted">{me?.email || user?.email || ""} は管理者ではありません。</p>
        {isFirebaseConfigured() && (
          <button className="login" onClick={() => void signOutUser()}>ログアウト</button>
        )}
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__brand">AgentForge 管理</div>
        <span className="topbar__tag">Admin Console（独立アプリ）</span>
        <span className="spacer" />
        <span className="topbar__user">
          {me.email || "(ローカル)"}
          {isFirebaseConfigured() && (
            <button className="logout" onClick={() => void signOutUser()}>ログアウト</button>
          )}
        </span>
      </header>
      <div className="body" style={{ gridTemplateColumns: "1fr" }}>
        <main className="main">
          <AdminView />
        </main>
      </div>
    </div>
  );
}
