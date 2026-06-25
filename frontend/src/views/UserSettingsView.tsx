import { useState } from "react";

export type LlmProvider = "gemini" | "openai" | "anthropic" | "codex";

export interface UserSettings {
  iconText: string;
  iconColor: string;
  iconImageDataUrl: string;
  callName: string;
  llmProvider: LlmProvider;
  llmApiKey: string;
}

const STORAGE_KEY = "af_user_settings";

export const defaultUserSettings: UserSettings = {
  iconText: "A",
  iconColor: "#4a4ae0",
  iconImageDataUrl: "",
  callName: "",
  llmProvider: "gemini",
  llmApiKey: "",
};

export function loadUserSettings(): UserSettings {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null") as Partial<UserSettings> | null;
    if (!parsed) return defaultUserSettings;
    return {
      ...defaultUserSettings,
      ...parsed,
      iconText: (parsed.iconText || defaultUserSettings.iconText).slice(0, 2),
    };
  } catch {
    return defaultUserSettings;
  }
}

function saveUserSettings(settings: UserSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

export function UserSettingsView({
  onClose,
  userEmail,
  onSaved,
}: {
  onClose: () => void;
  userEmail: string;
  onSaved: (settings: UserSettings) => void;
}) {
  const [settings, setSettings] = useState<UserSettings>(() => loadUserSettings());
  const [saved, setSaved] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);

  function patch(next: Partial<UserSettings>) {
    setSaved(false);
    setImageError(null);
    setSettings((current) => ({ ...current, ...next }));
  }

  function handleSave() {
    const normalized: UserSettings = {
      ...settings,
      iconText: (settings.iconText.trim() || defaultUserSettings.iconText).slice(0, 2),
      callName: settings.callName.trim(),
      llmApiKey: settings.llmApiKey.trim(),
    };
    setSettings(normalized);
    saveUserSettings(normalized);
    onSaved(normalized);
    setSaved(true);
  }

  function handleClearKey() {
    patch({ llmApiKey: "" });
  }

  function handleIconImage(file: File | null) {
    setSaved(false);
    setImageError(null);
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setImageError("画像ファイルを選んでください。");
      return;
    }
    if (file.size > 700 * 1024) {
      setImageError("画像は 700KB 以下にしてください。");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        patch({ iconImageDataUrl: reader.result });
      }
    };
    reader.onerror = () => setImageError("画像を読み込めませんでした。");
    reader.readAsDataURL(file);
  }

  return (
    <div className="user-settings">
      <div className="settings-head">
        <button className="back" onClick={onClose}>閉じる</button>
        <h2>ユーザー設定</h2>
      </div>

      <section className="settings-section settings-section--profile">
        <div
          className={settings.iconImageDataUrl ? "user-avatar-preview user-avatar-preview--image" : "user-avatar-preview"}
          style={settings.iconImageDataUrl ? undefined : { background: settings.iconColor }}
          aria-label="現在のユーザーアイコン"
        >
          {settings.iconImageDataUrl ? (
            <img src={settings.iconImageDataUrl} alt="" />
          ) : (
            settings.iconText || defaultUserSettings.iconText
          )}
        </div>
        <div className="settings-summary">
          <h3>{settings.callName || "呼び名未設定"}</h3>
          <p>{userEmail}</p>
          <span>API Key: デモ期間中は機能停止</span>
        </div>
      </section>

      <section className="settings-section">
        <h3>ユーザーアイコン</h3>
        <div className="settings-grid">
          <label>
            画像
            <input
              type="file"
              accept="image/*"
              onChange={(e) => handleIconImage(e.currentTarget.files?.[0] ?? null)}
            />
          </label>
          <label>
            表示文字
            <input
              maxLength={2}
              value={settings.iconText}
              onChange={(e) => patch({ iconText: e.target.value })}
              placeholder="A"
            />
          </label>
          <label>
            アイコン色
            <input
              type="color"
              value={settings.iconColor}
              onChange={(e) => patch({ iconColor: e.target.value })}
            />
          </label>
          <div className="settings-inline-actions">
            <button className="settings-secondary" onClick={() => patch({ iconImageDataUrl: "" })}>
              画像を外す
            </button>
            <span>画像がある場合は画像を優先します。</span>
          </div>
        </div>
        {imageError && <div className="error">{imageError}</div>}
      </section>

      <section className="settings-section">
        <h3>AI から呼んでもらう名前</h3>
        <label className="settings-field">
          呼び名
          <input
            value={settings.callName}
            onChange={(e) => patch({ callName: e.target.value })}
            placeholder="例: 山下さん"
          />
        </label>
      </section>

      <section className="settings-section settings-section--disabled" aria-disabled="true">
        <div className="settings-title-row">
          <h3>使用する LLM の API Key</h3>
          <span className="settings-disabled-badge">デモ期間中は機能停止</span>
        </div>
        <div className="settings-grid settings-grid--disabled">
          <label>
            Provider
            <select
              value={settings.llmProvider}
              onChange={(e) => patch({ llmProvider: e.target.value as LlmProvider })}
              disabled
            >
              <option value="gemini">Gemini</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Claude / Anthropic</option>
              <option value="codex">Codex CLI</option>
            </select>
          </label>
          <label>
            API Key
            <input
              type="password"
              value={settings.llmApiKey}
              onChange={(e) => patch({ llmApiKey: e.target.value })}
              placeholder="sk-... / AIza..."
              autoComplete="off"
              disabled
            />
          </label>
        </div>
        <p className="settings-note">
          デモ期間中、この機能は停止しています。API Key の入力・保存・接続テストはできません。
        </p>
      </section>

      <div className="settings-actions">
        <button className="admin-save" onClick={handleSave}>保存</button>
        <button className="settings-secondary" onClick={handleClearKey} disabled>API Key を消す</button>
        {saved && <span className="settings-saved">保存しました</span>}
      </div>
    </div>
  );
}
