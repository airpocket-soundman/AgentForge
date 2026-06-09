// Standard CHART component for generated features. The manifest declares charts
// (type + which fields); this renders them with Chart.js. The LLM never writes
// chart code — it only picks from the allowed component set (allowlist model).
import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Title,
  Tooltip,
} from "chart.js";
import { Bar, Doughnut, Line, Pie } from "react-chartjs-2";
import type { ChartSpec, Entity } from "../api";

ChartJS.register(
  CategoryScale, LinearScale, BarElement, PointElement, LineElement, ArcElement, Title, Tooltip, Legend,
);

const PALETTE = ["#4a4ae0", "#34a853", "#f9ab00", "#ea4335", "#0e7c9b", "#9333ea", "#e8730c", "#2f8f5b"];

export function FeatureCharts({ charts, items }: { charts: ChartSpec[]; items: Entity[] }) {
  if (!charts.length || !items.length) return null;
  return (
    <div className="gen-charts">
      {charts.map((c, i) => {
        // Aggregate the value field summed by the category field.
        const sums = new Map<string, number>();
        for (const it of items) {
          const k = String(it.data[c.category] ?? "—");
          sums.set(k, (sums.get(k) ?? 0) + (Number(it.data[c.value]) || 0));
        }
        const labels = [...sums.keys()];
        const values = [...sums.values()];
        const colors = labels.map((_, j) => PALETTE[j % PALETTE.length]);
        const data: any = {
          labels,
          datasets: [{ label: c.title || c.value, data: values, backgroundColor: colors, borderColor: "#4a4ae0" }],
        };
        const options: any = {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: c.type === "pie" || c.type === "doughnut" },
            title: { display: !!c.title, text: c.title },
          },
        };
        return (
          <div key={i} className="gen-chart">
            {c.type === "bar" && <Bar data={data} options={options} />}
            {c.type === "line" && <Line data={data} options={options} />}
            {c.type === "pie" && <Pie data={data} options={options} />}
            {c.type === "doughnut" && <Doughnut data={data} options={options} />}
          </div>
        );
      })}
    </div>
  );
}
