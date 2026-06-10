import { useEffect, useState } from "react";
import {
  getHistory,
  getWorkers,
  stopAllWorkers,
  type HistoryEntry,
  type RunningWorker,
  type WorkerRegistryEntry,
  type WorkerUsage,
} from "../api";

// Status monitor: the worker registry (type/status/model), the background builds
// running right now, this project's run-rate usage (loop guard), the change
// history (who/what/when), and a global stop.
const PHASE_LABEL: Record<string, string> = {
  planning: "設計案",
  revising: "設計案修正",
  codegen: "コード生成",
  editing: "修正版",
};
const HEALTH_LABEL: Record<string, string> = {
  progressing: "🟢 順調",
  slow: "🟡 遅延",
  stuck: "🔴 停止の可能性",
};
const STATUS_LABEL: Record<string, string> = {
  active: "🟢 活動中",
  idle: "🟡 待機中",
  stopped: "⚪ 停止中",
};
// Human-readable labels for the audit actions shown in the change history.
const ACTION_LABEL: Record<string, string> = {
  "generated_view.pending": "生成（承認待ち）",
  "approval.approved": "公開（有効化）",
  "approval.rejected": "却下",
  "generated_view.edited": "改変を公開",
  "feature.rolled_back": "巻き戻し",
  "feature.disabled": "無効化",
  "feature.worker_toggled": "ワーカー切替",
  "system.reset": "初期化",
};

export function StatusView({ onBack }: { onBack: () => void }) {
  const [registry, setRegistry] = useState<WorkerRegistryEntry[]>([]);
  const [workers, setWorkers] = useState<RunningWorker[]>([]);
  const [usage, setUsage] = useState<WorkerUsage | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);

  async function load() {
    try {
      const [w, h] = await Promise.all([getWorkers(), getHistory(undefined, 50)]);
      setRegistry(w.registry ?? []);
      setWorkers(w.workers);
      setUsage(w.usage);
      setHistory(h.history ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 3000);
    return () => clearInterval(id);
  }, []);

  async function stopAll() {
    if (stopping) return;
    if (!confirm("実行中のワーカーをすべて停止します（全セッション）。よろしいですか？")) return;
    setStopping(true);
    try {
      await stopAllWorkers();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStopping(false);
    }
  }

  return (
    <div className="view status-view">
      <div className="view__head">
        <h2>📊 ステータスモニタ</h2>
        <span className="spacer" />
        <button className="navitem" onClick={onBack}>← 戻る</button>
      </div>

      <div className="status-actions">
        <button className="rollback-top" onClick={() => void stopAll()} disabled={stopping}>
          ■ 全セッション停止
        </button>
        <button className="navitem" onClick={() => void load()}>↻ 更新</button>
      </div>

      {error && <div className="error">{error}</div>}

      {usage && (
        <div className="gen-desc">
          実行レート（このプロジェクト・直近{Math.round(usage.window_sec / 60)}分）:{" "}
          <b>{usage.runs_in_window}</b> / {usage.max_runs}　・累計実行 {usage.total_runs}　・
          ループ保護による停止 {usage.total_blocked}
        </div>
      )}

      <h3 className="status-sub">ワーカー（{registry.length}）</h3>
      {registry.length === 0 ? (
        <div className="sidebar__hint">まだワーカーの稼働記録はありません。</div>
      ) : (
        <table className="status-table">
          <thead>
            <tr>
              <th>ワーカー</th>
              <th>状態</th>
              <th>状況</th>
              <th>使用モデル</th>
              <th>最終更新</th>
            </tr>
          </thead>
          <tbody>
            {registry.map((w) => (
              <tr key={`${w.worker_type}:${w.project_id}`}>
                <td>{w.worker_type}</td>
                <td>{STATUS_LABEL[w.status] ?? w.status}{w.stale ? "（応答なし）" : ""}</td>
                <td className="status-goal">{w.detail || "—"}</td>
                <td className="status-goal">{w.model || "—"}</td>
                <td>{w.since_update_sec}s前</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 className="status-sub">起動中のバックグラウンド作業（{workers.length}）</h3>
      {workers.length === 0 ? (
        <div className="sidebar__hint">現在、実行中の作業はありません。</div>
      ) : (
        <table className="status-table">
          <thead>
            <tr>
              <th>セッション</th>
              <th>フェーズ</th>
              <th>内容</th>
              <th>経過</th>
              <th>状態</th>
            </tr>
          </thead>
          <tbody>
            {workers.map((w) => (
              <tr key={w.conversation_id}>
                <td>{w.project_id}</td>
                <td>{PHASE_LABEL[w.phase ?? ""] ?? w.phase ?? "—"}</td>
                <td className="status-goal">{w.goal || "—"}</td>
                <td>{w.total_sec}s</td>
                <td>{HEALTH_LABEL[w.health] ?? w.health}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 className="status-sub">変更履歴（{history.length}）</h3>
      {history.length === 0 ? (
        <div className="sidebar__hint">まだ変更履歴はありません。</div>
      ) : (
        <table className="status-table">
          <thead>
            <tr>
              <th>日時</th>
              <th>操作</th>
              <th>対象</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h) => (
              <tr key={h.log_id}>
                <td>{h.created_at?.slice(0, 19).replace("T", " ") || "—"}</td>
                <td>{ACTION_LABEL[h.action] ?? h.action}</td>
                <td className="status-goal">{h.target || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
