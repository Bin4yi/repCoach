"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { buildHeatGrid } from "@/lib/heatmap";
import { EXERCISE_LABEL, longDate } from "@/lib/format";
import type { ActivityDay } from "@/lib/types";

const CELL = 12;
const GAP = 3;
const COL_W = CELL + GAP;
const LABEL_W = 30;

function describe(d: ActivityDay): string {
  if (!d.points) return `${longDate(d.date)}: no training`;
  const ex = d.exercises.map((e) => EXERCISE_LABEL[e] ?? e).join(", ");
  return `${longDate(d.date)}: ${ex}, ${d.reps} reps${d.best_form != null ? `, best form ${d.best_form}` : ""}`;
}

/** GitHub-style contribution graph: 7 rows (Mon–Sun) × one column per week. Scrolls sideways on phones. */
export default function Heatmap({ days, totalSets }: { days: ActivityDay[]; totalSets: number }) {
  const grid = useMemo(() => buildHeatGrid(days), [days]);
  const [picked, setPicked] = useState<ActivityDay | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  // start scrolled to "today" (the right edge)
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [days]);

  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold">
        {totalSets} {totalSets === 1 ? "set" : "sets"} in the last year
      </h3>
      <div ref={scroller} className="overflow-x-auto pb-2" data-testid="heatmap-scroll">
        <div style={{ width: LABEL_W + grid.weeks.length * COL_W }}>
          {/* month labels */}
          <div className="relative h-4 text-[11px] text-muted" style={{ marginLeft: LABEL_W }}>
            {grid.months.map((m) => (
              <span key={m.col} className="absolute" style={{ left: m.col * COL_W }}>
                {m.label}
              </span>
            ))}
          </div>
          <div className="flex">
            {/* weekday labels */}
            <div className="grid shrink-0 text-[11px] leading-none text-muted" style={{ width: LABEL_W, gridTemplateRows: `repeat(7, ${CELL}px)`, rowGap: GAP }}>
              {["Mon", "", "Wed", "", "Fri", "", ""].map((l, i) => (
                <span key={i} className="flex items-center">
                  {l}
                </span>
              ))}
            </div>
            <div className="grid" style={{ gridAutoFlow: "column", gridTemplateRows: `repeat(7, ${CELL}px)`, gap: GAP }} role="img" aria-label={`${totalSets} sets in the last year`}>
              {grid.weeks.flatMap((week, c) =>
                week.map((cell, r) =>
                  cell.day ? (
                    <button
                      key={`${c}-${r}`}
                      type="button"
                      title={describe(cell.day)}
                      aria-label={describe(cell.day)}
                      onMouseEnter={() => setPicked(cell.day!)}
                      onFocus={() => setPicked(cell.day!)}
                      onClick={() => setPicked(cell.day!)}
                      className={`heat-cell heat-${cell.day.level} p-0`}
                    />
                  ) : (
                    <span key={`${c}-${r}`} className="heat-cell heat-pad" />
                  ),
                ),
              )}
            </div>
          </div>
        </div>
      </div>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span aria-live="polite" className="min-h-4">
          {picked ? describe(picked) : "Tap a square to see that day."}
        </span>
        <span className="flex items-center gap-1">
          Less
          {[0, 1, 2, 3, 4].map((l) => (
            <span key={l} className={`heat-cell heat-${l}`} />
          ))}
          More
        </span>
      </div>
    </div>
  );
}
