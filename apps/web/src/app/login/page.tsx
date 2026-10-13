"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError, login } from "@/lib/api";

function DependencyDiagram() {
  const node = (x: number, y: number, label: string, tone: string) => (
    <g key={label}>
      <rect x={x} y={y} width="92" height="34" rx="3" fill="#fff" stroke={tone} strokeWidth="1.5" />
      <text x={x + 46} y={y + 21} textAnchor="middle" className="fill-ink font-mono" fontSize="13">{label}</text>
    </g>
  );
  return (
    <svg viewBox="0 0 360 230" className="w-full max-w-sm" role="img"
         aria-label="Illustration: a change in architecture document A-101 propagates to S-201, M-301, Q-101 and E-020">
      <g stroke="#2F5D8A" strokeWidth="1.5" fill="none">
        <path d="M104 77 L150 41 L150 41" /><path d="M104 97 L150 97" /><path d="M104 117 L150 153" />
        <path d="M242 153 L258 195" strokeDasharray="4 3" />
      </g>
      {node(12, 80, "A-101", "#B3372F")}
      {node(150, 24, "S-201", "#C2571A")}
      {node(150, 80, "M-301", "#C2571A")}
      {node(150, 136, "Q-101", "#C2571A")}
      {node(258, 178, "E-020", "#B7791F")}
    </svg>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <section className="hidden flex-col justify-between border-r border-line bg-steel-light p-12 lg:flex">
        <div className="text-lg font-semibold tracking-tight">BIMGuard</div>
        <div>
          <DependencyDiagram />
          <h1 className="mt-8 max-w-md text-3xl font-semibold leading-tight">
            Version control tells you what changed. BIMGuard tells you what that change could affect.
          </h1>
          <p className="mt-4 max-w-md text-muted">
            Change detection, dependency analysis and issue-readiness checks that sit alongside your
            existing BIM and document management.
          </p>
        </div>
        <p className="text-sm text-muted">Prototype. Uses open IFC data and simulated project data.</p>
      </section>

      <section className="flex items-center justify-center p-8">
        <form onSubmit={onSubmit} className="w-full max-w-sm" noValidate>
          <h2 className="text-2xl font-semibold">Sign in</h2>
          <p className="mt-1 text-sm text-muted">Use your BIMGuard account.</p>

          <label htmlFor="email" className="mt-8 block text-sm font-medium">Email</label>
          <input id="email" type="email" autoComplete="username" required value={email}
                 onChange={(e) => setEmail(e.target.value)}
                 className="mt-1 w-full rounded border border-line bg-white px-3 py-2" />

          <label htmlFor="password" className="mt-4 block text-sm font-medium">Password</label>
          <input id="password" type="password" autoComplete="current-password" required value={password}
                 onChange={(e) => setPassword(e.target.value)}
                 className="mt-1 w-full rounded border border-line bg-white px-3 py-2" />

          {error && (
            <p role="alert" className="mt-4 rounded border border-status-critical/40 bg-status-critical/5 px-3 py-2 text-sm text-status-critical">
              {error}
            </p>
          )}

          <button type="submit" disabled={busy || !email || !password}
                  className="mt-6 w-full rounded bg-steel px-4 py-2 font-medium text-white hover:bg-steel-dark disabled:opacity-50">
            {busy ? "Signing in" : "Sign in"}
          </button>

          <p className="mt-6 text-xs text-muted">
            Local demo: engineer@example.local / engineer-demo-pass
          </p>
        </form>
      </section>
    </main>
  );
}
