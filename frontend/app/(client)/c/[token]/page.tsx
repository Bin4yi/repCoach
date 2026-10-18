"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { TrendChart } from "@/components/Charts";
import ProfileForm from "@/components/ProfileForm";
import { ErrorBox, Section, Spinner, useLoad } from "@/components/ui";
import { ClientNav } from "@/components/ClientNav";
import { api } from "@/lib/api";
import { EXERCISE_LABEL, longDate, shortDate } from "@/lib/format";

const DAY = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function ClientHomePage() {
  const { token } = useParams<{ token: string }>();
  const { data, error, loading, reload } = useLoad(() => api.home(token), [token]);
  const [editing, setEditing] = useState(false);

  if (loading && !data) return <Spinner />;
  if (error || !data) return <main className="mx-auto max-w-xl px-4 py-10"><ErrorBox message={error ?? "Not found"} onRetry={reload} /></main>;

  if (!data.profile_complete || editing) {
    return (
      <main className="mx-auto max-w-xl space-y-4 px-4 py-6">
        <h1 className="text-2xl font-bold">{data.profile_complete ? "Your profile" : `Welcome${data.name ? ", " + data.name.split(" ")[0] : ""}!`}</h1>
        {!data.profile_complete && <p className="text-muted">Tell us a little about you. It takes one minute and helps your coach.</p>}
        <ProfileForm token={token} profile={data.profile} alreadyConsented={data.consented} onSaved={() => { setEditing(false); reload(); }} />
        {data.profile_complete && <button className="btn btn-ghost w-full" onClick={() => setEditing(false)}>Cancel</button>}
      </main>
    );
  }

  const chart = [...data.reports].reverse().filter((r) => r.form_score != null).map((r) => ({ x: shortDate(r.created_at), form: r.form_score }));
  const weight = data.weight_log.map((w) => ({ x: shortDate(w.date), kg: w.kg }));

  return (
    <main className="mx-auto max-w-2xl space-y-4 px-4 py-6">
      <ClientNav token={token} />
      <h1 className="text-3xl font-extrabold tracking-tight">Hi <span className="text-gradient">{data.name.split(" ")[0].replace(/\s*\(demo\)/i, "")}</span> 👋</h1>

      {data.reshoot_reason && (
        <div role="alert" className="card border-warn/40 bg-warn-soft">
          <p className="font-semibold">Please film your last set again</p>
          <p className="text-sm">{data.reshoot_reason}</p>
        </div>
      )}
      {data.pending_count > 0 && (
        <div className="card bg-info-soft text-sm">
          📬 {data.pending_count} {data.pending_count === 1 ? "video is" : "videos are"} waiting. Your coach will send feedback soon.
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Link href={`/c/${token}/upload`} className="btn">Upload a set</Link>
        <Link href={`/c/${token}/profile`} className="btn btn-ghost">My training</Link>
      </div>

      {data.plan && (
        <Section title={`Your plan${data.plan_week_start ? ` · week of ${longDate(data.plan_week_start)}` : ""}`}>
          <p className="mb-2 text-sm">{data.plan.focus}</p>
          <ul className="divide-y divide-line">
            {data.plan.sessions.map((s, i) => (
              <li key={i} className="py-2 text-sm">
                <div className="flex justify-between gap-2 font-semibold">
                  <span>{DAY[s.day]} · {EXERCISE_LABEL[s.exercise] ?? s.exercise}</span>
                  <span>{s.sets} × {s.reps}</span>
                </div>
                <div className="text-muted">{s.load_suggestion} · tempo {s.tempo}</div>
                {s.cue && <div className="text-muted">Tip: {s.cue}</div>}
              </li>
            ))}
          </ul>
          <p className="hint mt-2">{data.plan.progression_rule}</p>
        </Section>
      )}

      <Section title="My reports">
        {data.reports.length === 0 ? (
          <p className="text-sm text-muted">No reports yet. After you upload a set, your coach reviews it and the feedback shows up here.</p>
        ) : (
          <ul className="space-y-3">
            {data.reports.map((r) => (
              <li key={r.id} className="tile p-3">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold">{EXERCISE_LABEL[r.exercise]} · {r.rep_count} reps</span>
                  <span className="hint">{longDate(r.created_at)}</span>
                </div>
                {r.form_score != null && <div className="text-sm text-muted">Form score {r.form_score}</div>}
                <p className="mt-2 whitespace-pre-wrap text-sm">{r.message}</p>
                {r.progress_message && <p className="mt-2 whitespace-pre-wrap rounded-lg bg-brand-soft p-2 text-sm">{r.progress_message}</p>}
              </li>
            ))}
          </ul>
        )}
      </Section>

      {chart.length >= 2 && (
        <Section title="Form score over time">
          <TrendChart data={chart} lines={[{ key: "form", label: "Form score", color: "var(--brand)" }]} domain={[0, 100]} />
        </Section>
      )}
      {weight.length >= 2 && (
        <Section title="My weight (only you and your coach see this)">
          <TrendChart data={weight} lines={[{ key: "kg", label: "kg", color: "#6366f1" }]} />
        </Section>
      )}

      <button className="btn btn-ghost w-full" onClick={() => setEditing(true)}>Edit my profile</button>
      <p className="hint text-center">RepCheck is a coaching helper, not a medical tool. If something hurts, stop and talk to your coach.</p>
    </main>
  );
}
