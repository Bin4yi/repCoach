"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { EXERCISE_LABEL, longDate } from "@/lib/format";
import type { PlanDoc, WeekPlan } from "@/lib/types";

const DAYS = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Coach edits an AI-drafted plan and approves it. Load changes above the cap are clamped by the server. */
export default function PlanEditor({ plan, onDone }: { plan: PlanDoc; onDone: () => void }) {
  const [draft, setDraft] = useState<WeekPlan>(structuredClone(plan.approved ?? plan.draft));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const approved = plan.status === "approved";

  const upd = (i: number, patch: Partial<WeekPlan["sessions"][number]>) =>
    setDraft((d) => ({ ...d, sessions: d.sessions.map((s, k) => (k === i ? { ...s, ...patch } : s)) }));

  async function approve() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.approvePlan(plan.id, draft);
      setMsg(r.notes.length ? "Approved. Adjusted by safety rules: " + r.notes.join(" ") : "Approved. The client can see this plan now.");
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not approve.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className={`chip ${approved ? "chip-good" : "chip-amber"}`}>{approved ? "Approved" : "Draft: needs your review"}</span>
        <span className="hint">Week of {longDate(plan.week_start)} · written by {plan.source === "gemma" ? "the AI model" : "a template"}</span>
        {plan.conservative_mode && <span className="chip chip-red">Careful mode: no load increases</span>}
      </div>
      {plan.warnings.length > 0 && <ul className="list-disc pl-5 text-xs text-muted">{plan.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}

      <div>
        <label className="label" htmlFor={`focus-${plan.id}`}>Focus</label>
        <input id={`focus-${plan.id}`} className="field" value={draft.focus} onChange={(e) => setDraft({ ...draft, focus: e.target.value })} />
      </div>

      <div className="space-y-2">
        {draft.sessions.map((s, i) => (
          <div key={i} className="tile p-3">
            <div className="mb-2 flex items-center justify-between font-semibold">
              <span>{DAYS[s.day]} · {EXERCISE_LABEL[s.exercise] ?? s.exercise}</span>
              <span className="hint">{s.load_suggestion}</span>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <label className="text-xs font-semibold">Sets
                <input className="field mt-1" type="number" min={1} max={10} value={s.sets} onChange={(e) => upd(i, { sets: Number(e.target.value) })} />
              </label>
              <label className="text-xs font-semibold">Reps
                <input className="field mt-1" value={s.reps} onChange={(e) => upd(i, { reps: e.target.value })} />
              </label>
              <label className="text-xs font-semibold">Load change %
                <input className="field mt-1" type="number" step="0.5" max={plan.max_load_increase_pct} value={s.load_change_pct} onChange={(e) => upd(i, { load_change_pct: Number(e.target.value) })} />
              </label>
              <label className="text-xs font-semibold">Tempo
                <input className="field mt-1" value={s.tempo} onChange={(e) => upd(i, { tempo: e.target.value })} />
              </label>
            </div>
            <label className="mt-2 block text-xs font-semibold">Cue
              <input className="field mt-1" value={s.cue} onChange={(e) => upd(i, { cue: e.target.value })} />
            </label>
          </div>
        ))}
      </div>
      <p className="hint">Max load increase this week: {plan.max_load_increase_pct}%. Higher values are reduced when you approve.</p>

      <div>
        <label className="label" htmlFor={`rule-${plan.id}`}>Progression rule</label>
        <input id={`rule-${plan.id}`} className="field" value={draft.progression_rule} onChange={(e) => setDraft({ ...draft, progression_rule: e.target.value })} />
      </div>

      <div className="rounded-xl bg-warn-soft p-3 text-sm">
        <div className="font-semibold">Check before approving</div>
        <ul className="list-disc pl-5">{draft.coach_review_points.map((p, i) => <li key={i}>{p}</li>)}</ul>
      </div>

      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      {msg && <p className="text-sm text-good">{msg}</p>}
      <button className="btn w-full sm:w-auto" onClick={approve} disabled={busy}>{busy ? "Saving…" : approved ? "Save changes and re-approve" : "Approve plan"}</button>
    </div>
  );
}
