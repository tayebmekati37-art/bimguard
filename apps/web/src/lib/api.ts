const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "bimguard.token";

export type Role = "admin" | "bim_coordinator" | "engineer" | "reviewer" | "viewer";
export type Discipline = "architecture" | "structure" | "mep" | "equipment" | "quantity" | "general";
export type RevisionStatus = "draft" | "in_review" | "approved" | "issued" | "superseded" | "rejected";
export type ProjectStatus = "active" | "archived";

export interface User { id: string; email: string; full_name: string; role: Role }
export interface Page<T> { items: T[]; total: number; limit: number; offset: number }
export interface Project {
  id: string; name: string; description: string; client: string; status: ProjectStatus;
  created_at: string; updated_at: string; document_count: number;
}
export interface DocumentRecord {
  id: string; project_id: string; document_number: string; name: string; discipline: Discipline;
  file_type: string; status: RevisionStatus; current_revision_number: number | null; author: string;
  source_system: string; checksum: string; issue_date: string | null; created_at: string; modified_at: string;
}
export interface Revision {
  id: string; document_id: string; revision_number: number; original_filename: string; file_size: number;
  checksum: string; uploaded_at: string; created_by_name: string; status: RevisionStatus;
  change_summary: string; previous_revision_id: string | null;
  extraction_status: "pending" | "ok" | "failed" | "unsupported"; extraction_message: string;
  element_count: number | null; model_schema: string | null;
}
export interface ElementRecord {
  id: string; revision_id: string; guid: string; ifc_class: string; name: string; tag: string;
  level: string | null; room: string | null; material: string | null;
  properties: Record<string, unknown>;
  geometry: { location?: number[]; rotation_deg?: number; dimensions?: Record<string, number> };
}
export interface ModelSummary {
  total: number; by_class: { key: string; count: number }[]; by_level: { key: string; count: number }[];
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export const tokenStore = {
  get: () => (typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY)),
  set: (t: string) => window.localStorage.setItem(TOKEN_KEY, t),
  clear: () => window.localStorage.removeItem(TOKEN_KEY),
};

async function send(path: string, init: RequestInit = {}): Promise<Response> {
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
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        const where = body.detail[0].loc?.slice(1).join(".");
        detail = `${where ? where + ": " : ""}${body.detail[0].msg}`;
      }
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await send(path, init);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

const qs = (params: Record<string, string | number | undefined>) => {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== "") p.set(k, String(v)); });
  const s = p.toString();
  return s ? `?${s}` : "";
};

export async function login(email: string, password: string): Promise<void> {
  const body = new URLSearchParams({ username: email, password });
  const data = await request<{ access_token: string }>("/auth/login", { method: "POST", body });
  tokenStore.set(data.access_token);
}

export const getMe = () => request<User>("/auth/me");

export const listProjects = (p: { status?: string; q?: string; limit?: number; offset?: number }) =>
  request<Page<Project>>(`/projects${qs(p)}`);
export const getProject = (id: string) => request<Project>(`/projects/${id}`);
export const createProject = (b: { name: string; client: string; description: string }) =>
  request<Project>("/projects", jsonInit("POST", b));
export const updateProject = (id: string, b: Partial<Pick<Project, "name" | "client" | "description" | "status">>) =>
  request<Project>(`/projects/${id}`, jsonInit("PATCH", b));
export const deleteProject = (id: string) => request<void>(`/projects/${id}`, { method: "DELETE" });

export const listDocuments = (
  projectId: string, p: { discipline?: string; status?: string; q?: string; limit?: number; offset?: number },
) => request<Page<DocumentRecord>>(`/projects/${projectId}/documents${qs(p)}`);
export const createDocument = (
  projectId: string, b: { document_number: string; name: string; discipline: Discipline; author?: string },
) => request<DocumentRecord>(`/projects/${projectId}/documents`, jsonInit("POST", b));

export const listRevisions = (documentId: string) => request<Revision[]>(`/documents/${documentId}/revisions`);
export const uploadRevision = (documentId: string, form: FormData) =>
  request<Revision>(`/documents/${documentId}/revisions`, { method: "POST", body: form });
export const setRevisionStatus = (revisionId: string, status: RevisionStatus) =>
  request<Revision>(`/revisions/${revisionId}/status`, jsonInit("PATCH", { status }));

export async function downloadRevision(rev: Revision): Promise<void> {
  const res = await send(`/revisions/${rev.id}/download`);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = rev.original_filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const listElements = (
  revisionId: string,
  p: { ifc_class?: string; level?: string; room?: string; q?: string; limit?: number; offset?: number },
) => request<Page<ElementRecord>>(`/revisions/${revisionId}/elements${qs(p)}`);
export const getModelSummary = (revisionId: string) => request<ModelSummary>(`/revisions/${revisionId}/summary`);
export const reextractRevision = (revisionId: string) =>
  request<Revision>(`/revisions/${revisionId}/extract`, { method: "POST" });
