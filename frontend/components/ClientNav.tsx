import Link from "next/link";
import { Logo } from "./Logo";

export function ClientNav({ token, current }: { token: string; current?: "home" | "upload" | "profile" }) {
  const items = [
    { key: "home", href: `/c/${token}`, label: "Home", icon: "🏠" },
    { key: "upload", href: `/c/${token}/upload`, label: "Upload", icon: "📹" },
    { key: "profile", href: `/c/${token}/profile`, label: "My training", icon: "📈" },
  ] as const;
  return (
    <div className="sticky top-0 z-20 -mx-4 space-y-3 px-4 pb-1 pt-3">
      <div className="flex items-center justify-between">
        <Logo size={28} />
      </div>
      <nav aria-label="Main" className="glass flex gap-1 rounded-2xl p-1 text-sm font-semibold">
        {items.map((i) => {
          const on = current === i.key;
          return (
            <Link
              key={i.key}
              href={i.href}
              aria-current={on ? "page" : undefined}
              className={`flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-xl px-2 py-2 text-center transition sm:px-3 ${
                on ? "text-white shadow-md" : "text-muted hover:text-ink"
              }`}
              style={on ? { background: "linear-gradient(135deg, var(--brand), var(--brand-2))" } : undefined}
            >
              <span aria-hidden className="hidden min-[400px]:inline">{i.icon}</span>
              {i.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
