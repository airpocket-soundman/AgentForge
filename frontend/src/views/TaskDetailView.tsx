import { useEffect, useRef, useState } from "react";
import {
  getTask,
  sendTaskMessage,
  setTaskDone,
  type ChatMessage,
  type TaskDetail,
} from "../api";

export function TaskDetailView({ taskId, onBack }: { taskId: string; onBack: () => void }) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [summary, setSummary] = useState("");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void (async () => {
      try {
        const t = await getTask(taskId);
        setTask(t);
        setMessages(t.messages ?? []);
        setSummary(t.summary ?? "");
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [taskId]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setMessages((m) => [...m, { role: "user", text, created_at: new Date().toISOString() }]);
    setInput("");
    try {
      const res = await sendTaskMessage(taskId, text);
      setMessages((m) => [...m, res.reply]);
      setSummary(res.summary);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      queueMicrotask(() => chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight }));
    }
  }

  async function toggleDone() {
    if (!task) return;
    const updated = await setTaskDone(task.task_id, !task.done);
    setTask({ ...task, done: updated.done });
  }

  if (error) return <div className="view"><button className="back" onClick={onBack}>← 戻る</button><div className="error">{error}</div></div>;
  if (!task) return <div className="view">読み込み中…</div>;

  return (
    <div className="detail">
      <div className="detail__top">
        <div className="view__head">
          <button className="back" onClick={onBack}>← 一覧</button>
          <h2>{task.title}</h2>
          <label className="done-toggle">
            <input type="checkbox" checked={task.done} onChange={() => void toggleDone()} /> 完了
          </label>
        </div>
        <div className="detail__meta">
          <span>期日: {task.due_date ?? "—"}</span>
          <span>状態: {task.done ? "完了" : "未完了"}</span>
        </div>
        <div className="detail__summary">
          <h3>エージェントが整理した内容</h3>
          {summary ? (
            <pre>{summary}</pre>
          ) : (
            <p className="hint">下のチャットでワーカーエージェントに相談すると、ここに整理内容が表示されます。</p>
          )}
        </div>
      </div>

      <div className="detail__bottom">
        <h3>ワーカーエージェントとの会話</h3>
        <div className="chat chat--mini" ref={chatRef}>
          {messages.length === 0 && (
            <div className="hint">例：「やることを3つに分解して」「期限を今週金曜にして整理して」</div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`bubble bubble--${m.role}`}>{m.text}</div>
          ))}
          {busy && <div className="bubble bubble--assistant bubble--pending">…</div>}
        </div>
        <div className="composer">
          <textarea
            value={input}
            placeholder="ワーカーエージェントに指示…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            rows={2}
          />
          <button onClick={() => void send()} disabled={busy}>送信</button>
        </div>
      </div>
    </div>
  );
}
