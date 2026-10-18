"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { RepBars } from "@/components/Charts";
import { CoachShell } from "@/components/CoachShell";
import { ErrorBox, FlagChip, Section, Spinner, useLoad } from "@/components/ui";
import { API_BASE, api } from "@/lib/api";
import { EXERCISE_LABEL, FLAG_LABEL, longDate, scoreColor } from "@/lib/format";
import type { SessionDetail } from "@/lib/types";

const MAX_WORDS = 120;
const words = (s: string) => s.trim().split(/\s+/).filter(Boolean).length;

export default function SessionReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: s, error, loading, reload } = useLoad(() => api.session(id), [id], () => router.replace("/login"));
  const me = useLoad(() => api.me(), [], () => router.replace("/login"));

  if (loading && !s) return <CoachShell><Spinner /></CoachShell>;
  if (error || !s) return <CoachShell><ErrorBox message={error ?? "Not found"} onRetry={reload} /></CoachShell>;

  return (
    <CoachShell wide>
      <div className="mb-3">
        <Link href={`/clients/${s.client.id}`} className="text-sm text-muted">← {s.client.name}</Link>
        <h1 className="mt-1 text-2xl font-bold">{EXERCISE_LABEL[s.exercise]} · {longDate(s.created_at)}</h1>
        <p className="hint">Status: {s.status.replace(/_/g, " ")} · camera: {s.inputs.camera_view} · load {s.inputs.load_kg ? `${s.inputs.load_kg} kg` : "body weight"}</p>
      </div>

      {s.status === "needs_reshoot" && <div role="alert" className="card mb-4 border-warn/40 bg-warn-soft"><b>Needs a re-shoot.</b> {s.quality?.reason}<p className="hint mt-1">The client has been shown this message.</p></div>}
      {s.status === "failed" && <ErrorBox message={s.error ?? "Processing failed on the server."} />}
      {(s.status === "queued" || s.status === "processing") && <div className="card mb-4">Still processing… <button className="btn btn-ghost ml-2" onClick={reload}>Refresh</button></div>}

      {s.judgement && s.set && s.reps && <Review s={s} voiceEnabled={!!me.data?.voice_enabled} onChanged={reload} />}
    </CoachShell>
  );
}

