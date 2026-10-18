"use client";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RepMetrics } from "@/lib/types";

const AXIS = { fontSize: 11, fill: "var(--muted)" };
const GRID = "var(--line)";
const TIP = {
  background: "var(--glass-strong)",
  border: "1px solid var(--glass-border)",
  borderRadius: 12,
  color: "var(--ink)",
  fontSize: 12,
  boxShadow: "var(--glass-shadow)",
  backdropFilter: "blur(14px)",
};

export interface LineDef {
  key: string;
  label: string;
  color: string;
}

/** Simple time-series line chart. `data` rows need an `x` label plus one numeric field per line. */
export function TrendChart({
  data,
  lines,
  height = 200,
  domain,
  unit,
}: {
  data: Record<string, number | string | null>[];
  lines: LineDef[];
  height?: number;
  domain?: [number | "auto", number | "auto"];
  unit?: string;
}) {
  if (data.length < 2) return <p className="hint">Not enough data yet. Charts appear after two sessions.</p>;
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
          <XAxis dataKey="x" tick={AXIS} minTickGap={24} />
          <YAxis tick={AXIS} domain={domain ?? ["auto", "auto"]} unit={unit} />
          <Tooltip contentStyle={TIP} />
          {lines.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
          {lines.map((l) => (
            <Line key={l.key} type="monotone" dataKey={l.key} name={l.label} stroke={l.color} strokeWidth={2} dot={{ r: 2 }} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** One bar per rep. Flagged reps are red. */
export function RepBars({
  reps,
  field,
  label,
  unit,
  height = 180,
}: {
  reps: RepMetrics[];
  field: string;
  label: string;
  unit?: string;
  height?: number;
}) {
  const data = reps.map((r) => ({ rep: `#${r.rep}`, value: (r[field] as number | null) ?? 0, flagged: r.flags.length > 0 }));
  return (
    <div>
      <div className="mb-1 text-xs font-semibold text-muted">{label}</div>
      <div style={{ height }} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
            <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="rep" tick={AXIS} />
            <YAxis tick={AXIS} unit={unit} />
            <Tooltip contentStyle={TIP} formatter={(v) => [`${v}${unit ?? ""}`, label]} />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.flagged ? "var(--bad)" : "var(--brand)"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
