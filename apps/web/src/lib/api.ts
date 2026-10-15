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
  projectId: string,
  p: { discipline?: string; status?: string; q?: string; file_type?: string; revision?: string; modified_since?: string; limit?: number; offset?: number },
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

export interface Comparison {
  id: string; project_id: string; document_id: string; document_number: string;
  from_revision_id: string; to_revision_id: string; from_revision_number: number; to_revision_number: number;
  created_at: string; created_by_name: string; total_changes: number;
  counts: { by_type?: Record<string, number>; by_severity?: Record<string, number>;
            elements_old?: number; elements_new?: number; elements_unchanged?: number };
  config: Record<string, unknown>;
}
export interface ChangeRecord {
  id: string; element_guid: string | null; element_tag: string; element_name: string; ifc_class: string;
  change_type: string; field: string; old_value: unknown; new_value: unknown; severity: string;
  confidence: number; summary: string; match_method: string; detail: Record<string, unknown>;
}
export interface PlanGeometry {
  location?: number[]; rotation_deg?: number;
  footprint?: { x0: number; y0: number; x1: number; y1: number; height: number };
}
export interface PlanElement {
  guid: string; tag: string; name: string; ifc_class: string; status: "added" | "removed" | "modified" | "unchanged";
  change_types: string[]; old: PlanGeometry | null; new: PlanGeometry | null;
}
export interface PlanData { changed: PlanElement[]; context: PlanElement[] }

export const getRevisionComparison = (revisionId: string) => request<Comparison>(`/revisions/${revisionId}/comparison`);
export const runComparison = (revisionId: string) => request<Comparison>(`/revisions/${revisionId}/compare`, { method: "POST" });
export const listChanges = (
  comparisonId: string, p: { change_type?: string; severity?: string; q?: string; limit?: number; offset?: number },
) => request<Page<ChangeRecord>>(`/comparisons/${comparisonId}/changes${qs(p)}`);
export const getPlan = (comparisonId: string) => request<PlanData>(`/comparisons/${comparisonId}/footprints`);

export type RelationshipType = "depends_on" | "affects" | "references" | "generated_from" | "derived_from"
  | "spatially_related_to" | "quantity_based_on" | "validation_source" | "approval_dependency";
export interface DependencyRecord {
  id: string; project_id: string; source_document_id: string; source_number: string; source_name: string;
  target_document_id: string; target_number: string; target_name: string; relationship_type: RelationshipType;
  flow: "target_to_source" | "source_to_target" | "both"; provider_document_id: string | null;
  provider_number: string | null; provider_current_revision: number | null; confidence: number; strength: number;
  reason: string; validated_against_revision: number | null; validated_at: string | null;
  validated_by_name: string; is_stale: boolean; created_by_name: string; created_at: string;
}
export type HealthState = "healthy" | "warning" | "stale" | "critical";
export interface GraphNode {
  id: string; document_number: string; name: string; discipline: Discipline; status: RevisionStatus;
  current_revision_number: number | null; health: HealthState; health_reasons: string[];
}
export interface GraphData { nodes: GraphNode[]; edges: DependencyRecord[]; cycles: string[][]; stale_count: number }
export interface ImpactItem {
  document_id: string; document_number: string; name: string; discipline: Discipline;
  current_revision_number: number | null; distance: number; direct: boolean; strength: number;
  path: { edge_id: string; from_number: string; to_number: string; relationship_type: RelationshipType; strength: number; reason: string }[];
}
export interface ImpactData {
  root_document_id: string; root_document_number: string; direction: string; radius: number; items: ImpactItem[];
}

export const getGraph = (projectId: string) => request<GraphData>(`/projects/${projectId}/graph`);
export const createDependency = (b: {
  source_document_id: string; target_document_id: string; relationship_type: RelationshipType;
  confidence: number; reason: string;
}) => request<DependencyRecord>("/dependencies", jsonInit("POST", b));
export const deleteDependency = (id: string) => request<void>(`/dependencies/${id}`, { method: "DELETE" });
export const validateDependency = (id: string) =>
  request<DependencyRecord>(`/dependencies/${id}/validate`, { method: "POST" });