function Review({ s, voiceEnabled, onChanged }: { s: SessionDetail; voiceEnabled: boolean; onChanged: () => void }) {
  const j = s.judgement!;
  const fb = s.ai_feedback;
  const reps = s.reps!;
  const set = s.set!;
  const approved = s.status === "approved";
  const [msg, setMsg] = useState(s.approved?.client_message ?? fb?.draft.client_message ?? "");
  const [progress, setProgress] = useState(s.approved?.progress_message ?? fb?.progress_draft.client_message ?? "");
  const [note, setNote] = useState(s.approved?.coach_note ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [audio, setAudio] = useState<string | null>(null);
  const [voiceBusy, setVoiceBusy] = useState(false);
  useEffect(() => () => { if (audio) URL.revokeObjectURL(audio); }, [audio]);

  const n = words(msg);
  const pain = j.safety.pain_reported;

  async function approve() {
    if (pain && !(/stop/i.test(msg) && /coach/i.test(msg)) &&
        !confirm("Pain was reported, but your message does not tell the client to stop and talk to you. Approve anyway?")) return;
    setBusy(true);
    setErr(null);
    try {
      await api.approveSession(s.id, msg, progress.trim() || null, note.trim() || null);
      setDone(true);
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not approve.");
    } finally {
      setBusy(false);
    }
  }

  async function voice() {
    setVoiceBusy(true);
    setErr(null);
    try {
      const blob = await api.voiceNote(s.id, msg);
      setAudio(URL.createObjectURL(blob));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Voice note failed.");
    } finally {
      setVoiceBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {pain && (
        <div role="alert" className="card border-bad bg-bad-soft text-bad">
          <p className="text-lg font-bold">⚠ The client reported pain during this set</p>
          {s.inputs.pain_text && <p>“{s.inputs.pain_text}”</p>}
          <p className="text-sm">No load increase is suggested. The client message tells them to stop and talk to you. Please follow up.</p>
        </div>
      )}
      {!pain && j.safety.conservative_mode && (
        <div className="card border-warn/40 bg-warn-soft text-sm">
          <b>Careful mode.</b> The AI was told not to suggest load increases.
          <ul className="list-disc pl-5">{j.safety.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <Section title="Skeleton overlay">
            {s.overlay_available ? (
              <>
                <video controls playsInline className="w-full rounded-lg bg-black" src={api.overlayUrl(s.id)} crossOrigin={API_BASE.startsWith("http") ? "use-credentials" : undefined} />
                <p className="hint mt-1">Red = reps with a flag. This video is deleted when you approve (or after 7 days).</p>
              </>
            ) : <p className="text-sm text-muted">No overlay video available (deleted after review, or it could not be made).</p>}
          </Section>

          <Section title="Judgement (computed by code)">
            <div className="flex items-end gap-4">
              <div className={`text-5xl font-bold tabular-nums ${scoreColor(j.form_score)}`}>{j.form_score ?? "–"}</div>
              <div className="pb-1 text-sm text-muted">form score / 100<br />{set.rep_count} reps · avg depth {set.depth_mean != null ? `${set.depth_mean}°` : "n/a"}</div>
            </div>
            {j.flags.length === 0 ? <p className="mt-2 text-sm text-good">No form flags.</p> : (
              <ul className="mt-3 space-y-2">
                {j.flags.map((f) => (
                  <li key={f.code} className="rounded-lg border border-line p-2 text-sm">
                    <div className="flex flex-wrap items-center gap-2"><FlagChip code={f.code} severity={f.severity} /><span className="hint">{f.severity} · reps {f.reps.join(", ")}</span></div>
                    <div className="mt-1 text-muted">{f.evidence}</div>
                  </li>
                ))}
              </ul>
            )}
            <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
              <dt className="text-muted">Relative load</dt><dd className="font-medium">{j.relative_load ?? "–"} × body weight</dd>
              <dt className="text-muted">RPE</dt><dd className="font-medium">{j.fatigue.rpe ?? "–"}</dd>
              <dt className="text-muted">Speed loss</dt><dd className="font-medium">{j.fatigue.velocity_loss_pct != null ? `${j.fatigue.velocity_loss_pct}%` : "n/a (needs 4+ reps)"}</dd>
              <dt className="text-muted">Close to failure</dt><dd className="font-medium">{j.fatigue.close_to_failure ? "Yes" : "No"}</dd>
              <dt className="text-muted">Tempo consistency (CV)</dt><dd className="font-medium">{set.tempo_cv ?? "–"}</dd>
              <dt className="text-muted">Max load change</dt><dd className="font-medium">{j.max_load_increase_pct}% / week</dd>
              {set.balance && (<><dt className="text-muted">Left / right</dt><dd className="font-medium">{set.balance.left_mean_min_deg}° / {set.balance.right_mean_min_deg}° ({set.balance.diff_pct}% apart)</dd></>)}
            </dl>
            {j.progress_vs_last_3 && (
              <p className="mt-3 rounded-lg bg-info-soft p-2 text-sm">
                vs last {j.progress_vs_last_3.sessions_compared} session(s): form {fmt(j.progress_vs_last_3.form_score_change)}, depth {fmt(j.progress_vs_last_3.depth_change_deg, "°")}, relative load {fmt(j.progress_vs_last_3.relative_load_change)}
              </p>
            )}
            {(!j.data_quality.ok || j.data_quality.notes.length > 0) && (
              <p className="mt-2 text-sm text-warn">Data quality: {j.data_quality.notes.join(" ") || "Some measurements are uncertain."}</p>
            )}
            {s.inputs.client_comment && <p className="mt-2 text-sm"><span className="text-muted">Client said:</span> “{s.inputs.client_comment}”</p>}
          </Section>
        </div>

        <div className="space-y-4">
          <Section title="AI draft for the client" right={fb && <span className="chip chip-info">{fb.source === "gemma" ? aiLabel(fb.model) : fb.source.startsWith("demo") ? "Demo template" : "Template (AI unavailable or rejected)"}</span>}>
            {fb?.warnings && fb.warnings.length > 0 && <ul className="mb-2 list-disc pl-5 text-xs text-muted">{fb.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
            {fb && (
              <div className="mb-3 space-y-2 text-sm">
                <p><b>For you:</b> {fb.draft.summary}</p>
                {fb.draft.what_went_well.length > 0 && <div><b>Went well:</b><ul className="list-disc pl-5">{fb.draft.what_went_well.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
                {fb.draft.fix_next_time.length > 0 && <div><b>Fix next time:</b><ul className="list-disc pl-5">{fb.draft.fix_next_time.map((c, i) => <li key={i}>{c.cue} <span className="text-muted">({c.why}{c.reps.length ? ` Reps ${c.reps.join(", ")}.` : ""})</span></li>)}</ul></div>}
                {fb.draft.coach_only_notes.length > 0 && <div className="rounded-lg bg-warn-soft p-2"><b>Coach-only notes:</b><ul className="list-disc pl-5">{fb.draft.coach_only_notes.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
              </div>
            )}
            <label className="label" htmlFor="msg">Message to the client (edit freely)</label>
            <textarea id="msg" className="field" rows={7} value={msg} onChange={(e) => setMsg(e.target.value)} />
            <p className={`hint mt-1 ${n > MAX_WORDS ? "text-bad" : ""}`}>{n} words (aim for {MAX_WORDS} or fewer)</p>

            <label className="label mt-3" htmlFor="prog">Progress note (optional)</label>
            <textarea id="prog" className="field" rows={3} value={progress} onChange={(e) => setProgress(e.target.value)} />
            <label className="label mt-3" htmlFor="note">Your private note (optional)</label>
            <textarea id="note" className="field" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />

            {err && <p role="alert" className="mt-2 text-sm text-bad">{err}</p>}
            {done && <p className="mt-2 text-sm text-good">Approved. The client can see this message now.</p>}
            <div className="mt-3 flex flex-wrap gap-2">
              <button className="btn" onClick={approve} disabled={busy || !msg.trim()}>{busy ? "Saving…" : approved ? "Save changes" : "Approve and send to client"}</button>
              {voiceEnabled && <button className="btn btn-ghost" onClick={voice} disabled={voiceBusy || !msg.trim()}>{voiceBusy ? "Making audio…" : "🔊 Voice note"}</button>}
            </div>
            {audio && <audio className="mt-3 w-full" controls src={audio} />}
            <p className="hint mt-2">Nothing is shown to the client until you approve. The AI only drafts.</p>
          </Section>
        </div>
      </div>

      <Section title="Per-rep data">
        <div className="grid gap-4 md:grid-cols-3">
          {s.exercise !== "squat" || reps[0]?.depth_angle != null ? <RepBars reps={reps} field="depth_angle" label="Depth angle (°, lower = deeper)" unit="°" /> : null}
          <RepBars reps={reps} field="eccentric_s" label="Lowering time (s)" unit="s" />
          <RepBars reps={reps} field="concentric_s" label="Lifting time (s)" unit="s" />
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[32rem] text-left text-sm">
            <thead className="text-xs text-muted"><tr><th className="py-1">Rep</th><th>Depth °</th><th>Range °</th><th>Down s</th><th>Up s</th><th>Pause s</th><th>Flags</th></tr></thead>
            <tbody>
              {reps.map((r) => (
                <tr key={r.rep} className={`border-t border-line ${r.flags.length ? "bg-bad-soft" : ""}`}>
                  <td className="py-1.5 font-semibold">{r.rep}</td><td>{r.depth_angle ?? "–"}</td><td>{r.range_of_motion}</td>
                  <td>{r.eccentric_s}</td><td>{r.concentric_s}</td><td>{r.bottom_pause_s}</td>
                  <td className="space-x-1">{r.flags.map((f) => <span key={f} className="chip chip-red">{FLAG_LABEL[f] ?? f}</span>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}

/** Name the model that actually wrote the draft (Gemma in production; a stand-in may be used for demos). */
function aiLabel(model: string | null): string {
  if (!model) return "AI draft";
  return model.toLowerCase().startsWith("gemma") ? `Gemma · ${model}` : `AI draft · ${model}`;
}

function fmt(v: number | null, unit = ""): string {
  if (v == null) return "n/a";
  return `${v > 0 ? "+" : ""}${v}${unit}`;
}
