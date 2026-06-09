import { useEffect, useState } from "react";
import type { User } from "firebase/auth";
import { disableFeature, getFeatureStates, getMe, resetAll, type Me } from "../api";
import { isFirebaseConfigured, signOutUser } from "../firebase";
import { ChatView } from "../views/ChatView";
import { TaskListView } from "../views/TaskListView";
import { TaskDetailView } from "../views/TaskDetailView";
import { AdminView } from "../views/AdminView";
import { ByokView } from "../views/ByokView";

type View =
  | { kind: "chat" }
  | { kind: "tasks" }
  | { kind: "task"; id: string }
  | { kind: "admin" }
  | { kind: "byok" };

export function AppShell({ user }: { user: User | null }) {
  const [taskActive, setTaskActive] = useState(false);
  const [taskTheme, setTaskTheme] = useState("default");
  const [view, setView] = useState<View>({ kind: "chat" });
  const [prevView, setPrevView] = useState<View>({ kind: "chat" });
  const [denied, setDenied] = useState(false);
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    void getMe().then(setMe).catch(() => {}); // identity + feature flags (admin/byok)
  }, []);

  function openOverlay(kind: "admin" | "byok") {
    setPrevView(view);
    setView({ kind });
  }

  function loadStates() {
    return getFeatureStates()
      .then((s) => {
        setTaskActive(s.task === "active");
        setTaskTheme(s.task_theme || "default"); // generated-view theme (idea 3 §2.6)
      })
      .catch((e: unknown) => {
        const status = (e as { status?: number })?.status;
        if (status === 401 || status === 403) setDenied(true);
      });
  }

  useEffect(() => {
    void loadStates();
  }, []);

  if (denied) {
    return (
      <div className="centered">
        <h1>アクセス権限がありません</h1>
        <p className="muted">{user?.email ?? ""} はこのアプリの利用を許可されていません。</p>
        <button className="login" onClick={() => void signOutUser()}>別のアカウントでログアウト</button>
      </div>
    );
  }

  function onFeatureActivated(feature: string) {
    if (feature === "task") {
      setTaskActive(true);
      setView({ kind: "tasks" });
      void loadStates(); // pick up the feature's chosen theme
    }
  }
  function onFeatureDisabled(feature: string) {
    if (feature === "task") {
      setTaskActive(false);
      setView({ kind: "chat" });
    }
  }

  // Rollback lives in the top bar = a human-only Control Plane action. The AI can
  // register/activate features but cannot reach this control to undo a rollback.
  async function handleRollback() {
    if (!taskActive) return;
    if (!confirm("AIが追加した機能を巻き戻しますか？（無効化のみ／データは保持されます）")) return;
    try {
      await disableFeature("task");
      onFeatureDisabled("task");
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  // DEV ONLY: wipe all data and reload to the initial main-chat-only state.
  async function handleReset() {
    if (!confirm("【開発用】完全に初期化します。タスク・会話・登録・監査ログなど全データを削除して、メインチャットだけの初期状態に戻します。よろしいですか？")) return;
    try {
      await resetAll();
      window.location.reload();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  const navItems = [
    { key: "chat", label: "💬 メインチャット", active: view.kind === "chat", go: () => setView({ kind: "chat" }) },
    ...(taskActive
      ? [{ key: "tasks", label: "✓ タスク管理", active: view.kind === "tasks" || view.kind === "task", go: () => setView({ kind: "tasks" }) }]
      : []),
  ];

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__brand">AgentForge</div>
        <span className="topbar__tag">DevOps AI Agent Workbench</span>
        <span className="spacer" />
        {me?.is_admin && (
          <button className="admin-top" title="管理者ページ（管理者のみ）" onClick={() => openOverlay("admin")}>
            ⚙ 管理
          </button>
        )}
        {me?.feature_flags.byok_visible && (
          <button className="byok-top" title="自分のAPIキー設定（試作）" onClick={() => openOverlay("byok")}>
            🔑 API設定
          </button>
        )}
        {taskActive && (
          <button
            className="rollback-top"
            title="AIが行った機能変更を取り消す（人間専用のControl Plane操作）"
            onClick={() => void handleRollback()}
          >
            ⟲ 機能を巻き戻す
          </button>
        )}
        <button
          className="reset-top"
          title="【開発用】全データを削除して初期状態に戻す"
          onClick={() => void handleReset()}
        >
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
          {navItems.map((it) => (
            <button
              key={it.key}
              className={it.active ? "navitem navitem--active" : "navitem"}
              onClick={it.go}
            >
              {it.label}
            </button>
          ))}
          {!taskActive && (
            <div className="sidebar__hint">
              メインチャットで「タスク管理を追加して」→「反映して」で機能が増えます。
            </div>
          )}
        </nav>

        <main
          className="main"
          data-theme={view.kind === "tasks" || view.kind === "task" ? taskTheme : "default"}
        >
          {view.kind === "chat" && (
            <ChatView onFeatureActivated={onFeatureActivated} onFeatureDisabled={onFeatureDisabled} />
          )}
          {view.kind === "tasks" && (
            <TaskListView onOpenTask={(id) => setView({ kind: "task", id })} />
          )}
          {view.kind === "task" && (
            <TaskDetailView taskId={view.id} onBack={() => setView({ kind: "tasks" })} />
          )}
          {view.kind === "admin" && <AdminView onBack={() => setView(prevView)} />}
          {view.kind === "byok" && <ByokView onBack={() => setView(prevView)} />}
        </main>
      </div>
    </div>
  );
}
