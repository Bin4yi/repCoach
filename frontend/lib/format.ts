import type { Experience, Goal, Trend } from "./types";

export const EXERCISE_LABEL: Record<string, string> = {
  squat: "Squat",
  pushup: "Push-up",
  bicep_curl: "Bicep curl",
};
export const EXERCISE_COLOR: Record<string, string> = {
  squat: "#1d1d1f",
  pushup: "#ff9500",
  bicep_curl: "#34c759",
};

export const GOAL_LABEL: Record<Goal, string> = {
  strength: "Get stronger",
  muscle_gain: "Build muscle",
  fat_loss: "Lose fat",
  general_fitness: "General fitness",
  rehab_return: "Return after rehab",
};
export const EXPERIENCE_LABEL: Record<Experience, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};

export const FLAG_LABEL: Record<string, string> = {
  shallow_depth: "Shallow depth",
  excess_forward_lean: "Too much forward lean",
  knee_cave: "Knees cave in",
  depth_drops_with_fatigue: "Depth drops when tired",
  rushed_eccentric: "Rushed on the way down",
  partial_range: "Partial range",
  hip_sag: "Hips sag",
  hips_high: "Hips too high",
  no_lockout: "No lockout",
  elbow_drift: "Elbow drift",
  body_swing: "Body swing",
};

export const TREND_ICON: Record<Trend, string> = {
  improving: "↗",
  stable: "→",
  declining: "↘",
  not_enough_data: "·",
};

export function initials(name: string): string {
  const parts = name.replace(/\(demo\)/i, "").trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
export function longDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
export function daysAgo(iso: string | null): string {
  if (!iso) return "never";
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  return d <= 0 ? "today" : d === 1 ? "yesterday" : `${d} days ago`;
}

export function scoreColor(score: number | null): string {
  if (score == null) return "text-muted";
  return score >= 80 ? "text-good" : score >= 60 ? "text-warn" : "text-bad";
}
