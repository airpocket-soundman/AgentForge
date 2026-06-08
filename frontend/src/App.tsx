import { useEffect, useRef, useState } from "react";
import type { User } from "firebase/auth";
import { approve, getFeatureStates, sendMessage, type ChatMessage } from "./api";
import {
  isFirebaseConfigured,
  onAuthChange,
  signInWithGoogle,
  signOutUser,
} from "./firebase";
import { TaskPanel } from "./TaskPanel";

const WELCOME: ChatMessage = {
  role: "assistant",
  text: "AgentForge へようこそ。追加したい機能を自然言語で伝えてください（例：「タスク管理を追加して」）。",
  created_at: new Date().toISOString(),
};

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingApprovalId, setPendingApprovalId] = useState<string | null>(null);
  const [taskActive, setTaskActive] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => onAuthChange((u) => { setUser(u); setAuthReady(true); }), []);

  // Restore feature state so the panel survives a reload.
  useEffect(() => {
    if (!isFirebaseConfigured() || user) {
      void getFeatureStates()
        .then((s) => setTaskActive(s.task === "active"))
        .catch(() => {});
    }
  }, [user]);

  async function handleSend() {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text, created_at: new Date().toISOString() }]);
    setInput("");
    try {
      const res = await sendMessage(text);
      setMessages((m) => [...m, res.reply]);
      if (res.approval_id && res.detected_intent?.startsWith("build_feature")) {
        setPendingApprovalId(res.approval_id);
      }
      // Conversational control ("反映して" / "戻して") changed feature state.
      if (res.activated_feature === "task") {
        setTaskActive(true);
        setPendingApprovalId(null);
      }
      if (res.disabled_feature) setTaskActive(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      queueMicrotask(() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight }));
    }
  }

  async function handleApprove() {
    if (!pendingApprovalId) return;
    try {
      await approve(pendingApprovalId);
      setPendingApprovalId(null);
      setTaskActive(true);
      setMessages((m) => [
        ...m,
        { role: "assistant", text: "承認しました。タスク管理機能を有効化しました（右のパネルで使えます）。", created_at: new Date().toISOString() },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!authReady && isFirebaseConfigured()) {
    return <div className="app app--center">読み込み中…</div>;
  }

  if (isFirebaseConfigured() && authReady && !user) {
    return (
      <div className="app app--center">
        <h1>AgentForge</h1>
        <p className="app__tag">DevOps AI Agent Workbench</p>
        <button className="login" onClick={() => void signInWithGoogle().catch((e) => setError(String(e)))}>
          Google でログイン
        </button>
        {error && <div className="error">{error}</div>}
      </div>
    );
  }

  return (
    <div className="layout">
      <div className="app">
        <header className="app__header">
          <h1>AgentForge</h1>
          <span className="app__tag">DevOps AI Agent Workbench</span>
          <span className="app__spacer" />
          {user && (
            <span className="app__user">
              {user.email}
              <button className="logout" onClick={() => void signOutUser()}>ログアウト</button>
            </span>
          )}
          {!isFirebaseConfigured() && <span className="app__user">（ローカル: 認証なし）</span>}
        </header>

        <div className="chat" ref={listRef}>
          {messages.map((m, i) => (
            <div key={i} className={`bubble bubble--${m.role}`}>{m.text}</div>
          ))}
          {busy && <div className="bubble bubble--assistant bubble--pending">…</div>}
        </div>

        {pendingApprovalId && !taskActive && (
          <div className="approval">
            <span>AIが作業計画を作成し、生成物を pending 登録しました。</span>
            <button onClick={() => void handleApprove()}>反映して（承認）</button>
          </div>
        )}

        {error && <div className="error">{error}</div>}

        <div className="composer">
          <textarea
            value={input}
            placeholder="追加したい機能を入力…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void handleSend();
              }
            }}
            rows={2}
          />
          <button onClick={() => void handleSend()} disabled={busy}>送信</button>
        </div>
      </div>

      <aside className="side">
        {taskActive ? (
          <TaskPanel onRollback={() => setTaskActive(false)} />
        ) : (
          <div className="side__empty">
            生成された機能はここに表示されます。<br />
            「タスク管理を追加して」→「反映して」で有効化。
          </div>
        )}
      </aside>
    </div>
  );
}
