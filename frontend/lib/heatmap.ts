import type { ActivityDay } from "./types";

export interface HeatCell {
  date: string;
  day?: ActivityDay; // undefined = padding cell (before the first day / after today)
}
export interface HeatGrid {
  weeks: HeatCell[][]; // each week = 7 cells, Monday first
  months: { col: number; label: string }[];
}

// Parse YYYY-MM-DD without time-zone surprises (never via new Date("YYYY-MM-DD")).
export function parseISO(iso: string): { y: number; m: number; d: number } {
  const [y, m, d] = iso.split("-").map(Number);
  return { y, m, d };
}
export function weekdayMon0(iso: string): number {
  const { y, m, d } = parseISO(iso);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7; // Mon=0 … Sun=6
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Lay out ~365 days into GitHub-style columns (weeks, Monday on top) with month labels. */
export function buildHeatGrid(days: ActivityDay[]): HeatGrid {
  if (!days.length) return { weeks: [], months: [] };
  const cells: HeatCell[] = [];
  const lead = weekdayMon0(days[0].date);
  for (let i = 0; i < lead; i++) cells.push({ date: "" });
  for (const d of days) cells.push({ date: d.date, day: d });
  while (cells.length % 7) cells.push({ date: "" });

  const weeks: HeatCell[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));

  const months: { col: number; label: string }[] = [];
  let lastMonth = -1;
  weeks.forEach((w, col) => {
    const first = w.find((c) => c.day);
    if (!first) return;
    const { m, d } = parseISO(first.date);
    // label a month on the first column that contains its 1st–7th (skip a cramped label in column 0 if it is a month tail)
    if (m !== lastMonth && (d <= 7 || col === 0)) {
      months.push({ col, label: MONTHS[m - 1] });
      lastMonth = m;
    }
  });
  if (months.length > 1 && months[1].col - months[0].col < 2) months.shift();
  return { weeks, months };
}
