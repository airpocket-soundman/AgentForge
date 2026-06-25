import { useEffect, useState } from "react";
import {
  connectConnector,
  disconnectConnector,
  listConnectors,
  type ConnectorInfo,
} from "../api";

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
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [connectorsLoading, setConnectorsLoading] = useState(true);
  const [connectorError, setConnectorError] = useState<string | null>(null);
  const [connectorBusy, setConnectorBusy] = useState<string | null>(null);
  const [connectorCredentials, setConnectorCredentials] = useState<Record<string, Record<string, string>>>({});

  async function refreshConnectors() {
    setConnectorError(null);
    try {
      const data = await listConnectors();
      setConnectors(data.items || []);
    } catch (e) {
      setConnectorError(e instanceof Error ? e.message : String(e));
    } finally {
      setConnectorsLoading(false);
    }
  }

  useEffect(() => {
    void refreshConnectors();
  }, []);

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

  function patchConnectorCredential(connectorId: string, key: string, value: string) {
    setConnectorCredentials((current) => ({
      ...current,
      [connectorId]: {
        ...(current[connectorId] || {}),
        [key]: value,
      },
    }));
  }

  function missingCredentialFields(connector: ConnectorInfo): string[] {
    const current = connectorCredentials[connector.id] || {};
    return (connector.credential_fields || [])
      .filter((field) => field.required)
      .filter((field) => connector.credential_status !== "configured" && !current[field.key]?.trim())
      .map((field) => field.label || field.key);
  }

  async function handleConnectorConnect(connector: ConnectorInfo) {
    const missing = missingCredentialFields(connector);
    if (missing.length > 0) {
      setConnectorError(`${connector.label} の認証情報が不足しています: ${missing.join(", ")}`);
      return;
    }
    setConnectorBusy(connector.id);
    setConnectorError(null);
    try {
      const scopes = connector.scopes.includes("read") ? ["read"] : connector.scopes.slice(0, 1);
      await connectConnector(
        connector.id,
        connector.account_label || userEmail,
        scopes,
        connectorCredentials[connector.id] || {},
      );
      setConnectorCredentials((current) => ({ ...current, [connector.id]: {} }));
      await refreshConnectors();
    } catch (e) {
      setConnectorError(e instanceof Error ? e.message : String(e));
    } finally {
      setConnectorBusy(null);
    }
  }

  async function handleConnectorDisconnect(connector: ConnectorInfo) {
    setConnectorBusy(connector.id);
    setConnectorError(null);
    try {
      await disconnectConnector(connector.id);
      await refreshConnectors();
    } catch (e) {
      setConnectorError(e instanceof Error ? e.message : String(e));
    } finally {
      setConnectorBusy(null);
    }
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

      <section className="settings-section">
        <div className="settings-title-row">
          <h3>外部サービス接続</h3>
          <span className="settings-disabled-badge">ユーザー許可</span>
        </div>
        <p className="settings-note">
          ミニアプリが外部サービスを使うには、ここでユーザーが許可する必要があります。
          認証情報やトークンは画面に表示しません。
        </p>
        {connectorsLoading && <div className="settings-note">接続可能なサービスを読み込み中...</div>}
        {connectorError && <div className="error">{connectorError}</div>}
        <div className="connector-list">
          {connectors.map((connector) => {
            const connected = connector.user_status === "connected";
            const configured = connector.credential_status === "configured";
            const busy = connectorBusy === connector.id;
            const actionCount = Object.keys(connector.actions || {}).length;
            const missing = missingCredentialFields(connector);
            const canSubmit = connector.enabled && !busy && missing.length === 0;
            return (
              <div
                className={connector.enabled ? "connector-card" : "connector-card connector-card--disabled"}
                key={connector.id}
              >
                <div className="connector-card__main">
                  <div className="connector-card__title">
                    <strong>{connector.label}</strong>
                    <span>{connector.enabled ? "管理者有効" : "管理者無効"}</span>
                    {connected && configured && <span className="connector-card__ok">接続済み</span>}
                    {connected && !configured && <span>認証情報未設定</span>}
                  </div>
                  <p>{connector.description}</p>
                  <div className="connector-card__meta">
                    <span>操作 {actionCount}件</span>
                    <span>権限: {(connector.scopes || []).join(", ") || "-"}</span>
                    <span>認証: {connector.credential_status}</span>
                  </div>
                  {(connector.credential_fields || []).length > 0 && (
                    <div className="connector-card__credentials">
                      {(connector.credential_fields || []).map((field) => (
                        <label key={field.key}>
                          {field.label}
                          <input
                            type={field.type === "password" ? "password" : "text"}
                            value={connectorCredentials[connector.id]?.[field.key] || ""}
                            onChange={(e) => patchConnectorCredential(connector.id, field.key, e.target.value)}
                            placeholder={configured ? "保存済み。変更時のみ入力" : field.required ? "必須" : "任意"}
                            autoComplete="off"
                            disabled={!connector.enabled || busy}
                          />
                        </label>
                      ))}
                    </div>
                  )}
                </div>
                <div className="connector-card__actions">
                  {connected ? (
                    <>
                      <button
                        className="admin-save"
                        onClick={() => void handleConnectorConnect(connector)}
                        disabled={!canSubmit}
                      >
                        更新
                      </button>
                      <button
                        className="settings-secondary"
                        onClick={() => void handleConnectorDisconnect(connector)}
                        disabled={busy}
                      >
                        切断
                      </button>
                    </>
                  ) : (
                    <button
                      className="admin-save"
                      onClick={() => void handleConnectorConnect(connector)}
                      disabled={!canSubmit}
                    >
                      接続
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
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