export const getImpact = (documentId: string, direction: "downstream" | "upstream") =>
  request<ImpactData>(`/documents/${documentId}/impact${qs({ direction })}`);

export interface ImpactFactor { key: string; label: string; value: number; explanation: string }
export interface ImpactPathStep {
  edge_id: string; from_number: string; to_number: string; relationship_type: RelationshipType;
  strength: number; confidence: number; reason: string;
}
export interface AffectedElement {
  guid: string; tag: string; name: string; ifc_class: string; room: string | null; kinds: string[];
  reasons: string[]; distance_mm: number | null;
}
export interface ImpactEvent {
  id: string; analysis_id: string; changed_document_id: string; changed_document_number: string;
  changed_revision_number: number; impacted_document_id: string; impacted_document_number: string;
  impacted_name: string; impacted_discipline: Discipline; impacted_status: RevisionStatus; distance: number;
  direct: boolean; score: number; severity: string; confidence: number; state: "open" | "reviewed" | "advisory";
  reason: string; formula: string; factors: ImpactFactor[]; path: ImpactPathStep[]; affected_elements: AffectedElement[];
  affected_element_count: number; note: string; first_edge_id: string | null;
  dependency_validated_against: number | null; validated_by_name: string; validated_at: string | null; created_at: string;
}
export interface ProjectImpact {
  analyses: { id: string; changed_document_id: string; changed_document_number: string; changed_revision_number: number;
              created_at: string; summary: { total?: number; changes?: number; radius?: number; by_severity?: Record<string, number> };
              config: Record<string, unknown> }[];
  counts: { total: number; open: number; reviewed: number; advisory: number; open_by_severity: Record<string, number> };
  events: Page<ImpactEvent>;
}

export const getProjectImpact = (projectId: string, p: { severity?: string; state?: string; limit?: number; offset?: number }) =>
  request<ProjectImpact>(`/projects/${projectId}/impact-analysis${qs(p)}`);
export const runImpactAnalysis = (projectId: string) =>
  request<ProjectImpact>(`/projects/${projectId}/impact-analysis`, { method: "POST" });

export interface RuleRecord {
  rule_id: string; name: string; description: string; category: string; enabled: boolean; severity: string;
  params: Record<string, unknown>; default_enabled: boolean; default_severity: string;
  default_params: Record<string, unknown>; is_default: boolean; configurable_severity: boolean; can_disable: boolean;
  updated_at: string; updated_by_name: string;
}
export type ReadinessStatus = "BLOCKED" | "READY_WITH_WARNINGS" | "READY";
export interface ValidationRun {
  id: string; project_id: string; created_at: string; created_by_name: string; status: ReadinessStatus;
  duration_ms: number; rules_snapshot: Record<string, unknown>;
  summary: { documents_checked?: number; total?: number; open?: number; acknowledged?: number; blocking?: number;
             blocking_severity?: string; open_by_severity?: Record<string, number>; by_rule?: Record<string, number> };
}
export interface ValidationIssue {
  id: string; run_id: string; rule_id: string; rule_name: string; category: string; severity: string;
  document_id: string | null; document_number: string; element_tag: string; title: string; message: string;
  recommended_action: string; details: Record<string, unknown>; status: "open" | "acknowledged";
  acknowledged_by_name: string; acknowledged_at: string | null; acknowledgement_note: string;
}

export const listRules = () => request<RuleRecord[]>("/rules");
export const updateRule = (id: string, b: { enabled?: boolean; severity?: string; params?: Record<string, unknown> }) =>
  request<RuleRecord>(`/rules/${id}`, jsonInit("PATCH", b));
