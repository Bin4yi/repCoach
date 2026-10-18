/** Brand mark: a gradient rounded square with a tiny barbell. */
export function Logo({ size = 32, withText = true, sub }: { size?: number; withText?: boolean; sub?: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span
        aria-hidden
        className="inline-flex items-center justify-center rounded-xl shadow-lg"
        style={{
          width: size,
          height: size,
          background: "var(--ink)",
        }}
      >
        <svg viewBox="0 0 32 32" width={size * 0.62} height={size * 0.62}>
          <path d="M7 16h18M10 10v12M22 10v12M5 13v6M27 13v6" stroke="#fff" strokeWidth="3" strokeLinecap="round" fill="none" />
        </svg>
      </span>
      {withText && (
        <span className="text-lg font-bold tracking-tight">
          Rep<span className="text-subtle">Check</span>
          {sub && <span className="ml-1.5 text-xs font-semibold uppercase tracking-wider text-muted">{sub}</span>}
        </span>
      )}
    </span>
  );
}
