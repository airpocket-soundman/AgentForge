// Standard Gantt/timeline component (Chart.js stacked horizontal bar trick).
// The manifest declares {label, start, end}; this draws floating bars per row.
import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  LinearScale,
  Title,
  Tooltip,
} from "chart.js";
import { Bar } from "react-chartjs-2";
import type { Entity, GanttSpec } from "../api";

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip);

const DAY = 86_400_000;

export function GanttChart({ gantt, items }: { gantt: GanttSpec; items: Entity[] }) {
  const rows = items
    .map((it) => ({
      label: String(it.data[gantt.label] ?? "—"),
      start: Date.parse(String(it.data[gantt.start])),
      end: Date.parse(String(it.data[gantt.end])),
    }))
    .filter((r) => !Number.isNaN(r.start) && !Number.isNaN(r.end) && r.end >= r.start);

  if (!rows.length) return null;

  const min = Math.min(...rows.map((r) => r.start));
  const fmt = (d: number) => new Date(min + d * DAY).toLocaleDateString();

  const data: any = {
    labels: rows.map((r) => r.label),
    datasets: [
      { label: "offset", data: rows.map((r) => (r.start - min) / DAY), backgroundColor: "transparent", stack: "g" },
      { label: "期間", data: rows.map((r) => Math.max(1, (r.end - r.start) / DAY + 1)), backgroundColor: "#4a4ae0", borderRadius: 4, stack: "g" },
    ],
  };

  const options: any = {
    indexAxis: "y" as const,
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx: { datasetIndex: number; dataIndex: number }) =>
            ctx.datasetIndex === 1 ? `${fmt((data.datasets[0].data[ctx.dataIndex]))}` : "",
        },
      },
    },
    scales: {
      x: { stacked: true, ticks: { callback: (v: string | number) => fmt(Number(v)) } },
      y: { stacked: true },
    },
  };

  return (
    <div className="gen-chart gen-chart--wide">
      <Bar data={data} options={options} />
    </div>
  );
}
