import { useEffect, useState } from "react";
import {
  createTask,
  disableFeature,
  listTasks,
  setTaskDone,
  type Task,
} from "./api";

export function TaskPanel({ onRollback }: { onRollback: () => void }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      const { tasks } = await listTasks();
      setTasks(tasks);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleAdd() {
    const t = title.trim();
    if (!t || busy) return;
    setBusy(true);
    setError(null);
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

  async function toggle(task: Task) {
    try {
      await setTaskDone(task.task_id, !task.done);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleRollback() {
    if (!confirm("タスク管理機能を無効化（ロールバック）しますか？データは消えません。")) return;
    try {
      await disableFeature("task");
      onRollback();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section className="panel">
      <div className="panel__head">
        <h2>タスク管理 <span className="badge badge--active">active</span></h2>
        <button className="rollback" onClick={() => void handleRollback()}>
          戻す（無効化）
        </button>
      </div>

      <div className="task-add">
        <input
          value={title}
          placeholder="新しいタスク…"
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void handleAdd()}
        />
        <button onClick={() => void handleAdd()} disabled={busy}>
          追加
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      <ul className="task-list">
        {tasks.length === 0 && <li className="task--empty">まだタスクはありません</li>}
        {tasks.map((t) => (
          <li key={t.task_id} className={t.done ? "task task--done" : "task"}>
            <label>
              <input type="checkbox" checked={t.done} onChange={() => void toggle(t)} />
              <span>{t.title}</span>
            </label>
            {t.due_date && <span className="task__due">{t.due_date}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
