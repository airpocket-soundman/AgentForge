import { useEffect, useState } from "react";
import { getWorkers, stopAllWorkers, type RunningWorker, type WorkerUsage } from "../api";

// Status monitor: which background workers are running right now (across all
// sessions), this project's run-rate usage (loop guard), and a global stop.
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

export function StatusView({ onBack }: { onBack: () => void }) {
  const [workers, setWorkers] = useState<RunningWorker[]>([]);
  const [usage, setUsage] = useState<WorkerUsage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);

  async function load() {
    try {
      const r = await getWorkers();
      setWorkers(r.workers);
      setUsage(r.usage);
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

      <h3 className="status-sub">起動中のワーカー（{workers.length}）</h3>
      {workers.length === 0 ? (
        <div className="sidebar__hint">現在、実行中のワーカーはありません。</div>
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
    </div>
  );
}