export const resetRule = (id: string) => request<RuleRecord>(`/rules/${id}/reset`, { method: "POST" });
export const getLatestRun = (projectId: string) => request<ValidationRun>(`/projects/${projectId}/validation-runs/latest`);
export const runValidation = (projectId: string) => request<ValidationRun>(`/projects/${projectId}/validate`, { method: "POST" });
export const listIssues = (runId: string, p: { severity?: string; status?: string; limit?: number; offset?: number }) =>
  request<Page<ValidationIssue>>(`/validation-runs/${runId}/issues${qs(p)}`);
export const acknowledgeIssue = (id: string, note: string) =>
  request<ValidationIssue>(`/issues/${id}/acknowledge`, jsonInit("POST", { note }));
export const revokeAcknowledgement = (id: string) =>
  request<ValidationIssue>(`/issues/${id}/acknowledge`, { method: "DELETE" });

export interface ValidationHealth {
  run_id: string; status: "BLOCKED" | "READY_WITH_WARNINGS" | "READY"; created_at: string; open: number; blocking: number;
  acknowledged: number; open_by_severity: Record<string, number>; outdated: boolean;
}
export interface ProjectHealth {
  project_id: string; project_name: string; project_status: string; client: string; documents: number;
  documents_with_revision: number; disciplines: Record<string, number>; dependencies: number; stale_dependencies: number;
  open_impacts: { total: number; by_severity: Record<string, number> };
  document_health: Record<HealthState, number>;
  documents_health: { document_id: string; document_number: string; name: string; state: HealthState; reasons: string[] }[];
  validation: ValidationHealth | null;
  recent_activity: { at: string; user: string; action: string; text: string }[];
  last_change_at: string | null;
}
export interface DashboardProject {
  project_id: string; project_name: string; client: string; project_status: string; documents: number;
  stale_dependencies: number; open_impacts: { total: number; by_severity: Record<string, number> };
  document_health: Record<HealthState, number>; validation: ValidationHealth | null; last_change_at: string | null;
}
export interface Dashboard {
  totals: { projects: number; documents: number; stale_dependencies: number; open_impacts: number; blocked: number;
            ready: number; not_validated: number; critical_documents: number };
  projects: DashboardProject[];
}
export interface SearchHit {
  kind: "project" | "document" | "element" | "issue"; id: string; title: string; subtitle: string; project_id: string;
  project_name: string; document_number: string;
}
export interface SearchResults { query: string; projects: SearchHit[]; documents: SearchHit[]; elements: SearchHit[]; issues: SearchHit[] }
export interface OverviewLink {
  document_id: string; document_number: string; relationship_type: RelationshipType; current_revision: number | null;
  validated_against_revision: number | null; stale: boolean;
}
export interface DocumentOverview {
  document: { id: string; project_id: string; document_number: string; name: string; discipline: Discipline; status: RevisionStatus;
              current_revision_number: number | null; author: string; file_type: string; modified_at: string };
  health_state: HealthState; health_reasons: string[]; providers: OverviewLink[]; dependents: OverviewLink[];
  downstream_count: number; radius: number;
  latest_comparison: { id: string; revision_id: string; from_revision_number: number; to_revision_number: number;
                       total_changes: number; by_severity: Record<string, number>; by_type: Record<string, number> } | null;
  open_impacts: { changed_document_number: string; changed_revision_number: number; score: number; severity: string; direct: boolean }[];
}

export const getProjectHealth = (projectId: string) => request<ProjectHealth>(`/projects/${projectId}/health`);
export const getDashboard = () => request<Dashboard>("/dashboard");
export const searchAll = (q: string) => request<SearchResults>(`/search${qs({ q })}`);
export const getDocumentOverview = (documentId: string) => request<DocumentOverview>(`/documents/${documentId}/overview`);


export interface AskResponse {
  answer: string;
  path: "template" | "ai";
  question_type: string;
  violations: string[];
}
export interface AiStatus {
  enabled: boolean;
  model: string | null;
  hourly_limit: number;
}

export const askProject = (projectId: string, question: string, aiEnabled: boolean) =>
  request<AskResponse>(`/projects/${projectId}/ask`,
    jsonInit("POST", { question, ai_enabled: aiEnabled }));
export const getAiStatus = () => request<AiStatus>("/ai/status");
