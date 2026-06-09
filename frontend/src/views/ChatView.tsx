import { useEffect, useRef, useState } from "react";
import {
  getCandidate,
  getConversationState,
  sendMessage,
  type Attachment,
  type ChatMessage,
  type ConversationState,
  type ViewManifest,
} from "../api";
import { AppFrame } from "./AppFrame";
import { AttachButton, AttachmentChips, useAttachments } from "./Attachments";

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
  const [mode, setMode] = useState<ConversationState["mode"]>("create");
  const [pendingFeature, setPendingFeature] = useState<string | null>(null);
  const [preview, setPreview] = useState<ViewManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const att = useAttachments();

  function scrollDown() {
    queueMicrotask(() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight }));
  }

  async function loadState() {
    try {
      const s = await getConversationState();
      setMessages(s.messages.length ? s.messages : [WELCOME]);
      setBuilding(s.building);
      setStage(s.stage);
      setMode(s.mode);
      setPendingFeature(s.pending_feature);
      scrollDown();
      return s;
    } catch {
      return null;
    }
  }

  useEffect(() => {
    void loadState();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll while a background step (planning or code generation) is running.
  useEffect(() => {
    if (!building) return;
    const id = setInterval(() => void loadState(), 2500);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [building]);

  // Fetch the candidate app once code is built and awaiting publish (works for
  // edits too, where the live manifest is still the previous version).
  useEffect(() => {
    if (stage === "built") {
      getCandidate().then(setPreview).catch(() => setPreview(null));
    } else {
      setPreview(null);
    }
  }, [stage, pendingFeature]);

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
      const res = await sendMessage(text, attachments);
      if (res.building) setBuilding(true);
      if (res.activated_feature) onFeatureActivated(res.activated_feature);
      if (res.disabled_feature) onFeatureDisabled(res.disabled_feature);
      await loadState();
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

  const spinnerText =
    stage === "plan"
      ? "🤖 設計案を作成しています…（数秒）"
      : "🤖 AIワーカーがコードを生成しています…（数十秒〜1分／他の画面に移動しても続きます）";

  return (
    <div className="chatview">
      <div className="chat" ref={listRef}>
        {messages.map((m, i) => (
          <div key={i} className={`bubble bubble--${m.role}`}>{m.text}</div>
        ))}

        {stage === "built" && preview?.html && (
          <div className="chat-preview">
            <div className="chat-preview__label">
              {mode === "edit" ? "プレビュー（修正版・未反映）" : "プレビュー（未公開）"}
            </div>
            <AppFrame html={preview.html} feature={pendingFeature ?? "preview"} title={preview.title} live={false} />
          </div>
        )}

        {building && <div className="bubble bubble--assistant bubble--pending">{spinnerText}</div>}
      </div>

      {!building && stage === "plan" && (
        <div className="approval">
          <span>この設計案で進めますか？修正があればメッセージで指示してください。</span>
          <button onClick={() => void send("これで作って")}>これで作って（コード生成）</button>
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
                ? "修正を入力…（例：色を増やして / 保存も付けて）。OKなら「これで作って」"
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
