import { useEffect, useRef, useState } from "react";
import {
  getCandidate,
  getConversationState,
  getFeatureWorker,
  getView,
  sendFeatureWorkerMessage,
  sendMessage,
  type ConversationState,
  type FeatureWorkerState,
  type ViewManifest,
} from "../api";
import { AppFrame, type AgentCommand } from "./AppFrame";
import { AttachButton, AttachmentChips, useAttachments } from "./Attachments";

// Generated View Renderer: every feature is a COMPLETE self-contained HTML app the
// UI Designer worker wrote. We run it live in a sandboxed iframe (see AppFrame).
// Each feature also has its OWN worker chat pinned at the bottom — a general
// instruction channel. The worker answers, or forwards a change into the SAME
// app-design pipeline the main chat uses (the Orchestrator decides create-vs-edit).
// The change's preview + 反映 come from the shared conversation state, shown here.
function msg(e: unknown) {
  return e instanceof Error ? e.message : String(e);
}

export function GeneratedView({
  feature,
  onEdited,
}: {
  feature: string;
  onEdited?: () => void;
}) {
  const [manifest, setManifest] = useState<ViewManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [worker, setWorker] = useState<FeatureWorkerState | null>(null);
  const [conv, setConv] = useState<ConversationState | null>(null);
  const [candidate, setCandidate] = useState<ViewManifest | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [acting, setActing] = useState(false);
  // app-kind: a content command from the worker for the running app to execute.
  const [command, setCommand] = useState<AgentCommand | null>(null);
  const cmdNonce = useRef(0);
  const threadRef = useRef<HTMLDivElement>(null);
  const att = useAttachments();

  // Draggable split between the app pane (top) and the worker chat (bottom).
  // appRatio = app pane height fraction; 1 → only app, 0 → only chat. Re-draggable
  // either way; persisted so it's the standard layout across features/reloads.
  const splitRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const [appRatio, setAppRatio] = useState<number>(() => {
    const v = parseFloat(localStorage.getItem("af_feature_split") || "");
    return isFinite(v) && v >= 0 && v <= 1 ? v : 0.68;
  });

  useEffect(() => {
    localStorage.setItem("af_feature_split", String(appRatio));
  }, [appRatio]);

  function onDragStart(e: React.PointerEvent) {
    e.preventDefault();
    draggingRef.current = true;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); // keep events over the iframe
  }
  function onDragMove(e: React.PointerEvent) {
    if (!draggingRef.current || !splitRef.current) return;
    const rect = splitRef.current.getBoundingClientRect();
    setAppRatio(Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)));
  }
  function onDragEnd(e: React.PointerEvent) {
    draggingRef.current = false;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  }

  const building = conv?.building ?? false;
  // The shared pipeline produced a change for THIS feature, awaiting 反映.
  const showPreview =
    conv?.stage === "built" && conv?.pending_feature === feature && !!candidate?.html;

  function scrollDown() {
    queueMicrotask(() => threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight }));
  }

  async function loadAll() {
    try {
      const [w, c] = await Promise.all([getFeatureWorker(feature), getConversationState()]);
      setWorker(w);
      setConv(c);
      if (c.stage === "built" && c.pending_feature === feature) {
        getCandidate().then(setCandidate).catch(() => setCandidate(null));
      } else {
        setCandidate(null);
      }
      scrollDown();
      return c;
    } catch {
      return null;
    }
  }

  useEffect(() => {
    setError(null);
    setManifest(null);
    setWorker(null);
    setConv(null);
    setCandidate(null);
    setInput("");
    att.clear();
    getView(feature)
      .then(setManifest)
      .catch((e) => setError(msg(e)));
    void loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feature]);

  // Poll while a background design runs on the shared pipeline.
  useEffect(() => {
    if (!building) return;
    const id = setInterval(() => void loadAll(), 2500);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [building]);

  async function sendWorker() {
    const text = input.trim();
    if (!text || sending) return;
    setSending(true);
    setError(null);
    const files = att.items;
    const note = files.length ? `${text}　📎${files.length}件` : text;
    setWorker((w) =>
      w ? { ...w, messages: [...w.messages, { role: "user", text: note, created_at: new Date().toISOString() }] } : w,
    );
    setInput("");
    att.clear();
    scrollDown();
    try {
      const res = await sendFeatureWorkerMessage(feature, text, files);
      // mini-app: dispatch the specialist worker's MCP-style tool call to the app.
      if (res.command?.name) {
        setCommand({ name: res.command.name, args: res.command.arguments, nonce: ++cmdNonce.current });
      }
      await loadAll();
    } catch (e) {
      setError(msg(e));
    } finally {
      setSending(false);
    }
  }

  async function publish() {
    if (acting) return;
    setActing(true);
    setError(null);
    try {
      await sendMessage("反映して"); // shared pipeline: publishes the pending change
      setManifest(await getView(feature)); // the live app changed
      await loadAll();
      onEdited?.();
    } catch (e) {
      setError(msg(e));
    } finally {
      setActing(false);
    }
  }

  async function cancel() {
    if (acting) return;
    setActing(true);
    setError(null);
    try {
      await sendMessage("キャンセル");
      await loadAll();
    } catch (e) {
      setError(msg(e));
    } finally {
      setActing(false);
    }
  }

  if (error && !manifest)
    return (
      <div className="view">
        <div className="error">{error}</div>
      </div>
    );
  if (!manifest) return <div className="view">読み込み中…</div>;

  if (!manifest.html) {
    return (
      <div className="view">
        <div className="view__head">
          <h2>{manifest.title}</h2>
        </div>
        <div className="error">
          この機能は旧形式で作成されたため表示できません。メインチャットで作り直すか、
          「🗑 初期化」後にもう一度依頼してください。
        </div>
      </div>
    );
  }

  return (
    <div className="view view--app">
      <div className="view__head">
        <h2>{manifest.title}</h2>
        <span className="hint">🤖 AI生成アプリ（{manifest.generated_by}）</span>
      </div>

      {worker && !worker.enabled ? (
        <>
          <AppFrame html={manifest.html} feature={feature} title={manifest.title} live command={command} />
          <div className="hint feature-worker__off">この機能のAIワーカーは無効です。</div>
        </>
      ) : (
        // App pane / draggable divider / worker chat. Drag the divider to resize;
        // drag fully to either end to show only one side (re-draggable back).
        <div className="gv-split" ref={splitRef}>
          <div className="gv-pane gv-pane--app" style={{ flexBasis: `${appRatio * 100}%` }}>
            <AppFrame html={manifest.html} feature={feature} title={manifest.title} live command={command} />
          </div>

          <div
            className="gv-divider"
            role="separator"
            aria-orientation="horizontal"
            title="ドラッグで境界を移動（上下端まで動かすと一方だけ表示）"
            onPointerDown={onDragStart}
            onPointerMove={onDragMove}
            onPointerUp={onDragEnd}
          />

          <div className="gv-pane gv-pane--chat">
            <div className="feature-worker" onDrop={att.onDrop} onDragOver={(e) => e.preventDefault()}>
              <div className="fw-scroll" ref={threadRef}>
                {showPreview && (
                  <div className="chat-preview fw-preview">
                    <div className="chat-preview__label">プレビュー（変更候補・未反映）</div>
                    <AppFrame html={candidate!.html!} feature={feature} title={candidate!.title} live={false} />
                    <div className="fw-actions">
                      <button onClick={() => void publish()} disabled={acting}>
                        🚀 反映（更新）
                      </button>
                      <button className="rollback" onClick={() => void cancel()} disabled={acting}>
                        やめる
                      </button>
                    </div>
                  </div>
                )}

                {worker?.messages.map((m, i) => (
                  <div key={i} className={`bubble bubble--${m.role}`}>{m.text}</div>
                ))}
                {building && (
                  <div className="bubble bubble--assistant bubble--pending">
                    🤖 指示を反映しています…（数十秒）
                  </div>
                )}
                {error && <div className="error">{error}</div>}
              </div>

              <AttachmentChips items={att.items} onRemove={att.removeAt} />
              <div className="feature-edit">
                <AttachButton inputRef={att.inputRef} onFiles={att.addFiles} />
                <textarea
                  value={input}
                  placeholder="この機能のワーカーに指示…（例：列を追加 / 集計を出す / 配色を変える / 使い方を質問・画像も添付）"
                  onChange={(e) => setInput(e.target.value)}
                  onPaste={att.onPaste}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void sendWorker();
                    }
                  }}
                  rows={2}
                  disabled={sending}
                />
                <button onClick={() => void sendWorker()} disabled={sending || !input.trim()}>
                  送信
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
