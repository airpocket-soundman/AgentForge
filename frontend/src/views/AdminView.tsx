import { useEffect, useState } from "react";
import {
  getAdminConfig,
  setAllowlist,
  setFeatureFlags,
  type AdminConfig,
} from "../api";

// Admin-only page (isolated from user data; gated by the separate admin allowlist).
// Lets the owner edit the USER allowlist and toggle feature flags (e.g. BYOK entry).
export function AdminView({ onBack }: { onBack?: () => void }) {
  const [cfg, setCfg] = useState<AdminConfig | null>(null);
  const [emailsText, setEmailsText] = useState("");
  const [byok, setByok] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    getAdminConfig()
      .then((c) => {
        setCfg(c);
        setEmailsText(c.allowlist_editable.join("\n"));
        setByok(c.feature_flags.byok_visible);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }
  useEffect(load, []);

  async function saveAllowlist() {
    setStatus(null);
    setError(null);
    try {
      const emails = emailsText.split(/[\s,;]+/).map((e) => e.trim()).filter(Boolean);
      await setAllowlist(emails);
      setStatus("ユーザー許可リストを保存しました。");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function toggleByok(next: boolean) {
    setByok(next);
    setStatus(null);
    setError(null);
    try {
      const f = await setFeatureFlags({ byok_visible: next });
      setByok(f.byok_visible);
      setStatus("機能フラグを保存しました。");
    } catch (e) {
      setByok(!next);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="view">
      <div className="view__head">
        {onBack && <button className="back" onClick={onBack}>← 戻る</button>}
        <h2>⚙ 管理者ページ</h2>
      </div>
      <p className="hint">
        このページは管理者（別ホワイトリスト）専用です。ユーザーページとは隔離されています。
      </p>

      {error && <div className="error">{error}</div>}
      {status && <div className="hint" style={{ color: "#2f8f5b" }}>{status}</div>}

      <section className="admin-card">
        <h3>ユーザー許可リスト（このアプリを使えるメール）</h3>
        <p className="hint">
          1行1メール。env で固定された分と管理者は常に許可されます（下の「有効な許可リスト」参照）。
        </p>
        <textarea
          className="admin-textarea"
          rows={6}
          value={emailsText}
          placeholder="user1@example.com&#10;user2@example.com"
          onChange={(e) => setEmailsText(e.target.value)}
        />
        <button className="admin-save" onClick={() => void saveAllowlist()}>保存</button>
        {cfg && (
          <div className="admin-meta">
            <div><b>有効な許可リスト:</b> {cfg.allowlist_effective.join(", ") || "（なし）"}</div>
            <div><b>管理者（編集不可）:</b> {cfg.admin_emails.join(", ")}</div>
          </div>
        )}
      </section>

      <section className="admin-card">
        <h3>機能フラグ</h3>
        <label className="admin-flag">
          <input type="checkbox" checked={byok} onChange={(e) => void toggleByok(e.target.checked)} />
          BYOK（自分のAPIキー設定）の入口をユーザーに表示する
          <span className="hint">※ 表示しても現在は非機能（謝罪ポップアップ）です</span>
        </label>
      </section>
    </div>
  );
}
