// Standard KPI/metric tiles. The manifest declares stats (label + value field +
// aggregate); this computes and shows them. No library, no LLM-authored code.
import type { Entity, StatSpec } from "../api";

export function FeatureStats({ stats, items }: { stats: StatSpec[]; items: Entity[] }) {
  if (!stats.length) return null;

  function value(s: StatSpec): string {
    if (s.agg === "count") return String(items.length);
    const nums = items.map((it) => Number(it.data[s.value])).filter((n) => !Number.isNaN(n));
    const sum = nums.reduce((a, b) => a + b, 0);
    if (s.agg === "avg") return nums.length ? (sum / nums.length).toLocaleString(undefined, { maximumFractionDigits: 1 }) : "0";
    return sum.toLocaleString();
  }

  return (
    <div className="gen-stats">
      {stats.map((s, i) => (
        <div key={i} className="gen-stat">
          <div className="gen-stat__label">{s.label}</div>
          <div className="gen-stat__value">{value(s)}</div>
        </div>
      ))}
    </div>
  );
}
