import { useEffect, useRef, useState } from "react";
import {
  getCandidate,
  getConversationState,
  listMainChatContexts,
  activateMainChatContext,
  deleteMainChatContext,
  renameMainChatContext,
  sendMessage,
  type Attachment,
  type ChatMessage,
  type ConversationState,
  type MainChatContext,
  type ViewManifest,
} from "../api";
import { AppFrame, deleteFeatureBlobs } from "./AppFrame";
import { AttachButton, AttachmentChips, useAttachments } from "./Attachments";
import { MdText } from "./Markdown";

const WELCOME: ChatMessage = {
  role: "assistant",
  text: "AgentForge へようこそ。追加したい機能を自然言語で伝えてください（例：「お絵描きツールを作って」「タスク管理を追加して」）。\nまず設計案をお見せします → 修正できます → 「これで作って」でコード生成 → プレビュー確認 → 「反映して」で公開、の流れです。",
  created_at: "",
};

// The chat is BACKEND-DRIVEN and follows a two-stage flow:
//   idle → (依頼) → plan(設計案レビュー) → (これで作って) → built(プレビュー) → (反映して) → 公開
// History, the in-progress flag, the stage, and the preview/approval all come from
// /api/reception/state, so leaving this screen or reloading never loses progress.
export function ChatView({
  onFeatureActivated,
  onFeatureDisabled,
}: {
  onFeatureActivated: (feature: string) => void;
  onFeatureDisabled: (feature: string) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [building, setBuilding] = useState(false);
  const [stage, setStage] = useState<ConversationState["stage"]>("idle");
  const [phase, setPhase] = useState<string | null>(null);
  const [mode, setMode] = useState<ConversationState["mode"]>("create");
  const [pendingFeature, setPendingFeature] = useState<string | null>(null);
  const [preview, setPreview] = useState<ViewManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [contexts, setContexts] = useState<MainChatContext[]>([]);
  const [chatContext, setChatContext] = useState(() => localStorage.getItem("af_main_chat_context") || "default");
  // Backend state flag (set when a codegen failed its gates) — not derived from
  // assistant wording, so message-text changes can never break the button.
  const [needsRegeneration, setNeedsRegeneration] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const att = useAttachments();
  // The CURRENT session id, readable from long-lived closures. The poll interval
  // and the visibilitychange/focus resync listeners capture loadState from an
  // old render; without this ref they'd fetch (and display) the session that was
  // selected when they were registered — the dropdown and the shown messages
  // would disagree after switching sessions and coming back to the tab.
  const chatContextRef = useRef(chatContext);
  chatContextRef.current = chatContext;

  function scrollDown() {
    queueMicrotask(() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight }));
  }

  async function loadState() {
    const ctx = chatContextRef.current;
    try {
      const s = await getConversationState(undefined, ctx);
      // Drop stale responses: the user may have switched sessions while this
      // request was in flight (or a late response arrives out of order).
      if (chatContextRef.current !== ctx || (s.context_id && s.context_id !== ctx)) return null;
      setMessages(s.messages.length ? s.messages : [WELCOME]);
      setBuilding(s.building);
      setStage(s.stage);
      setPhase(s.phase ?? null);
      setMode(s.mode);
      setNeedsRegeneration(!!s.needs_regeneration);
      setPendingFeature(s.pending_feature);
      // Fetch the candidate app the moment code is built (create OR edit), in the
      // SAME call that flips the stage — avoids a one-shot race that left the
      // preview blank. Keep any existing preview if a transient fetch fails.
      if (s.stage === "built") {
        try {
          const c = await getCandidate();
          if (c) setPreview(c);
        } catch {
          /* keep current preview; the poll will retry */
        }
      } else {
        setPreview(null);
      }
      scrollDown();
      return s;
    } catch {
      return null;
    }
  }

  useEffect(() => {
    void loadState();
    void loadContexts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatContext]);

  async function loadContexts() {
    try {
      const c = await listMainChatContexts();
      setContexts(c.contexts);
    } catch {
      setContexts([]);
    }
  }

  // Poll while a background step runs, and keep polling until the built-stage
  // preview has actually loaded (so a slow/again-null candidate still appears).
  useEffect(() => {
    if (!building && !(stage === "built" && !preview)) return;
    const id = setInterval(() => void loadState(), 2500);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [building, stage, preview]);

  // Background tabs freeze setInterval, so a build that finished while the user
  // was on another tab wouldn't appear until a manual reload. Re-sync immediately
  // whenever the tab becomes visible / regains focus.
  useEffect(() => {
    const resync = () => {
      if (document.visibilityState === "visible") void loadState();
    };
    document.addEventListener("visibilitychange", resync);
    window.addEventListener("focus", resync);
    return () => {
      document.removeEventListener("visibilitychange", resync);
      window.removeEventListener("focus", resync);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function send(text: string, attachments: Attachment[] = []) {
    // The chat stays usable while a background build runs — the reception worker
    // replies with status. Only block on an in-flight POST (sending).
    if (!text.trim() || sending) return;
    setError(null);
    setSending(true);
    const note = attachments.length ? `${text}　📎${attachments.length}件` : text;
    setMessages((prev) => [...prev, { role: "user", text: note, created_at: new Date().toISOString() }]);
    scrollDown();
    try {
      const res = await sendMessage(text, attachments, undefined, chatContext);
      if (res.building) setBuilding(true);
      if (res.activated_feature) onFeatureActivated(res.activated_feature);
      if (res.deleted_feature) {
        await deleteFeatureBlobs(res.deleted_feature).catch(() => 0);
        onFeatureDisabled(res.deleted_feature);
      }
      if (res.disabled_feature) {
        onFeatureDisabled(res.disabled_feature);
      }
      await loadState();
      await loadContexts();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  async function handleSend() {
    const text = input.trim();
    if (!text) return;
    const files = att.items;
    setInput("");
    att.clear();
    await send(text, files);
  }

  async function switchContext(id: string) {
    const next = id || "default";
    setChatContext(next);
    localStorage.setItem("af_main_chat_context", next);
    await activateMainChatContext(next).catch(() => undefined);
  }

  async function createContext() {
    const id = `session_${Date.now().toString(36)}`;
    await switchContext(id);
    await loadContexts();
  }

  async function clearContext() {
    if (!window.confirm("この session を削除しますか？")) return;
    await deleteMainChatContext(chatContext);
    const next = "default";
    setChatContext(next);
    localStorage.setItem("af_main_chat_context", next);
    await activateMainChatContext(next).catch(() => undefined);
    await loadContexts();
    await loadState();
  }

  async function editSessionName() {
    const current = contexts.find((c) => c.context_id === chatContext);
    const raw = window.prompt("session name", current?.label || chatContext);
    const label = (raw || "").trim();
    if (!label) return;
    await renameMainChatContext(chatContext, label);
    await loadContexts();
  }

  // Drive the spinner by the ACTIVE phase, not the flow stage: the stage stays
  // "plan" during code generation, so keying off stage mislabels codegen as 設計案.
  // No fixed time estimates — generation time varies (high-capability models).
  const spinnerText =
    phase === "receiving"
      ? "🤖 ご依頼を整理しています…"
      : phase === "codegen"
        ? "🤖 AIワーカーがコードを生成しています…（他の画面に移動しても続きます）"
        : phase === "editing"
          ? "🤖 修正版を作成しています…"
          : phase === "revising"
            ? "🤖 設計案を修正しています…"
            : "🤖 設計案を作成しています…";

  return (
    <div className="chatview">
      <div className="main-context-bar">
        <select value={chatContext} onChange={(e) => void switchContext(e.target.value)} aria-label="メインチャット文脈">
          {(contexts.length ? contexts : [{ context_id: "default", label: "通常", message_count: 0, active: true }]).map((c) => (
            <option key={c.context_id} value={c.context_id}>
              {c.label || c.context_id}{c.message_count ? ` (${c.message_count})` : ""}
            </option>
          ))}
        </select>
        <button type="button" className="secondary" onClick={() => void createContext()}>new session</button>
        <button type="button" className="secondary" onClick={() => void editSessionName()}>session name edit</button>
        <button type="button" className="danger" onClick={() => void clearContext()}>session delete</button>
      </div>
      <div className="chat" ref={listRef}>
        {messages.map((m, i) => (
          <div key={i} className={`bubble bubble--${m.role}`}>
            <MdText text={m.text} />
            {m.svg && (
              <img
                className="bubble-svg"
                alt="画面イメージ（モック）"
                src={`data:image/svg+xml;utf8,${encodeURIComponent(m.svg)}`}
              />
            )}
          </div>
        ))}


        {stage === "built" && preview && (
          <div className="chat-preview">
            <div className="chat-preview__label">
              {mode === "edit" ? "プレビュー（修正版・未反映）" : "プレビュー（未公開）"}
            </div>
            {preview.html ? (
              <AppFrame html={preview.html} feature={pendingFeature ?? "preview"} title={preview.title} live={false} />
            ) : (
              <div className="chat-preview__data">
                <div className="chat-preview__title">{preview.title}</div>
                {preview.description && <p className="chat-preview__desc">{preview.description}</p>}
                {preview.list_columns?.length > 0 && (
                  <table className="table">
                    <thead>
                      <tr>{preview.list_columns.map((c) => <th key={c}>{c}</th>)}</tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td colSpan={preview.list_columns.length} className="table__empty">
                          公開後にデータを追加できます
                        </td>
                      </tr>
                    </tbody>
                  </table>
                )}
                <div className="chat-preview__meta">
                  {preview.fields?.length > 0 && <span>入力項目 {preview.fields.length}</span>}
                  {preview.stats?.length ? <span>📊 指標 {preview.stats.length}</span> : null}
                  {preview.charts?.length ? <span>📈 グラフ {preview.charts.length}</span> : null}
                  {preview.gantt ? <span>📅 ガント</span> : null}
                  {preview.calendar ? <span>🗓 カレンダー</span> : null}
                </div>
              </div>
            )}
          </div>
        )}

        {building && <div className="bubble bubble--assistant bubble--pending">{spinnerText}</div>}
      </div>

      {!building && stage === "plan" && (
        <div className="approval">
          <span>
            {needsRegeneration
              ? "未通過の生成物は公開できません。同じ設計で再生成するか、修正内容をメッセージで指示してください。"
              : "この設計案で進めますか？修正があればメッセージで指示してください。"}
          </span>
          <div className="approval__actions">
            <button className="rollback" onClick={() => void send("キャンセル")}>やめる</button>
            <button onClick={() => void send("これで作って")}>
              {needsRegeneration ? "同じ設計で再生成" : "これで作って（コード生成）"}
            </button>
          </div>
        </div>
      )}

      {!building && stage === "built" && (
        <div className="approval">
          <span>
            プレビューを確認できます。問題なければ{mode === "edit" ? "更新" : "公開"}します。
          </span>
          <button onClick={() => void send("反映して")}>
            🚀 反映して（{mode === "edit" ? "更新" : "公開"}）
          </button>
          <button className="rollback" onClick={() => void send("キャンセル")}>やめる</button>
        </div>
      )}

      {error && <div className="error">{error}</div>}

      <div className="composer-wrap" onDrop={att.onDrop} onDragOver={(e) => e.preventDefault()}>
        <AttachmentChips items={att.items} onRemove={att.removeAt} />
        <div className="composer">
          <AttachButton inputRef={att.inputRef} onFiles={att.addFiles} />
          <textarea
            value={input}
            placeholder={
              stage === "plan"
                ? needsRegeneration
                  ? "修正を入力…（例：指摘の表示方法を変えて）。同じ設計なら「同じ設計で再生成」"
                  : "修正を入力…（例：色を増やして / 保存も付けて）。OKなら「これで作って」"
                : "追加したい機能を入力…（画像やファイルも貼り付け・ドロップ・＋で添付）"
            }
            onChange={(e) => setInput(e.target.value)}
            onPaste={att.onPaste}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void handleSend();
              }
            }}
            rows={2}
          />
          <button onClick={() => void handleSend()} disabled={sending}>送信</button>
        </div>
      </div>
    </div>
  );
}
