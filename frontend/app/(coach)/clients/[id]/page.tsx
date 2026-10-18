"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { TrendChart } from "@/components/Charts";
import { CoachShell } from "@/components/CoachShell";
import PlanEditor from "@/components/PlanEditor";
import TrainingDashboard from "@/components/TrainingDashboard";
import { ErrorBox, FlagChip, Section, Spinner, useLoad, WarningChips } from "@/components/ui";
import { api } from "@/lib/api";
import { EXERCISE_COLOR, EXERCISE_LABEL, EXPERIENCE_LABEL, GOAL_LABEL, longDate, scoreColor, shortDate } from "@/lib/format";
import type { CoachClientDetail, Exercise, Goal, Experience } from "@/lib/types";

export default function ClientPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const unauth = () => router.replace("/login");
  const { data, error, loading, reload } = useLoad(() => api.client(id), [id], unauth);
  const act = useLoad(() => api.clientActivity(id), [id], unauth);
  const [exercise, setExercise] = useState<Exercise | null>(null);
  const [planBusy, setPlanBusy] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);

  const exercises = useMemo(() => (data ? (Object.keys(data.series) as Exercise[]) : []), [data]);
  const ex = exercise ?? exercises[0] ?? null;

  if (loading && !data) return <CoachShell><Spinner /></CoachShell>;
  if (error || !data) return <CoachShell><ErrorBox message={error ?? "Not found"} onRetry={reload} /></CoachShell>;

  const formData = mergeSeries(data, exercises, "form_score");
  const relData = mergeSeries(data, exercises, "relative_load");
  const series = ex ? data.series[ex] : [];
  const depthData = series.map((p) => ({ x: shortDate(p.date), depth: p.depth, down: p.eccentric_s, up: p.concentric_s }));
  const weight = data.weight_log.map((w) => ({ x: shortDate(w.date), kg: w.kg }));
  const lines = exercises.map((e) => ({ key: e, label: EXERCISE_LABEL[e], color: EXERCISE_COLOR[e] }));

  async function makePlan() {
    setPlanBusy(true);
    setPlanError(null);
    try {
      await api.generatePlan(id);
      reload();
    } catch (e) {
      setPlanError(e instanceof Error ? e.message : "Could not make a plan.");
    } finally {
      setPlanBusy(false);
    }
  }

  return (
    <CoachShell wide>
      <div className="space-y-4">
        <div>
          <Link href="/dashboard" className="text-sm text-muted">← All clients</Link>
          <h1 className="mt-1 text-2xl font-bold">{data.name}</h1>
          <div className="mt-1"><WarningChips warnings={data.warnings} /></div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
          <div className="space-y-4">
            <ProfileEditor data={data} onSaved={reload} />
            <Section title="Private client link">
              <code className="block break-all text-xs">{data.link}</code>
              <button className="btn btn-ghost mt-2 w-full" onClick={() => navigator.clipboard?.writeText(data.link)}>Copy link</button>
              <p className="hint mt-2">{data.consent_at ? `Privacy note accepted ${longDate(data.consent_at)}.` : "The client has not accepted the privacy note yet."}</p>
            </Section>
          </div>

          <div className="min-w-0 space-y-4">
            <Section title="Sessions" right={<span className="hint">{data.sessions.length} total</span>}>
              {data.sessions.length === 0 ? <p className="text-sm text-muted">No uploads yet.</p> : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[34rem] text-left text-sm">
                    <thead className="text-xs text-muted"><tr><th className="py-1">Date</th><th>Exercise</th><th>Reps</th><th>Load</th><th>Form</th><th>Flags</th><th>Status</th></tr></thead>
                    <tbody>
                      {data.sessions.slice(0, 15).map((s) => (
                        <tr key={s.id} className="border-t border-line align-top">
                          <td className="py-2"><Link className="font-medium underline" href={`/sessions/${s.id}`}>{shortDate(s.created_at)}</Link></td>
                          <td>{EXERCISE_LABEL[s.exercise]}</td>
                          <td>{s.rep_count ?? "–"}</td>
                          <td>{s.load_kg ? `${s.load_kg} kg` : "BW"}</td>
                          <td className={`font-bold ${scoreColor(s.form_score)}`}>{s.form_score ?? "–"}</td>
                          <td className="space-x-1">{s.pain && <span className="chip chip-red">⚠ pain</span>}{s.flags.slice(0, 2).map((f) => <FlagChip key={f} code={f} />)}</td>
                          <td><StatusChip status={s.status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Section>

            <Section title="Form score over time">
              <TrendChart data={formData} lines={lines} domain={[0, 100]} />
            </Section>
            <div className="grid gap-4 md:grid-cols-2">
              <Section title="Relative strength (load ÷ body weight)"><TrendChart data={relData} lines={lines} /></Section>
              <Section title="Body weight (coach only)"><TrendChart data={weight} lines={[{ key: "kg", label: "kg", color: "#6366f1" }]} /></Section>
            </div>

            {exercises.length > 0 && (
              <Section
                title="Depth and tempo"
                right={
                  <select aria-label="Exercise" className="field !min-h-9 !w-auto !py-1 text-sm" value={ex ?? ""} onChange={(e) => setExercise(e.target.value as Exercise)}>
                    {exercises.map((e) => <option key={e} value={e}>{EXERCISE_LABEL[e]}</option>)}
                  </select>
                }
              >
                <div className="grid gap-4 md:grid-cols-2">
                  <div><div className="mb-1 text-xs font-semibold text-muted">Average depth angle (lower = deeper)</div>
                    <TrendChart data={depthData} lines={[{ key: "depth", label: "Depth °", color: "var(--brand)" }]} height={170} /></div>
                  <div><div className="mb-1 text-xs font-semibold text-muted">Seconds per phase</div>
                    <TrendChart data={depthData} lines={[{ key: "down", label: "Down (s)", color: "#f59e0b" }, { key: "up", label: "Up (s)", color: "#3b82f6" }]} height={170} /></div>
                </div>
              </Section>
            )}

            <Section title="Next week plan" right={<button className="btn" onClick={makePlan} disabled={planBusy}>{planBusy ? "Writing…" : "Generate next week plan"}</button>}>
              {planError && <p role="alert" className="mb-2 text-sm text-bad">{planError}</p>}
              {data.plans.length === 0 ? <p className="text-sm text-muted">No plan yet. Gemma writes a draft from the recent numbers; you review and approve it.</p> : (
                <div className="space-y-5">
                  {data.plans.slice(0, 2).map((p) => <PlanEditor key={p.id + p.status} plan={p} onDone={reload} />)}
                </div>
              )}
            </Section>
          </div>
        </div>

        <div>
          <h2 className="mb-2 text-lg font-bold">Training dashboard</h2>
          <p className="hint mb-2">This is what {data.name.split(" ")[0]} sees on their own training page.</p>
          {act.loading && !act.data ? <Spinner /> : act.data ? <TrainingDashboard a={act.data} /> : <ErrorBox message={act.error ?? ""} onRetry={act.reload} />}
        </div>
      </div>
    </CoachShell>
  );
}

function mergeSeries(data: CoachClientDetail, exercises: Exercise[], field: "form_score" | "relative_load") {
  const byDate = new Map<string, Record<string, number | string | null>>();
  for (const e of exercises) {
    for (const p of data.series[e]) {
      const key = p.date;
      const row = byDate.get(key) ?? { x: shortDate(p.date), t: key };
      row[e] = p[field];
      byDate.set(key, row);
    }
  }
  return [...byDate.values()].sort((a, b) => String(a.t).localeCompare(String(b.t)));
}

function StatusChip({ status }: { status: string }) {
  const map: Record<string, string> = { ready_for_review: "chip-amber", approved: "chip-good", needs_reshoot: "chip-red", failed: "chip-red", queued: "chip-info", processing: "chip-info" };
  return <span className={`chip ${map[status] ?? "chip-info"}`}>{status.replace(/_/g, " ")}</span>;
}

function ProfileEditor({ data, onSaved }: { data: CoachClientDetail; onSaved: () => void }) {
  const p = data.profile;
  const [editing, setEditing] = useState(false);
  const [notes, setNotes] = useState(data.coach_notes ?? "");
  const [inj, setInj] = useState(p.injuries_or_limits ?? "");
  const [goal, setGoal] = useState<Goal | "">(p.goal ?? "");
  const [exp, setExp] = useState<Experience | "">(p.experience_level ?? "");
  const [days, setDays] = useState(String(p.training_days_per_week ?? 3));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const patch: Record<string, unknown> = { coach_notes: notes, injuries_or_limits: inj || null };
      if (p.goal !== undefined || goal) patch.goal = goal || undefined;
      if (p.experience_level !== undefined || exp) patch.experience_level = exp || undefined;
      if (data.profile_complete) patch.training_days_per_week = Number(days);
      await api.patchClient(data.id, patch);
      setEditing(false);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  const rows: [string, React.ReactNode][] = data.profile_complete ? [
    ["Age", p.age], ["Sex", p.sex?.replace(/_/g, " ") ?? "–"], ["Height", `${p.height_cm} cm`], ["Weight", `${p.body_weight_kg} kg`],
    ["Experience", p.experience_level ? EXPERIENCE_LABEL[p.experience_level] : "–"], ["Goal", p.goal ? GOAL_LABEL[p.goal] : "–"],
    ["Days per week", p.training_days_per_week], ["Equipment", p.equipment?.join(", ") || "–"],
  ] : [];

  return (
    <Section title="Profile" right={<button className="text-sm font-semibold text-brand" onClick={() => setEditing(!editing)}>{editing ? "Cancel" : "Edit"}</button>}>
      {!data.profile_complete && <p className="mb-2 text-sm text-muted">The client has not filled in their profile yet.</p>}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        {rows.map(([k, v]) => (<div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="font-medium">{v}</dd></div>))}
      </dl>
      {data.derived.bmi && (
        <p className="mt-2 text-sm"><span className="text-muted">BMI</span> <strong>{data.derived.bmi.value}</strong><span className="hint block">{data.derived.bmi.note}</span></p>
      )}
      {data.derived.femur_torso_ratio && (
        <p className="mt-1 text-sm"><span className="text-muted">Femur ÷ torso (from pose)</span> <strong>{data.derived.femur_torso_ratio}</strong>
          <span className="hint block">A higher number means the torso leans more in a squat. This is normal and is accounted for.</span></p>
      )}
      <p className="mt-2 text-sm"><span className="text-muted">Injuries or limits: </span>{p.injuries_or_limits || "none listed"}</p>
      {!editing ? (
        <p className="mt-2 whitespace-pre-wrap rounded-lg bg-info-soft p-2 text-sm"><span className="font-semibold">Coach notes: </span>{data.coach_notes || "–"}</p>
      ) : (
        <div className="mt-3 space-y-2">
          {data.profile_complete && (<>
            <label className="label" htmlFor="g">Goal</label>
            <select id="g" className="field" value={goal} onChange={(e) => setGoal(e.target.value as Goal)}>{Object.entries(GOAL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
            <label className="label" htmlFor="e">Experience</label>
            <select id="e" className="field" value={exp} onChange={(e) => setExp(e.target.value as Experience)}>{Object.entries(EXPERIENCE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
            <label className="label" htmlFor="d">Training days per week</label>
            <select id="d" className="field" value={days} onChange={(e) => setDays(e.target.value)}>{[1, 2, 3, 4, 5, 6, 7].map((n) => <option key={n}>{n}</option>)}</select>
          </>)}
          <label className="label" htmlFor="i">Injuries or limits</label>
          <textarea id="i" className="field" rows={2} value={inj} onChange={(e) => setInj(e.target.value)} />
          <label className="label" htmlFor="n">Coach notes (the client never sees these)</label>
          <textarea id="n" className="field" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
          {err && <p role="alert" className="text-sm text-bad">{err}</p>}
          <button className="btn w-full" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        </div>
      )}
    </Section>
  );
}
