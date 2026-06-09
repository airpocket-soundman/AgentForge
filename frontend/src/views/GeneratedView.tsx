import { useEffect, useState } from "react";
import { editFeatureRequest, getView, type ViewManifest } from "../api";
import { AppFrame } from "./AppFrame";
import { AttachButton, AttachmentChips, useAttachments } from "./Attachments";

// Generated View Renderer: every feature is a COMPLETE self-contained HTML app the
// UI Designer worker wrote to faithfully implement the request. We run it live in a
// sandboxed iframe (see AppFrame) with the AF persistence bridge. Each feature also
// has its own worker box that edits ONLY this feature (code/UI changes); the preview
// + 「反映して」 then happen in the main chat.
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
  const [edit, setEdit] = useState("");
  const [editing, setEditing] = useState(false);
  const att = useAttachments();

  useEffect(() => {
    setError(null);
    setManifest(null);
    setEdit("");
    att.clear();
    getView(feature)
      .then(setManifest)
      .catch((e) => setError(msg(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feature]);

  async function submitEdit() {
    const text = edit.trim();
    if (!text || editing) return;
    setEditing(true);
    setError(null);
    const files = att.items;
    try {
      await editFeatureRequest(feature, text, files);
      setEdit("");
      att.clear();
      onEdited?.(); // jump to main chat where the修正版 preview + 反映して appear
    } catch (e) {
      setError(msg(e));
    } finally {
      setEditing(false);
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

      {/* This feature's own worker: edit ONLY this feature in natural language. */}
      <div className="feature-edit-wrap" onDrop={att.onDrop} onDragOver={(e) => e.preventDefault()}>
        <AttachmentChips items={att.items} onRemove={att.removeAt} />
        <div className="feature-edit">
          <AttachButton inputRef={att.inputRef} onFiles={att.addFiles} />
          <input
            value={edit}
            placeholder="この機能を修正…（例：ボタンを大きく / 桁を四捨五入 / 画像も貼り付け・＋で添付）"
            onChange={(e) => setEdit(e.target.value)}
            onPaste={att.onPaste}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void submitEdit();
              }
            }}
            disabled={editing}
          />
          <button onClick={() => void submitEdit()} disabled={editing || !edit.trim()}>
            {editing ? "作成中…" : "修正を依頼"}
          </button>
        </div>
      </div>
      {error && <div className="error">{error}</div>}

      <AppFrame html={manifest.html} feature={feature} title={manifest.title} live />
    </div>
  );
}
