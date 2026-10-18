"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Logo } from "./Logo";
import { api } from "@/lib/api";

export function CoachShell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  const router = useRouter();
  const width = wide ? "max-w-6xl" : "max-w-4xl";
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 px-3 pt-3">
        <div className={`glass mx-auto flex items-center justify-between rounded-2xl px-4 py-2.5 ${width}`}>
          <Link href="/dashboard" aria-label="RepCheck coach home">
            <Logo size={30} sub="coach" />
          </Link>
          <nav className="flex items-center gap-2">
            <Link href="/dashboard" className="hidden rounded-lg px-3 py-1.5 text-sm font-semibold text-muted hover:text-ink sm:inline">
              Clients
            </Link>
            <button
              className="btn btn-ghost !min-h-9 !py-1 text-sm"
              onClick={async () => {
                await api.logout();
                router.push("/login");
              }}
            >
              Log out
            </button>
          </nav>
        </div>
      </header>
      <main className={`mx-auto px-4 py-6 ${width}`}>{children}</main>
    </div>
  );
}
