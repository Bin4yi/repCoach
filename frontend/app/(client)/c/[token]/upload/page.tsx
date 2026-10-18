"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import CameraTips from "@/components/CameraTips";
import { ClientNav } from "@/components/ClientNav";
import { ErrorBox, Spinner, useLoad } from "@/components/ui";
import { api, uploadVideo } from "@/lib/api";
import { EXERCISE_LABEL } from "@/lib/format";
import type { Exercise } from "@/lib/types";

const MAX_MB = 100;
const EXERCISES: { key: Exercise; emoji: string; hint: string }[] = [
  { key: "squat", emoji: "🏋️", hint: "Legs and hips" },
  { key: "pushup", emoji: "💪", hint: "Chest and arms" },
  { key: "bicep_curl", emoji: "🦾", hint: "Arms" },
];

type Phase = "form" | "uploading" | "analysing" | "done" | "reshoot";

export default function UploadPage() {
  const { token } = useParams<{ token: string }>();
  const home = useLoad(() => api.home(token), [token]);
  const [exercise, setExercise] = useState<Exercise>("squat");
  const [view, setView] = useState<"side" | "front">("side");
  const [load, setLoad] = useState("0");
  const [target, setTarget] = useState("");
  const [sets, setSets] = useState("");
  const [rpe, setRpe] = useState("");
  const [pain, setPain] = useState(false);
  const [painText, setPainText] = useState("");
  const [bw, setBw] = useState("");
  const [comment, setComment] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [pct, setPct] = useState(0);
  const [phase, setPhase] = useState<Phase>("form");
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  function pick(f: File | null) {
    setError(null);
    if (f && f.size > MAX_MB * 1024 * 1024) {
      setError(`That video is too big. The limit is ${MAX_MB} MB.`);
      return setFile(null);
    }
    if (f && !/\.(mp4|mov|webm)$/i.test(f.name)) {
      setError("Please choose an mp4, mov or webm video.");
      return setFile(null);
    }
    setFile(f);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return setError("Please choose a video first.");
    setError(null);
    const fd = new FormData();
    fd.set("file", file);
    fd.set("exercise", exercise);
    fd.set("camera_view", view);
    fd.set("load_kg", load || "0");
    if (target) fd.set("target_reps", target);
    if (sets) fd.set("sets_done_today", sets);
    if (rpe) fd.set("rpe", rpe);
    fd.set("pain_during_set", String(pain));
    if (pain && painText) fd.set("pain_text", painText);
    if (bw) fd.set("body_weight_today_kg", bw);
    if (comment) fd.set("client_comment", comment);
    setPhase("uploading");
    setPct(0);
    try {
      await uploadVideo(token, fd, setPct);
      setPhase("analysing");
    } catch (err) {
      setPhase("form");
      setError(err instanceof Error ? err.message : "The upload failed.");
    }
  }

  // After upload: poll for a few seconds so a "please film again" message shows right away.
  useEffect(() => {
    if (phase !== "analysing") return;
    let tries = 0;
    const id = setInterval(async () => {
      tries++;
      try {
        const h = await api.home(token);
        if (h.processing_count === 0) {
          if (h.reshoot_reason) {
            setReason(h.reshoot_reason);
            setPhase("reshoot");
          } else {
            setPhase("done");
          }
          clearInterval(id);
        }
      } catch {
        /* keep trying */
      }
      if (tries > 40) {
        setPhase("done");
        clearInterval(id);
      }
    }, 3000);
    return () => clearInterval(id);
  }, [phase, token]);

  if (home.loading && !home.data) return <Spinner />;
  if (home.error || !home.data) return <main className="mx-auto max-w-xl px-4 py-10"><ErrorBox message={home.error ?? "Not found"} onRetry={home.reload} /></main>;

  if (!home.data.profile_complete) {
    return (
      <main className="mx-auto max-w-xl space-y-4 px-4 py-6">
        <ClientNav token={token} current="upload" />
        <div className="card">Please fill in your profile and read the privacy note first.</div>
        <Link href={`/c/${token}`} className="btn w-full">Go to my profile</Link>
      </main>
    );
  }

  if (phase === "analysing" || phase === "done" || phase === "reshoot") {
    return (
      <main className="mx-auto max-w-xl space-y-4 px-4 py-6">
        <ClientNav token={token} current="upload" />
        <div className="card space-y-2 text-center">
          {phase === "analysing" && (<><div className="text-4xl">⏳</div><h1 className="text-xl font-bold">Checking your set…</h1><p className="text-muted">This can take a minute. You can leave this page.</p></>)}
          {phase === "done" && (<><div className="text-4xl">✅</div><h1 className="text-xl font-bold">Got it!</h1><p className="text-muted">Your coach will review it and send you feedback. Your video has been deleted; only numbers are kept.</p></>)}
          {phase === "reshoot" && (<><div className="text-4xl">🎥</div><h1 className="text-xl font-bold">Please film it again</h1><p>{reason}</p></>)}
        </div>
        <button className="btn w-full" onClick={() => { setPhase("form"); setFile(null); setReason(null); }}>Upload another set</button>
        <Link href={`/c/${token}`} className="btn btn-ghost w-full">Back home</Link>
      </main>
    );
  }

  const uploading = phase === "uploading";
  return (
    <main className="mx-auto max-w-xl space-y-4 px-4 py-6">
      <ClientNav token={token} current="upload" />
      <h1 className="text-3xl font-extrabold tracking-tight">Upload a <span className="text-gradient">set</span></h1>
      <form onSubmit={submit} className="space-y-4">
        <fieldset className="card">
          <legend className="label float-left mb-2 w-full">1. Which exercise?</legend>
          <div className="clear-both grid grid-cols-3 gap-2">
            {EXERCISES.map((x) => (
              <label key={x.key} className={`tile cursor-pointer p-3 text-center ${exercise === x.key ? "tile-on" : ""}`}>
                <input type="radio" className="sr-only" name="exercise" checked={exercise === x.key} onChange={() => setExercise(x.key)} />
                <div className="text-2xl" aria-hidden>{x.emoji}</div>
                <div className="text-sm font-semibold">{EXERCISE_LABEL[x.key]}</div>
                <div className="hint">{x.hint}</div>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="card">
          <legend className="label float-left mb-2 w-full">2. Camera view</legend>
          <div className="clear-both grid grid-cols-2 gap-2">
            {(["side", "front"] as const).map((v) => (
              <label key={v} className={`tile cursor-pointer p-3 text-center text-sm font-semibold ${view === v ? "tile-on" : ""}`}>
                <input type="radio" className="sr-only" name="view" checked={view === v} onChange={() => setView(v)} />
                {v === "side" ? "Side view (best)" : "Front view"}
              </label>
            ))}
          </div>
        </fieldset>
        <CameraTips view={view} exercise={exercise} />

        <div className="card space-y-3">
          <h2 className="label !mb-0">3. Your video</h2>
          <input ref={fileInput} type="file" accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm" className="sr-only" id="video" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
          <label htmlFor="video" className="btn btn-ghost w-full cursor-pointer">{file ? `📎 ${file.name}` : "Choose or record a video"}</label>
          <p className="hint">mp4, mov or webm · up to 60 seconds · up to {MAX_MB} MB. Your video is deleted after checking.</p>
        </div>

        <div className="card space-y-3">
          <h2 className="label !mb-0">4. About this set</h2>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="load">Weight used (kg)</label>
              <input id="load" className="field" type="number" inputMode="decimal" min={0} step="0.5" value={load} onChange={(e) => setLoad(e.target.value)} />
              <p className="hint mt-1">0 = body weight</p>
            </div>
            <div>
              <label className="label" htmlFor="rpe">How hard was it? (1–10)</label>
              <select id="rpe" className="field" value={rpe} onChange={(e) => setRpe(e.target.value)}>
                <option value="">–</option>
                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => <option key={n} value={n}>{n}{n === 10 ? " (max)" : n === 1 ? " (very easy)" : ""}</option>)}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="target">Reps planned</label>
              <input id="target" className="field" type="number" inputMode="numeric" min={1} value={target} onChange={(e) => setTarget(e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="sets">Sets done today</label>
              <input id="sets" className="field" type="number" inputMode="numeric" min={1} value={sets} onChange={(e) => setSets(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="label" htmlFor="bw">Body weight today (kg, optional)</label>
            <input id="bw" className="field" type="number" inputMode="decimal" min={30} step="0.1" value={bw} onChange={(e) => setBw(e.target.value)} />
          </div>
          <label className={`tile flex items-start gap-2 p-3 ${pain ? "!border-bad !bg-bad-soft" : ""}`}>
            <input type="checkbox" className="mt-1 h-5 w-5" checked={pain} onChange={(e) => setPain(e.target.checked)} />
            <span className="text-sm font-medium">I felt pain during this set</span>
          </label>
          {pain && (
            <div>
              <label className="label" htmlFor="pain">Where and what did it feel like?</label>
              <input id="pain" className="field" maxLength={300} value={painText} onChange={(e) => setPainText(e.target.value)} />
              <p className="hint mt-1 text-bad">Please stop this exercise and talk to your coach. Your coach will be told.</p>
            </div>
          )}
          <div>
            <label className="label" htmlFor="comment">Anything else? (optional)</label>
            <textarea id="comment" className="field" rows={2} maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
        </div>

        {error && <div role="alert" className="card border-bad/40 bg-bad-soft text-bad">{error}</div>}
        {uploading && (
          <div className="card" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div className="mb-1 text-sm font-semibold">Uploading… {pct}%</div>
            <div className="h-2.5 overflow-hidden rounded-full bg-line"><div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: "var(--ink)" }} /></div>
          </div>
        )}
        <button className="btn w-full" disabled={uploading || !file}>{uploading ? "Uploading…" : "Send to my coach"}</button>
      </form>
    </main>
  );
}
