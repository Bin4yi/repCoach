import Link from "next/link";
import { Logo } from "@/components/Logo";

const STEPS = [
  { icon: "📐", title: "MediaPipe measures", text: "Body points in every frame become reps, angles, depth and tempo." },
  { icon: "⚖️", title: "Code judges", text: "Fixed rules use your profile, effort and history. Safety first." },
  { icon: "💬", title: "Gemma explains", text: "An open model turns the numbers into a draft. It never sees the video." },
  { icon: "✅", title: "Your coach decides", text: "Nothing reaches you until your coach edits and approves it." },
];

export default function Home() {
  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:py-14">
      <Logo size={36} />

      <section className="mt-10 grid items-center gap-8 md:grid-cols-[1.1fr_1fr]">
        <div>
          <span className="chip chip-info">Open-weight AI · coach in control</span>
          <h1 className="mt-4 text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
            Every rep measured.
            <br />
            <span className="text-gradient">Every message approved.</span>
          </h1>
          <p className="mt-4 max-w-lg text-lg text-muted">
            Film a set on your phone. RepCheck measures your form and drafts feedback. Your coach reviews it before you see it.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link href="/login" className="btn !px-6">
              Coach log in →
            </Link>
            <a href="#client" className="btn btn-ghost !px-6">
              I&apos;m a client
            </a>
          </div>
        </div>

        <div className="card relative overflow-hidden !p-5">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-muted">Squat · 8 reps</span>
            <span className="chip chip-good">Approved</span>
          </div>
          <div className="mt-3 flex items-end gap-3">
            <span className="text-gradient text-6xl font-extrabold tabular-nums">86</span>
            <span className="pb-2 text-sm text-muted">form score</span>
          </div>
          <div className="mt-4 flex h-20 items-end gap-1.5" aria-hidden>
            {[78, 82, 80, 84, 70, 66, 74, 72].map((h, i) => (
              <span
                key={i}
                className="flex-1 rounded-t-md"
                style={{
                  height: `${h}%`,
                  background: i === 4 || i === 5 ? "var(--bad)" : "linear-gradient(180deg, var(--brand-2), var(--brand))",
                  opacity: 0.85,
                }}
              />
            ))}
          </div>
          <p className="mt-4 rounded-xl bg-brand-soft p-3 text-sm">
            “Great control on the way down. Sit a little deeper on reps 5 and 6. Keep your chest tall.”
          </p>
        </div>
      </section>

      <section className="mt-14 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((s) => (
          <div key={s.title} className="card">
            <div className="text-2xl" aria-hidden>
              {s.icon}
            </div>
            <h2 className="mt-2 font-semibold">{s.title}</h2>
            <p className="mt-1 text-sm text-muted">{s.text}</p>
          </div>
        ))}
      </section>

      <section id="client" className="card mt-6 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-semibold">I am a client</h2>
          <p className="hint">
            Open the private link your coach sent you. It looks like <code className="rounded bg-brand-soft px-1">/c/your-private-code</code>.
          </p>
        </div>
        <span className="chip chip-info">🔒 Videos are deleted after checking</span>
      </section>

      <p className="hint mt-8 text-center">
        RepCheck is a coaching helper, not a medical tool. It never diagnoses injuries and never gives diet advice.
      </p>
    </main>
  );
}
