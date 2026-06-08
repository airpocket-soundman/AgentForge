import { useEffect, useState } from "react";
import { createTask, listTasks, setTaskDone, type Task } from "../api";
import { FeatureWorkerPanel } from "./FeatureWorkerPanel";

export function TaskListView({ onOpenTask }: { onOpenTask: (taskId: string) => void }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setTasks((await listTasks()).tasks);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function add() {
    const t = title.trim();
    if (!t || busy) return;
    setBusy(true);
    try {
      await createTask(t);
      setTitle("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggle(task: Task, e: React.MouseEvent) {
    e.stopPropagation();
    await setTaskDone(task.task_id, !task.done);
    await refresh();
  }

  return (
    <div className="view">
      <div className="view__head">
        <h2>タスク管理</h2>
      </div>

      <FeatureWorkerPanel feature="task" onChanged={() => void refresh()} />

      <div className="task-add">
        <input
          value={title}
          placeholder="新しいタスク…"
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void add()}
        />
        <button onClick={() => void add()} disabled={busy}>追加</button>
      </div>

      {error && <div className="error">{error}</div>}

      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 40 }}>完了</th>
            <th>タイトル</th>
            <th style={{ width: 120 }}>期日</th>
          </tr>
        </thead>
        <tbody>
          {tasks.length === 0 && (
            <tr><td colSpan={3} className="table__empty">まだタスクはありません</td></tr>
          )}
          {tasks.map((t) => (
            <tr key={t.task_id} className="table__row" onClick={() => onOpenTask(t.task_id)}>
              <td onClick={(e) => void toggle(t, e)}>
                <input type="checkbox" checked={t.done} readOnly />
              </td>
              <td className={t.done ? "table__title--done" : ""}>{t.title}</td>
              <td className="table__due">{t.due_date ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">行をクリックすると詳細・ワーカーエージェントとの会話が開きます。</p>
    </div>
  );
}
