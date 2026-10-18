import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-6 px-4 py-10">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">RepCheck</h1>
        <p className="mt-2 text-muted">
          Film a set. We measure your reps. Your coach reviews the feedback before you see it.
        </p>
      </div>
      <div className="card space-y-3">
        <h2 className="font-semibold">I am a coach</h2>
        <p className="hint">Review videos, edit the AI draft, and send feedback to your clients.</p>
        <Link href="/login" className="btn">
          Coach log in
        </Link>
      </div>
      <div className="card space-y-1">
        <h2 className="font-semibold">I am a client</h2>
        <p className="hint">
          Open the private link your coach sent you. It looks like <code>/c/your-private-code</code>.
        </p>
      </div>
      <p className="hint">
        RepCheck is a coaching helper, not a medical tool. It never diagnoses injuries and never gives diet advice.
      </p>
    </main>
  );
}
