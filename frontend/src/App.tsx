import { useEffect, useState } from "react";
import type { User } from "firebase/auth";
import {
  isFirebaseConfigured,
  onAuthChange,
  signOutUser,
  signInWithGoogle,
} from "./firebase";
import { getPublicConfig } from "./api";
import { AppShell } from "./shell/AppShell";

function LandingPage({
  user,
  showGuestCta,
  error,
  onSignIn,
  onGuestLogin,
  onOpenApp,
  onSignOut,
}: {
  user: User | null;
  showGuestCta: boolean;
  error: string | null;
  onSignIn: () => void;
  onGuestLogin: () => void;
  onOpenApp: () => void;
  onSignOut: () => void;
}) {
  return (
    <div className="landing">
      <header className="landing-nav">
        <button className="landing-brand" onClick={() => window.location.hash = "home"}>AgentForge</button>
        <nav className="landing-links" aria-label="メイン">
          <a href="https://findy.notion.site/devops-ai-agent-hackathon-2026" target="_blank" rel="noreferrer">Hackathon</a>
          <a href="#features">特徴</a>
          <a href="#flow">流れ</a>
          <a href="#safety">安全性</a>
        </nav>
        <div className="landing-auth">
          {user ? (
            <>
              <span className="landing-user">{user.photoURL && <img src={user.photoURL} alt="" />} {user.email}</span>
              <button className="landing-secondary" onClick={onOpenApp}>アプリを開く</button>
              <button className="landing-primary" onClick={onSignOut}>Sign out</button>
            </>
          ) : (
            <>
              <button className="landing-judge-nav" onClick={onGuestLogin}>審査員用ゲストログイン</button>
              <span className="landing-usericon" aria-hidden="true" />
              <button className="landing-secondary" onClick={onSignIn}>Sign in</button>
              <button className="landing-primary" onClick={onSignIn}>Sign up</button>
            </>
          )}
        </div>
      </header>

      <main>
        <section className="landing-hero">
          <div className="landing-copy">
            <a
              className="landing-hackathon"
              href="https://findy.notion.site/devops-ai-agent-hackathon-2026"
              target="_blank"
              rel="noreferrer"
            >
              DevOps × AI Agent Hackathon 2026 提出作品
            </a>
            <div className="landing-kicker">DevOps AI Agent Workbench</div>
            <h1>会話だけで、自分専用アプリを作って育てる。</h1>
            <p>
              AgentForge は、非エンジニアでもメインチャットからミニアプリを作成・改変・公開・巻き戻しできる、
              自己拡張型の AI ワークベンチです。
            </p>
            <div className="landing-actions">
              {user ? (
                <button className="landing-primary landing-primary--large" onClick={onOpenApp}>アプリ画面へ</button>
              ) : (
                <button className="landing-primary landing-primary--large" onClick={onSignIn}>アプリを開く</button>
              )}
            </div>
            {!user && (
              <button className="landing-judge-big" onClick={onGuestLogin}>
                審査員用ゲストログイン
                <span>{showGuestCta ? "Google アカウントで個別のゲスト環境に入ります" : "ローカルデモ環境でアプリに入ります"}</span>
              </button>
            )}
            {!user && (
              <p className="landing-note">許可リスト外の Google アカウントは、ゲストとして個別環境で試せます。</p>
            )}
            {error && <div className="error">{error}</div>}
          </div>
          <div className="landing-visual" aria-label="AgentForge の画面イメージ">
            <img src="/agentforge_app_screen.png" alt="AgentForge のアプリ画面構成" />
          </div>
        </section>

        <section className="landing-band" id="features">
          <h2>話すだけで DevOps を回す</h2>
          <div className="landing-grid">
            <div><b>つくる</b><span>Receptor と Orchestrator が要求を整理し、設計案から実装へ進めます。</span></div>
            <div><b>ためす</b><span>Tester と Reviewer が動作と規約を確認し、未完成の公開を防ぎます。</span></div>
            <div><b>とどける</b><span>プレビュー確認後、「反映して」で公開。履歴から巻き戻しもできます。</span></div>
          </div>
        </section>

        <section className="landing-band landing-band--split" id="flow">
          <div>
            <h2>生成されたアプリにも専属ワーカー</h2>
            <p>各ミニアプリには Specialist Worker が付き、アプリの中身の編集や操作をその画面で依頼できます。</p>
          </div>
          <div id="safety">
            <h2>勝手に本公開しない</h2>
            <p>設計承認、プレビュー、公開承認を分け、AI が強い権限を直接持たない構造にしています。</p>
          </div>
        </section>
      </main>
    </div>
  );
}

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [guestEnabled, setGuestEnabled] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [publicReady, setPublicReady] = useState(false);
  const [route, setRoute] = useState(() => window.location.hash.replace(/^#/, ""));

  useEffect(() => onAuthChange((u) => { setUser(u); setAuthReady(true); }), []);

  useEffect(() => {
    const onHash = () => setRoute(window.location.hash.replace(/^#/, ""));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    getPublicConfig()
      .then((c) => {
        setGuestEnabled(c.guest_access_enabled);
        setAuthRequired(c.auth_required);
      })
      .catch(() => setGuestEnabled(false))
      .finally(() => setPublicReady(true));
  }, []);

  if ((!authReady && isFirebaseConfigured()) || !publicReady) {
    return <div className="centered">読み込み中…</div>;
  }

  if (authRequired && !isFirebaseConfigured()) {
    return (
      <div className="centered">
        <h1>Firebase 設定が必要です</h1>
        <p className="muted">
          認証込みローカルデモでは、frontend/.env.local に Firebase Web app config を設定してください。
        </p>
      </div>
    );
  }

  const noAuthLocal = !isFirebaseConfigured() && !authRequired;
  const showHome = route === "home" || (isFirebaseConfigured() && authReady && !user) || (noAuthLocal && route !== "app");
  const openApp = () => {
    window.location.hash = "app";
    setRoute("app");
  };
  const signIn = () => {
    if (noAuthLocal) {
      openApp();
      return;
    }
    void signInWithGoogle().then(openApp).catch((e) => setError(String(e)));
  };
  const guestLogin = () => {
    if (noAuthLocal) {
      openApp();
      return;
    }
    signIn();
  };
  const signOut = () => {
    void signOutUser()
      .then(() => {
        window.location.hash = "home";
        setRoute("home");
      })
      .catch((e) => setError(String(e)));
  };

  if (showHome) {
    return (
      <LandingPage
        user={user}
        showGuestCta={guestEnabled || noAuthLocal}
        error={error}
        onSignIn={signIn}
        onGuestLogin={guestLogin}
        onOpenApp={openApp}
        onSignOut={signOut}
      />
    );
  }

  return <AppShell user={user} onShowHome={() => { window.location.hash = "home"; setRoute("home"); }} />;
}
