import { useEffect, useState } from "react";
import type { User } from "firebase/auth";
import { disableFeature, getFeatureStates, getMe, resetAll, type Me } from "../api";
import { isFirebaseConfigured, signOutUser } from "../firebase";
import { ChatView } from "../views/ChatView";
import { TaskListView } from "../views/TaskListView";
import { TaskDetailView } from "../views/TaskDetailView";
import { GeneratedView } from "../views/GeneratedView";
import { ByokView } from "../views/ByokView";

// Admin is a SEPARATE app (frontend/admin.html), not reachable from here.
type View =
  | { kind: "chat" }
  | { kind: "tasks" }
  | { kind: "task"; id: string }
  | { kind: "feature"; key: string } // an AI-generated feature (Generated View Renderer)
  | { kind: "byok" };

export function AppShell({ user }: { user: User | null }) {
  // Raw feature_states doc: { <feature>: "active"|"disabled", <feature>_title, _theme, _worker, ... }
  const [states, setStates] = useState<Record<string, string>>({});
  const [view, setView] = useState<View>({ kind: "chat" });
  const [prevView, setPrevView] = useState<View>({ kind: "chat" });
  const [denied, setDenied] = useState(false);
  const [me, setMe] = useState<Me | null>(null);

  function loadStates() {
    return getFeatureStates()
      .then((s) => setStates(s))
      .catch((e: unknown) => {
        const status = (e as { status?: number })?.status;
        if (status === 401 || status === 403) setDenied(true);
      });
  }

  useEffect(() => { void loadStates(); }, []);
  useEffect(() => { void getMe().then(setMe).catch(() => {}); }, []); // identity + flags

  function openOverlay(kind: "byok") {
    setPrevView(view);
    setView({ kind });
  }

  if (denied) {
    return (
      <div className="centered">
        <h1>アクセス権限がありません</h1>
        <p className="muted">{user?.email ?? ""} はこのアプリの利用を許可されていません。</p>
        <button className="login" onClick={() => void signOutUser()}>別のアカウントでログアウト</button>
      </div>
    );
  }

  // Active features are keys whose value is exactly "active" (meta keys like
  // *_title / *_theme / *_worker / updated_at don't match and are filtered out).
  const activeFeatures = Object.keys(states).filter((k) => states[k] === "active");
  const titleOf = (f: string) => states[`${f}_title`] || (f === "task" ? "タスク管理" : f);
  const themeOf = (f: string) => states[`${f}_theme`] || "default";
  const iconOf = (f: string) => (f === "task" ? "✓" : "🧩");

  function goFeature(f: string) {
    if (f === "task") setView({ kind: "tasks" });
    else setView({ kind: "feature", key: f });
  }

  function onFeatureActivated(feature: string) {
    void loadStates();
    goFeature(feature);
  }
  function onFeatureDisabled() {
    void loadStates();
    setView({ kind: "chat" });
  }

  // Rollback (human-only): soft-disable every active feature. Data is kept.
  async function handleRollback() {
    if (activeFeatures.length === 0) return;
    if (!confirm("AIが追加した機能を巻き戻しますか？（無効化のみ／データは保持されます）")) return;
    try {
      for (const f of activeFeatures) await disableFeature(f);
      await loadStates();
      setView({ kind: "chat" });
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleReset() {
    if (!confirm("【開発用】完全に初期化します。タスク・会話・登録・監査ログ・生成機能など全データを削除して、メインチャットだけの初期状態に戻します。よろしいですか？")) return;
    try {
      await resetAll();
      window.location.reload();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  const currentFeature =
    view.kind === "tasks" || view.kind === "task" ? "task" : view.kind === "feature" ? view.key : null;
  const mainTheme = currentFeature ? themeOf(currentFeature) : "default";
  const navActive = (f: string) =>
    (f === "task" && (view.kind === "tasks" || view.kind === "task")) ||
    (view.kind === "feature" && view.key === f);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__brand">AgentForge</div>
        <span className="topbar__tag">DevOps AI Agent Workbench</span>
        <span className="spacer" />
        {me?.feature_flags.byok_visible && (
          <button className="byok-top" title="自分のAPIキー設定（試作）" onClick={() => openOverlay("byok")}>
            🔑 API設定
          </button>
        )}
        {activeFeatures.length > 0 && (
          <button
            className="rollback-top"
            title="AIが追加した機能を取り消す（人間専用のControl Plane操作）"
            onClick={() => void handleRollback()}
          >
            ⟲ 機能を巻き戻す
          </button>
        )}
        <button className="reset-top" title="【開発用】全データを削除して初期状態に戻す" onClick={() => void handleReset()}>
          🗑 初期化
        </button>
        {user && (
          <span className="topbar__user">
            {user.email}
            <button className="logout" onClick={() => void signOutUser()}>ログアウト</button>
          </span>
        )}
        {!isFirebaseConfigured() && <span className="topbar__user">（ローカル: 認証なし）</span>}
      </header>

      <div className="body">
        <nav className="sidebar">
          <div className="sidebar__label">機能</div>
          <button
            className={view.kind === "chat" ? "navitem navitem--active" : "navitem"}
            onClick={() => setView({ kind: "chat" })}
          >
            💬 メインチャット
          </button>
          {activeFeatures.map((f) => (
            <button key={f} className={navActive(f) ? "navitem navitem--active" : "navitem"} onClick={() => goFeature(f)}>
              {iconOf(f)} {titleOf(f)}
            </button>
          ))}
          {activeFeatures.length === 0 && (
            <div className="sidebar__hint">
              メインチャットで「タスク管理を追加して」→「反映して」で機能が増えます。
            </div>
          )}
        </nav>

        <main className="main" data-theme={mainTheme}>
          {view.kind === "chat" && (
            <ChatView onFeatureActivated={onFeatureActivated} onFeatureDisabled={onFeatureDisabled} />
          )}
          {view.kind === "tasks" && <TaskListView onOpenTask={(id) => setView({ kind: "task", id })} />}
          {view.kind === "task" && <TaskDetailView taskId={view.id} onBack={() => setView({ kind: "tasks" })} />}
          {view.kind === "feature" && <GeneratedView feature={view.key} />}
          {view.kind === "byok" && <ByokView onBack={() => setView(prevView)} />}
        </main>
      </div>
    </div>
  );
}
