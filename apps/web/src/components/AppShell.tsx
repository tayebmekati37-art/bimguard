"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { ApiError, getMe, tokenStore, type User } from "@/lib/api";
import { SearchBox } from "@/components/SearchBox";
import { NotificationBell } from "@/components/NotificationBell";
import { ROLE_LABELS } from "@/lib/labels";

const UserContext = createContext<User | null>(null);

export function useUser(): User {
  const user = useContext(UserContext);
  if (!user) throw new Error("useUser must be used inside AppShell");
  return user;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!tokenStore.get()) { router.replace("/login"); return; }
    getMe().then(setUser).catch((err) => {
      if (err instanceof ApiError && err.status === 401) { tokenStore.clear(); router.replace("/login"); }
      else setError(err.message);
    });
  }, [router]);

  function signOut() { tokenStore.clear(); router.replace("/login"); }

  if (error) return <p role="alert" className="p-8 text-status-critical">{error}</p>;
  if (!user) return <p className="p-8 text-muted">Loading</p>;

  return (
    <UserContext.Provider value={user}>
      <header className="flex items-center justify-between border-b border-line bg-white px-6 py-3">
        <nav className="flex items-center gap-6">
          <Link href="/dashboard" className="font-semibold">BIMGuard</Link>
          <Link href="/dashboard" className="text-sm text-muted hover:text-ink">Dashboard</Link>
          <Link href="/projects" className="text-sm text-muted hover:text-ink">Projects</Link>
          <Link href="/rules" className="text-sm text-muted hover:text-ink">Rules</Link>
          {["admin", "bim_coordinator", "reviewer"].includes(user.role) && (
            <Link href="/audit" className="text-sm text-muted hover:text-ink">Audit</Link>
          )}
        </nav>
        <div className="flex items-center gap-4 text-sm">
          <SearchBox />
          <NotificationBell />
          <span>{user.full_name} <span className="text-muted">({ROLE_LABELS[user.role]})</span></span>
          <button onClick={signOut} className="rounded border border-line px-3 py-1 hover:bg-paper">Sign out</button>
        </div>
      </header>
      <main className="mx-auto max-w-6xl p-8">{children}</main>
    </UserContext.Provider>
  );
}
