const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "bimguard.token";

export type Role = "admin" | "bim_coordinator" | "engineer" | "reviewer" | "viewer";
export interface User { id: string; email: string; full_name: string; role: Role }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export const tokenStore = {
  get: () => (typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY)),
  set: (t: string) => window.localStorage.setItem(TOKEN_KEY, t),
  clear: () => window.localStorage.removeItem(TOKEN_KEY),
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore.get();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, `Cannot reach the BIMGuard API at ${API_URL}. Check that it is running.`);
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status}).`;
    try { const body = await res.json(); if (typeof body.detail === "string") detail = body.detail; } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<void> {
  const body = new URLSearchParams({ username: email, password });
  const data = await request<{ access_token: string }>("/auth/login", { method: "POST", body });
  tokenStore.set(data.access_token);
}

export const getMe = () => request<User>("/auth/me");
