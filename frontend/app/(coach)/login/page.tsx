"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not log in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-4 px-4">
      <h1 className="text-2xl font-bold">Coach log in</h1>
      <form onSubmit={submit} className="card space-y-3">
        <div>
          <label htmlFor="pw" className="label">Password</label>
          <input id="pw" type="password" className="field" autoFocus required value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        <button className="btn w-full" disabled={busy}>{busy ? "Checking…" : "Log in"}</button>
      </form>
      <p className="hint">MVP: one coach account. The password is set by the COACH_PASSWORD environment variable.</p>
    </main>
  );
}
