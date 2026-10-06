"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, getMe, tokenStore, type User } from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          tokenStore.clear();
          router.replace("/login");
        } else {
          setError(err.message);
        }
      });
  }, [router]);

  function signOut() {
    tokenStore.clear();
    router.replace("/login");
  }

  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between border-b border-line bg-white px-6 py-3">
        <span className="font-semibold">BIMGuard</span>
        {user && (
          <div className="flex items-center gap-4 text-sm">
            <span>{user.full_name} <span className="text-muted">({user.role})</span></span>
            <button onClick={signOut} className="rounded border border-line px-3 py-1 hover:bg-paper">Sign out</button>
          </div>
        )}
      </header>
      <main className="mx-auto max-w-5xl p-8">
        <h1 className="text-2xl font-semibold">Projects</h1>
        {error && <p role="alert" className="mt-4 text-status-critical">{error}</p>}
        {!error && !user && <p className="mt-4 text-muted">Loading</p>}
        {user && (
          <div className="mt-6 rounded border border-dashed border-line bg-white p-8">
            <p className="font-medium">No projects yet.</p>
            <p className="mt-1 text-sm text-muted">
              Project creation arrives in the next milestone. You are signed in as {user.email}.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
