import { useRef, useState } from "react";
import type { Attachment } from "../api";

// Shared attachment handling for chat composers: paste an image, drag & drop files,
// or pick via the ＋ button. Text/data files are read as text (inlined for the AI);
// images are read as base64 (sent for vision).
const TEXT_EXT =
  /\.(txt|csv|tsv|json|md|markdown|js|jsx|ts|tsx|html|htm|css|scss|py|rb|go|rs|java|c|cpp|yml|yaml|toml|ini|xml|svg|log|sql|sh)$/i;
const MAX_FILES = 8;
const MAX_TEXT = 20000;

function isImage(f: File) {
  return f.type.startsWith("image/");
}
function isText(f: File) {
  return f.type.startsWith("text/") || f.type === "application/json" || TEXT_EXT.test(f.name);
}

function readImage(f: File): Promise<Attachment> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const url = String(r.result);
      const i = url.indexOf("base64,");
      resolve({ name: f.name || "image", mime: f.type || "image/png", kind: "image", content: i >= 0 ? url.slice(i + 7) : "" });
    };
    r.onerror = reject;
    r.readAsDataURL(f);
  });
}
function readText(f: File): Promise<Attachment> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () =>
      resolve({ name: f.name || "file", mime: f.type || "text/plain", kind: "text", content: String(r.result).slice(0, MAX_TEXT) });
    r.onerror = reject;
    r.readAsText(f);
  });
}

export function useAttachments() {
  const [items, setItems] = useState<Attachment[]>([]);
  const inputRef = useRef<HTMLInputElement | null>(null);

  async function addFiles(files: FileList | File[]) {
    const out: Attachment[] = [];
    for (const f of Array.from(files)) {
      if (isImage(f)) out.push(await readImage(f));
      else if (isText(f)) out.push(await readText(f));
      // unsupported binary types are ignored
    }
    if (out.length) setItems((p) => [...p, ...out].slice(0, MAX_FILES));
  }
  function onPaste(e: React.ClipboardEvent) {
    const files = Array.from(e.clipboardData?.items || [])
      .filter((it) => it.kind === "file")
      .map((it) => it.getAsFile())
      .filter((f): f is File => !!f);
    if (files.length) {
      e.preventDefault();
      void addFiles(files);
    }
  }
  function onDrop(e: React.DragEvent) {
    if (e.dataTransfer?.files?.length) {
      e.preventDefault();
      void addFiles(e.dataTransfer.files);
    }
  }
  return {
    items,
    addFiles,
    onPaste,
    onDrop,
    removeAt: (i: number) => setItems((p) => p.filter((_, j) => j !== i)),
    clear: () => setItems([]),
    openPicker: () => inputRef.current?.click(),
    inputRef,
  };
}

// Hidden file input + the ＋ button. Place inside a composer.
export function AttachButton({
  inputRef,
  onFiles,
}: {
  inputRef: React.RefObject<HTMLInputElement>;
  onFiles: (files: FileList | File[]) => void;
}) {
  return (
    <>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept="image/*,.txt,.csv,.tsv,.json,.md,.js,.jsx,.ts,.tsx,.html,.css,.py,.yml,.yaml,.xml,.svg,.log,.sql"
        style={{ display: "none" }}
        onChange={(e) => {
          if (e.target.files) onFiles(e.target.files);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        className="attach-add"
        title="ファイル・画像を追加"
        onClick={() => inputRef.current?.click()}
      >
        +
      </button>
    </>
  );
}

export function AttachmentChips({ items, onRemove }: { items: Attachment[]; onRemove: (i: number) => void }) {
  if (!items.length) return null;
  return (
    <div className="attach-chips">
      {items.map((a, i) => (
        <span key={i} className="attach-chip" title={a.name}>
          {a.kind === "image" ? (
            <img className="attach-thumb" src={`data:${a.mime};base64,${a.content}`} alt={a.name} />
          ) : (
            <span className="attach-ic">📄</span>
          )}
          <span className="attach-name">{a.name}</span>
          <button className="attach-x" onClick={() => onRemove(i)} title="削除">×</button>
        </span>
      ))}
    </div>
  );
}
