import { useEffect, useState } from "react";
import {
  createEntity,
  deleteEntity,
  getView,
  listEntities,
  type Entity,
  type ViewManifest,
} from "../api";
import ReactMarkdown from "react-markdown";
import { FeatureWorkerPanel } from "./FeatureWorkerPanel";
import { FeatureCharts } from "./FeatureCharts";
import { FeatureStats } from "./FeatureStats";
import { GanttChart } from "./GanttChart";
import { CalendarView } from "./CalendarView";

// Generated View Renderer: draws a feature screen from the view_manifest the UI
// Designer worker produced (form + list, bound to the generic CRUD). This is what
// makes an arbitrary AI-generated feature actually appear and work.
function msg(e: unknown) { return e instanceof Error ? e.message : String(e); }
function fmt(v: unknown) {
  if (v === true) return "✓";
  if (v === false || v == null || v === "") return "—";
  return String(v);
}

export function GeneratedView({ feature }: { feature: string }) {
  const [manifest, setManifest] = useState<ViewManifest | null>(null);
  const [items, setItems] = useState<Entity[]>([]);
  const [form, setForm] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function loadItems() {
    listEntities(feature).then((r) => setItems(r.items)).catch((e) => setError(msg(e)));
  }

  useEffect(() => {
    setError(null);
    setManifest(null);
    getView(feature).then(setManifest).catch((e) => setError(msg(e)));
    loadItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feature]);

  async function add() {
    if (!manifest || busy) return;
    const data: Record<string, unknown> = {};
    for (const f of manifest.fields) {
      const v = form[f.key];
      if (f.type === "checkbox") data[f.key] = v === "true";
      else if (f.type === "number") data[f.key] = v ? Number(v) : null;
      else data[f.key] = v ?? "";
    }
    setBusy(true);
    setError(null);
    try {
      await createEntity(feature, data);
      setForm({});
      loadItems();
    } catch (e) {
      setError(msg(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    try {
      await deleteEntity(id);
      loadItems();
    } catch (e) {
      setError(msg(e));
    }
  }

  if (error && !manifest) return <div className="view"><div className="error">{error}</div></div>;
  if (!manifest) return <div className="view">読み込み中…</div>;

  const cols = manifest.list_columns.length ? manifest.list_columns : manifest.fields.map((f) => f.key);
  const labelOf = (k: string) => manifest.fields.find((f) => f.key === k)?.label ?? k;
  const typeOf = (k: string) => manifest.fields.find((f) => f.key === k)?.type;

  return (
    <div className="view">
      <div className="view__head">
        <h2>{manifest.title}</h2>
        <span className="hint">🤖 AI生成（{manifest.generated_by}）</span>
      </div>

      <FeatureStats stats={manifest.stats ?? []} items={items} />

      <FeatureWorkerPanel feature={feature} onChanged={loadItems} />

      <div className="gen-form">
        {manifest.fields.map((f) => (
          <label key={f.key} className="gen-field">
            <span>{f.label}</span>
            {f.type === "textarea" || f.type === "markdown" ? (
              <textarea rows={2} value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
            ) : f.type === "checkbox" ? (
              <input type="checkbox" checked={form[f.key] === "true"} onChange={(e) => setForm({ ...form, [f.key]: String(e.target.checked) })} />
            ) : (
              <input
                type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
                value={form[f.key] ?? ""}
                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
              />
            )}
          </label>
        ))}
        <button onClick={() => void add()} disabled={busy}>追加</button>
      </div>

      {error && <div className="error">{error}</div>}

      <FeatureCharts charts={manifest.charts ?? []} items={items} />
      {manifest.gantt && <GanttChart gantt={manifest.gantt} items={items} />}
      {manifest.calendar && <CalendarView calendar={manifest.calendar} items={items} />}

      <table className="table">
        <thead>
          <tr>
            {cols.map((c) => <th key={c}>{labelOf(c)}</th>)}
            <th style={{ width: 60 }}></th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 && (
            <tr><td colSpan={cols.length + 1} className="table__empty">まだデータがありません</td></tr>
          )}
          {items.map((it) => (
            <tr key={it.entity_id}>
              {cols.map((c) => (
                <td key={c}>
                  {typeOf(c) === "markdown" ? <ReactMarkdown>{String(it.data[c] ?? "")}</ReactMarkdown> : fmt(it.data[c])}
                </td>
              ))}
              <td><button className="gen-del" onClick={() => void remove(it.entity_id)}>削除</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
