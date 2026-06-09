import { useRef, useState } from "react";
import { approve, sendMessage, type ChatMessage } from "../api";

const WELCOME: ChatMessage = {
  role: "assistant",
  text: "AgentForge へようこそ。追加したい機能を自然言語で伝えてください（例：「タスク管理を追加して」）。承認は「反映して」、取り消しは「戻して」でもOKです。",
  created_at: new Date().toISOString(),
};

export function ChatView({
  onFeatureActivated,
  onFeatureDisabled,
}: {
  onFeatureActivated: (feature: string) => void;
  onFeatureDisabled: (feature: string) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingApprovalId, setPendingApprovalId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  function push(m: ChatMessage) {
    setMessages((prev) => [...prev, m]);
    queueMicrotask(() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight }));
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    setBusy(true);
    push({ role: "user", text, created_at: new Date().toISOString() });
    setInput("");
    try {
      const res = await sendMessage(text);
      push(res.reply);
      if (res.approval_id && res.detected_intent?.startsWith("build_feature")) {
        setPendingApprovalId(res.approval_id);
      }
      if (res.activated_feature) {
        setPendingApprovalId(null);
        onFeatureActivated(res.activated_feature);
      }
      if (res.disabled_feature) onFeatureDisabled(res.disabled_feature);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleApprove() {
    if (!pendingApprovalId) return;
    try {
      const res = await approve(pendingApprovalId);
      setPendingApprovalId(null);
      push({
        role: "assistant",
        text: "承認しました。左メニューに機能が追加されました。",
        created_at: new Date().toISOString(),
      });
      onFeatureActivated(res.feature);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="chatview">
      <div className="chat" ref={listRef}>
        {messages.map((m, i) => (
          <div key={i} className={`bubble bubble--${m.role}`}>{m.text}</div>
        ))}
        {busy && (
          <div className="bubble bubble--assistant bubble--pending">
            🤖 AIワーカーが機能を設計しています…（数十秒かかることがあります）
          </div>
        )}
      </div>

      {pendingApprovalId && (
        <div className="approval">
          <span>AIが作業計画を作成し、生成物を pending 登録しました。</span>
          <button onClick={() => void handleApprove()}>反映して（承認）</button>
        </div>
      )}

      {error && <div className="error">{error}</div>}

      <div className="composer">
        <textarea
          value={input}
          placeholder="追加したい機能を入力…（例：タスク管理を追加して）"
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
  );
}
