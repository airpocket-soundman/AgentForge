import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  getFeatureWorker,
  sendFeatureWorkerMessage,
  setFeatureWorker,
  type ChatMessage,
} from "../api";

const AUTO_SCROLL_THRESHOLD = 80;

function isNearBottom(el: HTMLElement | null): boolean {
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight <= AUTO_SCROLL_THRESHOLD;
}

/**
 * Standard feature-screen control: an instruction chat to operate the feature's
 * managing AI worker in natural language. Can be turned off per feature.
 * `onChanged` fires when the worker performs an action (e.g. created tasks).
 */
export function FeatureWorkerPanel({
  feature,
  onChanged,
  onCommand,
}: {
  feature: string;
  onChanged?: () => void;
  // mini-app: an MCP-style tool call the running app should execute (e.g. clear canvas)
  onCommand?: (cmd: { name: string; arguments?: Record<string, unknown> }) => void;
}) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);

  function scrollDown() {
    requestAnimationFrame(() => ref.current?.scrollTo({ top: ref.current.scrollHeight }));
  }

  useLayoutEffect(() => {
    if (shouldAutoScrollRef.current) scrollDown();
  }, [messages.length, busy]);

  useEffect(() => {
    void getFeatureWorker(feature)
      .then((w) => { setEnabled(w.enabled); setMessages(w.messages ?? []); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [feature]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    shouldAutoScrollRef.current = true;
    setMessages((m) => [...m, { role: "user", text, created_at: new Date().toISOString() }]);
    setInput("");
    try {
      const res = await sendFeatureWorkerMessage(feature, text);
      shouldAutoScrollRef.current = isNearBottom(ref.current);
      setMessages((m) => [...m, res.reply]);
      if (res.command) onCommand?.(res.command); // app-kind: run it in the live app
      if ((res.created && res.created.length > 0) || res.data_changed) onChanged?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggle(next: boolean) {
    await setFeatureWorker(feature, next);
    setEnabled(next);
  }

  if (enabled === null) return null;

  if (!enabled) {
    return (
      <div className="worker worker--off">
        <span>この機能のAIワーカーは無効です。</span>
        <button onClick={() => void toggle(true)}>AIワーカーを有効化</button>
      </div>
    );
  }

  return (
    <div className="worker">
      <div className="worker__head">
        <h3>🤖 機能AIワーカーへの指示</h3>
        <button className="worker__off" title="このページのAIワーカーを無効化" onClick={() => void toggle(false)}>
          ワーカーOFF
        </button>
      </div>
      <div className="chat chat--mini" ref={ref}>
        {messages.length === 0 && (
          <div className="hint">例：「買い物（卵・牛乳・パン）をタスクに追加して」「今日やるべきものを提案して」</div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble bubble--${m.role}`}>{m.text}</div>
        ))}
        {busy && <div className="bubble bubble--assistant bubble--pending">…</div>}
      </div>
      {error && <div className="error">{error}</div>}
      <div className="composer">
        <textarea
          value={input}
          placeholder="この機能のAIワーカーに指示…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }}
          rows={2}
        />
        <button onClick={() => void send()} disabled={busy}>送信</button>
      </div>
    </div>
  );
}
