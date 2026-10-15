import { Page, request as playwrightRequest } from "@playwright/test";

export const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8001";
export const PASSWORD = "admin-demo-pass";
export const ADMIN_EMAIL = "admin@example.local";
export const COORD_EMAIL = "coordinator@example.local";
export const ENGINEER_EMAIL = "engineer@example.local";

export function uniqueName(prefix: string): string {
  const stamp = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  return `${prefix}-${stamp}`;
}

export async function apiLogin(email: string, password = PASSWORD): Promise<string> {
  const ctx = await playwrightRequest.newContext();
  const res = await ctx.post(`${API_URL}/auth/login`, {
    form: { username: email, password },
  });
  if (!res.ok()) throw new Error(`Login failed: ${res.status()} ${await res.text()}`);
  const body = await res.json();
  await ctx.dispose();
  return body.access_token as string;
}

export async function apiPost(token: string, path: string, data: unknown) {
  const ctx = await playwrightRequest.newContext({
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const res = await ctx.post(`${API_URL}${path}`, { data });
  const text = await res.text();
  await ctx.dispose();
  if (!res.ok()) throw new Error(`POST ${path} failed: ${res.status()} ${text}`);
  return JSON.parse(text);
}

export async function apiGet(token: string, path: string) {
  const ctx = await playwrightRequest.newContext({
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const res = await ctx.get(`${API_URL}${path}`);
  const text = await res.text();
  await ctx.dispose();
  if (!res.ok()) throw new Error(`GET ${path} failed: ${res.status()} ${text}`);
  return JSON.parse(text);
}

export async function seedAuth(page: Page, token: string) {
  await page.addInitScript((t: string) => {
    try { window.localStorage.setItem("bimguard.token", t); } catch {}
  }, token);
}

export async function uiLogin(page: Page, email: string, password = PASSWORD) {
  await page.goto("/login");
  const emailInput = page
    .locator('input[type="email"], input[name="email"], input[name="username"]')
    .first();
  const passwordInput = page.locator('input[type="password"]').first();
  await emailInput.fill(email);
  await passwordInput.fill(password);
  await page
    .getByRole("button")
    .filter({ hasText: /sign in|log in|login/i })
    .first()
    .click();
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 });
}