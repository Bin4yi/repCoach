"use client";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { FLAG_LABEL } from "@/lib/format";
import type { Warning } from "@/lib/types";

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="py-10 text-center text-muted">
      {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="card !border-bad/40 !bg-bad-soft text-bad">
      <p>{message}</p>
      {onRetry && (
        <button className="btn btn-ghost mt-2" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

/** Fetch on mount with loading + error state. `onUnauthorized` lets coach pages bounce to /login. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = [], onUnauthorized?: () => void) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    fn()
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 401 && onUnauthorized) return onUnauthorized();
        setError(e instanceof Error ? e.message : "Something went wrong.");
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, loading, reload: () => setTick((t) => t + 1), setData };
}

export function WarningChips({ warnings }: { warnings: Warning[] }) {
  if (!warnings.length) return <span className="chip chip-good">All good</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {warnings.map((w) => (
        <span key={w.code} className={`chip chip-${w.level}`}>
          {w.level === "red" ? "⚠ " : ""}
          {w.text}
        </span>
      ))}
    </span>
  );
}

export function FlagChip({ code, severity }: { code: string; severity?: "low" | "medium" | "high" }) {
  const cls = severity === "high" ? "chip-red" : severity === "medium" ? "chip-amber" : "chip-info";
  return <span className={`chip ${cls}`}>{FLAG_LABEL[code] ?? code}</span>;
}

export function Section({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="card">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="card !p-3">
      <div className="text-xs font-medium text-muted">{label}</div>
      <div className="text-gradient mt-0.5 text-2xl font-extrabold tabular-nums">{value}</div>
      {sub && <div className="hint">{sub}</div>}
    </div>
  );
}
