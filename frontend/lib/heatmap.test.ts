// Run with: npm test  (Node's built-in test runner)
import assert from "node:assert/strict";
import { test } from "node:test";
import { buildHeatGrid, weekdayMon0 } from "./heatmap.ts";

function daysFrom(start: string, n: number) {
  const out = [];
  const [y, m, d] = start.split("-").map(Number);
  for (let i = 0; i < n; i++) {
    const dt = new Date(Date.UTC(y, m - 1, d + i));
    out.push({
      date: dt.toISOString().slice(0, 10),
      level: 0 as const,
      points: 0,
      exercises: [],
      reps: 0,
      best_form: null,
    });
  }
  return out;
}

test("weekday uses Monday as 0", () => {
  assert.equal(weekdayMon0("2026-10-19"), 0); // Monday
  assert.equal(weekdayMon0("2026-10-18"), 6); // Sunday
});

test("grid has 7 rows per week, Monday first, and pads the first column", () => {
  const g = buildHeatGrid(daysFrom("2026-10-14", 10)); // starts on a Wednesday
  assert.ok(g.weeks.every((w) => w.length === 7));
  assert.equal(g.weeks[0][0].day, undefined); // Mon padding
  assert.equal(g.weeks[0][2].date, "2026-10-14");
});

test("365 days make 53 or 54 columns and month labels in order", () => {
  const g = buildHeatGrid(daysFrom("2025-10-19", 365));
  assert.ok(g.weeks.length >= 52 && g.weeks.length <= 54);
  assert.equal(g.weeks.flat().filter((c) => c.day).length, 365);
  assert.ok(g.months.length >= 11);
  const cols = g.months.map((m) => m.col);
  assert.deepEqual(cols, [...cols].sort((a, b) => a - b));
});

test("empty input", () => {
  assert.deepEqual(buildHeatGrid([]), { weeks: [], months: [] });
});
