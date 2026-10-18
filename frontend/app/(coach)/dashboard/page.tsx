"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { CoachShell } from "@/components/CoachShell";
import { ErrorBox, Spinner, useLoad, WarningChips } from "@/components/ui";
import { api } from "@/lib/api";
import { daysAgo, EXPERIENCE_LABEL, GOAL_LABEL, scoreColor, TREND_ICON } from "@/lib/format";

export default function DashboardPage() {
  const router = useRouter();
  const { data, error, loading, reload } = useLoad(api.clients, [], () => router.replace("/login"));
  const [name, setName] = useState("");
  const [created, setCreated] = useState<{ name: string; link: string } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    try {
      const r = await api.createClient(name.trim());
      setCreated({ name, link: r.link });
      setName("");
      reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not add client.");
    }
  }

  return (
    <CoachShell>
      <h1 className="mb-4 text-2xl font-bold">Your clients</h1>

      <form onSubmit={add} className="card mb-4 flex flex-wrap items-end gap-2">
        <div className="min-w-[12rem] flex-1">
          <label htmlFor="newname" className="label">Add a client</label>
          <input id="newname" className="field" placeholder="Client name" required value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <button className="btn">Create private link</button>
        {formError && <p role="alert" className="w-full text-sm text-bad">{formError}</p>}
      </form>
      {created && (
        <div className="card mb-4 border-brand/40 bg-brand-soft text-sm">
          <p className="font-semibold">Link for {created.name}. Send it to them privately:</p>
          <code className="mt-1 block break-all">{created.link}</code>
          <button className="btn btn-ghost mt-2" onClick={() => navigator.clipboard?.writeText(created.link)}>Copy link</button>
        </div>
      )}

      {loading && !data ? (
        <Spinner />
      ) : error || !data ? (
        <ErrorBox message={error ?? "No data"} onRetry={reload} />
      ) : data.length === 0 ? (
        <div className="card text-muted">No clients yet. Add your first client above, or run the demo seed script.</div>
      ) : (
        <ul className="space-y-2">
          {data.map((c) => (
            <li key={c.id}>
              <Link href={`/clients/${c.id}`} className="card block transition hover:border-brand">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate font-semibold">{c.name}</div>
                    <div className="hint">
                      {c.goal ? GOAL_LABEL[c.goal] : "Profile not filled in"}
                      {c.experience_level ? ` · ${EXPERIENCE_LABEL[c.experience_level]}` : ""} · last upload {daysAgo(c.last_session_at)}
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className={`text-2xl font-bold tabular-nums ${scoreColor(c.latest_form_score)}`}>
                      {c.latest_form_score ?? "–"}
                      <span className="ml-1 text-lg text-muted" title={`Trend: ${c.trend.replace(/_/g, " ")}`}>{TREND_ICON[c.trend]}</span>
                    </div>
                    <div className="hint">form score</div>
                  </div>
                </div>
                <div className="mt-2"><WarningChips warnings={c.warnings} /></div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </CoachShell>
  );
}
