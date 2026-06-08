import { useEffect, useState } from "react";
import type { User } from "firebase/auth";
import { disableFeature, getFeatureStates } from "../api";
import { isFirebaseConfigured, signOutUser } from "../firebase";
import { ChatView } from "../views/ChatView";
import { TaskListView } from "../views/TaskListView";
import { TaskDetailView } from "../views/TaskDetailView";

type View = { kind: "chat" } | { kind: "tasks" } | { kind: "task"; id: string };

export function AppShell({ user }: { user: User | null }) {
  const [taskActive, setTaskActive] = useState(false);
  const [view, setView] = useState<View>({ kind: "chat" });

  useEffect(() => {
    void getFeatureStates()
      .then((s) => setTaskActive(s.task === "active"))
      .catch(() => {});
  }, []);

  function onFeatureActivated(feature: string) {
    if (feature === "task") {
      setTaskActive(true);
      setView({ kind: "tasks" });
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
        {taskActive && (
          <button
            className="rollback-top"
            title="AIが行った機能変更を取り消す（人間専用のControl Plane操作）"
            onClick={() => void handleRollback()}
          >
            ⟲ 機能を巻き戻す
          </button>
        )}
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

        <main className="main">
          {view.kind === "chat" && (
            <ChatView onFeatureActivated={onFeatureActivated} onFeatureDisabled={onFeatureDisabled} />
          )}
          {view.kind === "tasks" && (
            <TaskListView onOpenTask={(id) => setView({ kind: "task", id })} />
          )}
          {view.kind === "task" && (
            <TaskDetailView taskId={view.id} onBack={() => setView({ kind: "tasks" })} />
          )}
        </main>
      </div>
    </div>
  );
}
