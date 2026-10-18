"use client";
import Heatmap from "./Heatmap";
import { EXERCISE_LABEL, EXPERIENCE_LABEL, GOAL_LABEL, initials, longDate, shortDate } from "@/lib/format";
import type { Activity, BadgeInfo, ExerciseCard, FeedGroup } from "@/lib/types";

function monthYear(ym: string | null): string {
  if (!ym) return "";
  const [y, m] = ym.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString(undefined, { month: "long", year: "numeric", timeZone: "UTC" });
}

/** Left column, like a GitHub profile. Deliberately NO weight, injuries or other sensitive data (people screenshot this). */
export function ProfileCard({ a }: { a: Activity }) {
  const p = a.profile;
  const name = p.name.replace(/\s*\(demo\)/i, "");
  return (
    <div className="card flex items-center gap-4 md:flex-col md:items-start">
      <div
        aria-hidden
        className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-brand-soft text-2xl font-bold text-brand md:h-28 md:w-28 md:text-4xl"
      >
        {initials(p.name)}
      </div>
      <div className="min-w-0">
        <h2 className="truncate text-xl font-bold">{name}</h2>
        <ul className="mt-1 space-y-0.5 text-sm text-muted">
          {p.goal && <li>🎯 {GOAL_LABEL[p.goal]}</li>}
          {p.experience_level && <li>💪 {EXPERIENCE_LABEL[p.experience_level]}</li>}
          {a.totals.training_since && <li>📅 Training since {monthYear(a.totals.training_since)}</li>}
        </ul>
      </div>
    </div>
  );
}

export function StatsRow({ a }: { a: Activity }) {
  const items: [string, string | number, string?][] = [
    ["Current streak", a.streaks.current, a.streaks.current === 1 ? "day" : "days"],
    ["Longest streak", a.streaks.longest, a.streaks.longest === 1 ? "day" : "days"],
    ["Sessions", a.totals.sessions],
    ["Total reps", a.totals.reps.toLocaleString()],
    ["Avg form (30 days)", a.totals.avg_form_30d ?? "–"],
  ];
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {items.map(([label, value, unit]) => (
        <div key={label} className="card !p-3">
          <div className="text-xs font-medium text-muted">{label}</div>
          <div className="text-2xl font-bold tabular-nums">
            {value}
            {unit && <span className="ml-1 text-sm font-medium text-muted">{unit}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

function Sparkline({ values, color }: { values: number[]; color: string }) {
  if (values.length < 2) return <div className="h-8 text-xs text-muted">Not enough data yet</div>;
  const w = 120;
  const h = 32;
  const min = Math.min(...values, 40);
  const max = Math.max(...values, 100);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - 2 - ((v - min) / (max - min || 1)) * (h - 4)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-8 w-full" role="img" aria-label={`Form score trend: ${values.join(", ")}`}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/** Like GitHub's pinned repositories. */
export function ExerciseCards({ cards }: { cards: ExerciseCard[] }) {
  if (!cards.length) return <p className="hint">No exercises yet. Upload a set to see your first card.</p>;
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {cards.map((c) => (
        <div key={c.exercise} className="card !p-3">
          <div className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-full" style={{ background: c.color }} aria-hidden />
            <h3 className="font-semibold">{EXERCISE_LABEL[c.exercise] ?? c.label}</h3>
          </div>
          <div className="mt-2 flex gap-4 text-sm text-muted">
            <span>{c.sessions} sessions</span>
            <span>Best form {c.best_form ?? "–"}</span>
          </div>
          <div className="mt-2">
            <Sparkline values={c.sparkline} color={c.color} />
          </div>
          <div className="hint mt-1">Last session {shortDate(c.last_date)}</div>
        </div>
      ))}
    </div>
  );
}

const FEED_ICON = { upload: "📹", best_depth: "🏅", approved: "✅", streak: "🔥" } as const;

/** Activity timeline grouped by month. */
export function ActivityFeed({ groups }: { groups: FeedGroup[] }) {
  if (!groups.length) return <p className="hint">Your activity will show up here.</p>;
  return (
    <div className="space-y-4">
      {groups.slice(0, 6).map((g) => (
        <div key={g.month}>
          <h3 className="mb-1 text-sm font-semibold">{g.summary}</h3>
          <ul className="space-y-1 border-l border-line pl-3">
            {g.items.slice(0, 8).map((it, i) => (
              <li key={i} className="text-sm">
                <span aria-hidden>{FEED_ICON[it.type]} </span>
                {it.text}
                <span className="hint ml-2">{shortDate(it.date)}</span>
              </li>
            ))}
            {g.items.length > 8 && <li className="hint">+ {g.items.length - 8} more</li>}
          </ul>
        </div>
      ))}
    </div>
  );
}

export function Badges({ badges }: { badges: BadgeInfo[] }) {
  return (
    <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {badges.map((b) => (
        <li
          key={b.code}
          title={b.earned && b.earned_on ? `${b.description} (${longDate(b.earned_on)})` : b.description}
          className={`card !p-3 text-center ${b.earned ? "" : "opacity-45"}`}
        >
          <div className="text-2xl" aria-hidden>
            {b.earned ? "🏆" : "🔒"}
          </div>
          <div className="text-sm font-semibold">{b.label}</div>
          <div className="hint">{b.earned ? "Earned" : "Not yet"}</div>
        </li>
      ))}
    </ul>
  );
}

/** The whole GitHub-style page. Same component for the client and the coach. */
export default function TrainingDashboard({ a, showProfileCard = true }: { a: Activity; showProfileCard?: boolean }) {
  return (
    <div className={`grid gap-4 ${showProfileCard ? "md:grid-cols-[260px_minmax(0,1fr)]" : ""}`}>
      {showProfileCard && (
        <div className="space-y-4">
          <ProfileCard a={a} />
          <div className="card">
            <h3 className="mb-2 text-sm font-semibold">Badges</h3>
            <Badges badges={a.badges} />
          </div>
        </div>
      )}
      <div className="min-w-0 space-y-4">
        <StatsRow a={a} />
        <div className="card min-w-0">
          <Heatmap days={a.days} totalSets={a.total_sets_last_year} />
        </div>
        <div>
          <h3 className="mb-2 text-sm font-semibold">Exercises</h3>
          <ExerciseCards cards={a.exercise_cards} />
        </div>
        <div className="card">
          <h3 className="mb-3 text-sm font-semibold">Activity</h3>
          <ActivityFeed groups={a.feed} />
        </div>
        {!showProfileCard && (
          <div className="card">
            <h3 className="mb-2 text-sm font-semibold">Badges</h3>
            <Badges badges={a.badges} />
          </div>
        )}
      </div>
    </div>
  );
}
