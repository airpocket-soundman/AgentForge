// Standard month-calendar component. The manifest declares {date, title}; this
// places each entity on its day. Lightweight (no library). Date fields are stored
// as "YYYY-MM-DD" strings, so we key on the raw string (no timezone surprises).
import { useState } from "react";
import type { CalendarSpec, Entity } from "../api";

const pad = (n: number) => String(n).padStart(2, "0");

export function CalendarView({ calendar, items }: { calendar: CalendarSpec; items: Entity[] }) {
  const byDate = new Map<string, string[]>();
  let anchorY = new Date().getFullYear();
  let anchorM = new Date().getMonth();
  let found = false;
  for (const it of items) {
    const raw = String(it.data[calendar.date] ?? "").slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) continue;
    byDate.set(raw, [...(byDate.get(raw) ?? []), String(it.data[calendar.title] ?? "")]);
    if (!found) {
      anchorY = Number(raw.slice(0, 4));
      anchorM = Number(raw.slice(5, 7)) - 1;
      found = true;
    }
  }

  const [ym, setYm] = useState({ y: anchorY, m: anchorM });
  const startDow = new Date(ym.y, ym.m, 1).getDay();
  const days = new Date(ym.y, ym.m + 1, 0).getDate();
  const cells: (number | null)[] = [
    ...Array.from({ length: startDow }, () => null),
    ...Array.from({ length: days }, (_, i) => i + 1),
  ];
  const key = (day: number) => `${ym.y}-${pad(ym.m + 1)}-${pad(day)}`;
  const move = (delta: number) => {
    const d = new Date(ym.y, ym.m + delta, 1);
    setYm({ y: d.getFullYear(), m: d.getMonth() });
  };

  return (
    <div className="gen-cal">
      <div className="gen-cal__head">
        <button onClick={() => move(-1)}>‹</button>
        <span>{ym.y}年 {ym.m + 1}月</span>
        <button onClick={() => move(1)}>›</button>
      </div>
      <div className="gen-cal__grid">
        {["日", "月", "火", "水", "木", "金", "土"].map((d) => (
          <div key={d} className="gen-cal__dow">{d}</div>
        ))}
        {cells.map((day, i) => (
          <div key={i} className={day ? "gen-cal__cell" : "gen-cal__cell gen-cal__cell--empty"}>
            {day && (
              <>
                <div className="gen-cal__day">{day}</div>
                {(byDate.get(key(day)) ?? []).map((t, j) => (
                  <div key={j} className="gen-cal__ev" title={t}>{t}</div>
                ))}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
