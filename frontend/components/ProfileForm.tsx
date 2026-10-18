"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { EXPERIENCE_LABEL, GOAL_LABEL } from "@/lib/format";
import type { Equipment, Experience, Goal, Profile } from "@/lib/types";

const EQUIPMENT: Equipment[] = ["bodyweight", "dumbbells", "barbell", "machines", "bands"];

export function ConsentCard({ accepted, onChange }: { accepted: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="card border-brand/40 bg-brand-soft">
      <h2 className="font-semibold">Before you start: your privacy</h2>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
        <li>Your video is checked by software, then it is deleted.</li>
        <li>We keep only numbers (like angles and reps) and text.</li>
        <li>Your coach sees your numbers and a short skeleton video, only until they review it.</li>
        <li>An AI model writes a draft. Your coach reads and edits it before you see it.</li>
        <li>RepCheck is not a medical tool. If something hurts, stop and talk to your coach or a doctor.</li>
      </ul>
      <label className="mt-3 flex items-start gap-2 text-sm font-medium">
        <input type="checkbox" className="mt-1 h-5 w-5" checked={accepted} onChange={(e) => onChange(e.target.checked)} />
        <span>I understand and I agree.</span>
      </label>
    </div>
  );
}

type FormState = {
  name: string;
  age: string;
  sex: string;
  height_cm: string;
  body_weight_kg: string;
  experience_level: Experience;
  goal: Goal;
  training_days_per_week: string;
  injuries_or_limits: string;
  equipment: Equipment[];
};

function initial(p?: Profile): FormState {
  return {
    name: p?.name ?? "",
    age: p?.age?.toString() ?? "",
    sex: p?.sex ?? "",
    height_cm: p?.height_cm?.toString() ?? "",
    body_weight_kg: p?.body_weight_kg?.toString() ?? "",
    experience_level: p?.experience_level ?? "beginner",
    goal: p?.goal ?? "general_fitness",
    training_days_per_week: p?.training_days_per_week?.toString() ?? "3",
    injuries_or_limits: p?.injuries_or_limits ?? "",
    equipment: p?.equipment ?? [],
  };
}

export default function ProfileForm({
  token,
  profile,
  alreadyConsented,
  onSaved,
}: {
  token: string;
  profile?: Profile;
  alreadyConsented: boolean;
  onSaved: () => void;
}) {
  const [f, setF] = useState<FormState>(() => initial(profile));
  const [consent, setConsent] = useState(alreadyConsented);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((s) => ({ ...s, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!consent) return setError("Please tick the privacy box to continue.");
    setBusy(true);
    try {
      await api.putProfile(token, {
        name: f.name.trim(),
        age: Number(f.age),
        sex: f.sex || null,
        height_cm: Number(f.height_cm),
        body_weight_kg: Number(f.body_weight_kg),
        experience_level: f.experience_level,
        goal: f.goal,
        training_days_per_week: Number(f.training_days_per_week),
        injuries_or_limits: f.injuries_or_limits.trim() || null,
        equipment: f.equipment,
        timezone: profile?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? "Asia/Colombo",
        consent,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {!alreadyConsented && <ConsentCard accepted={consent} onChange={setConsent} />}
      <div className="card space-y-3">
        <h2 className="font-semibold">About you</h2>
        <div>
          <label className="label" htmlFor="name">Name</label>
          <input id="name" className="field" required value={f.name} onChange={(e) => set("name", e.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="age">Age</label>
            <input id="age" className="field" type="number" inputMode="numeric" min={16} max={90} required value={f.age} onChange={(e) => set("age", e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="sex">Sex (optional)</label>
            <select id="sex" className="field" value={f.sex} onChange={(e) => set("sex", e.target.value)}>
              <option value="">–</option>
              <option value="female">Female</option>
              <option value="male">Male</option>
              <option value="prefer_not_to_say">Prefer not to say</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="height">Height (cm)</label>
            <input id="height" className="field" type="number" inputMode="decimal" min={100} max={250} step="0.1" required value={f.height_cm} onChange={(e) => set("height_cm", e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="weight">Weight (kg)</label>
            <input id="weight" className="field" type="number" inputMode="decimal" min={30} max={300} step="0.1" required value={f.body_weight_kg} onChange={(e) => set("body_weight_kg", e.target.value)} />
          </div>
        </div>
      </div>

      <div className="card space-y-3">
        <h2 className="font-semibold">Your training</h2>
        <div>
          <label className="label" htmlFor="exp">Experience</label>
          <select id="exp" className="field" value={f.experience_level} onChange={(e) => set("experience_level", e.target.value as Experience)}>
            {Object.entries(EXPERIENCE_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="goal">Main goal</label>
          <select id="goal" className="field" value={f.goal} onChange={(e) => set("goal", e.target.value as Goal)}>
            {Object.entries(GOAL_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="days">Training days per week</label>
          <select id="days" className="field" value={f.training_days_per_week} onChange={(e) => set("training_days_per_week", e.target.value)}>
            {[1, 2, 3, 4, 5, 6, 7].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
        <fieldset>
          <legend className="label">Equipment you have</legend>
          <div className="flex flex-wrap gap-2">
            {EQUIPMENT.map((eq) => {
              const on = f.equipment.includes(eq);
              return (
                <label key={eq} className={`chip cursor-pointer border px-3 py-2 text-sm ${on ? "chip-good border-brand" : "border-line"}`}>
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={on}
                    onChange={() => set("equipment", on ? f.equipment.filter((x) => x !== eq) : [...f.equipment, eq])}
                  />
                  {eq}
                </label>
              );
            })}
          </div>
        </fieldset>
        <div>
          <label className="label" htmlFor="inj">Injuries or limits (optional)</label>
          <textarea id="inj" className="field" rows={3} maxLength={500} placeholder="For example: left knee pain, lower back" value={f.injuries_or_limits} onChange={(e) => set("injuries_or_limits", e.target.value)} />
          <p className="hint mt-1">Your coach will see this. It helps keep your plan careful.</p>
        </div>
      </div>

      {error && <div role="alert" className="card border-bad/40 bg-bad-soft text-bad">{error}</div>}
      <button className="btn w-full" disabled={busy}>{busy ? "Saving…" : alreadyConsented ? "Save changes" : "Save and continue"}</button>
    </form>
  );
}
