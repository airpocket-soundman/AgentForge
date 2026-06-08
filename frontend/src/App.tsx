import { useEffect, useRef, useState } from "react";
import type { User } from "firebase/auth";
import { sendMessage, type ChatMessage } from "./api";
import {
  isFirebaseConfigured,
  onAuthChange,
  signInWithGoogle,
  signOutUser,
} from "./firebase";

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
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const unsub = onAuthChange((u) => {
      setUser(u);
      setAuthReady(true);
    });
    return unsub;
  }, []);

  async function handleSend() {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    setBusy(true);
    const userMsg: ChatMessage = {
      role: "user",
      text,
      created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    try {
      const res = await sendMessage(text);
      setMessages((m) => [...m, res.reply]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      queueMicrotask(() =>
        listRef.current?.scrollTo({ top: listRef.current.scrollHeight }),
      );
    }
  }

  // Auth gate: require Google login when Firebase is configured.
  const needsLogin = isFirebaseConfigured() && authReady && !user;

  if (!authReady && isFirebaseConfigured()) {
    return <div className="app app--center">読み込み中…</div>;
  }

  if (needsLogin) {
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
    <div className="app">
      <header className="app__header">
        <h1>AgentForge</h1>
        <span className="app__tag">DevOps AI Agent Workbench — Phase 1</span>
        <span className="app__spacer" />
        {user && (
          <span className="app__user">
            {user.email}
            <button className="logout" onClick={() => void signOutUser()}>
              ログアウト
            </button>
          </span>
        )}
        {!isFirebaseConfigured() && (
          <span className="app__user">（ローカル: 認証なし）</span>
        )}
      </header>

      <div className="chat" ref={listRef}>
        {messages.map((m, i) => (
          <div key={i} className={`bubble bubble--${m.role}`}>
            {m.text}
          </div>
        ))}
        {busy && <div className="bubble bubble--assistant bubble--pending">…</div>}
      </div>

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
        <button onClick={() => void handleSend()} disabled={busy}>
          送信
        </button>
      </div>
    </div>
  );
}
