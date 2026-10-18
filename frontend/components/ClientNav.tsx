import Link from "next/link";

export function ClientNav({ token, current }: { token: string; current?: "home" | "upload" | "profile" }) {
  const items = [
    { key: "home", href: `/c/${token}`, label: "Home" },
    { key: "upload", href: `/c/${token}/upload`, label: "Upload" },
    { key: "profile", href: `/c/${token}/profile`, label: "My training" },
  ] as const;
  return (
    <nav aria-label="Main" className="flex gap-1 rounded-xl border border-line bg-card p-1 text-sm font-semibold">
      {items.map((i) => (
        <Link
          key={i.key}
          href={i.href}
          aria-current={current === i.key ? "page" : undefined}
          className={`flex-1 rounded-lg px-3 py-2 text-center ${current === i.key ? "bg-brand text-brand-ink" : "text-muted"}`}
        >
          {i.label}
        </Link>
      ))}
    </nav>
  );
}
