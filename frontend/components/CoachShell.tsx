"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export function CoachShell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  const router = useRouter();
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-card">
        <div className={`mx-auto flex items-center justify-between px-4 py-3 ${wide ? "max-w-6xl" : "max-w-4xl"}`}>
          <Link href="/dashboard" className="text-lg font-bold">RepCheck <span className="text-sm font-medium text-muted">coach</span></Link>
          <button className="btn btn-ghost !min-h-9 !py-1 text-sm" onClick={async () => { await api.logout(); router.push("/login"); }}>
            Log out
          </button>
        </div>
      </header>
      <main className={`mx-auto px-4 py-5 ${wide ? "max-w-6xl" : "max-w-4xl"}`}>{children}</main>
    </div>
  );
}
