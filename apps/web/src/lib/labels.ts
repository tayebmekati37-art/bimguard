import type { Discipline, RelationshipType, RevisionStatus, Role } from "./api";

export const DISCIPLINES: Record<Discipline, string> = {
  architecture: "Architecture", structure: "Structure", mep: "MEP",
  equipment: "Equipment", quantity: "Quantity", general: "General",
};

export const STATUSES: Record<RevisionStatus, string> = {
  draft: "Draft", in_review: "In review", approved: "Approved",
  issued: "Issued", superseded: "Superseded", rejected: "Rejected",
};

export const STATUS_TRANSITIONS: Record<RevisionStatus, RevisionStatus[]> = {
  draft: ["in_review"], in_review: ["approved", "rejected", "draft"], approved: ["issued", "in_review"],
  issued: [], rejected: ["draft"], superseded: [],
};

export const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin", bim_coordinator: "BIM coordinator", engineer: "Engineer", reviewer: "Reviewer", viewer: "Viewer",
};

export const can = {
  manageProjects: (r: Role) => r === "admin" || r === "bim_coordinator",
  deleteProjects: (r: Role) => r === "admin",
  editDocuments: (r: Role) => r === "admin" || r === "bim_coordinator" || r === "engineer",
  changeStatus: (r: Role) => r !== "viewer",
  compare: (r: Role) => r !== "viewer",
};

export const CHANGE_TYPES: Record<string, string> = {
  ELEMENT_ADDED: "Added", ELEMENT_REMOVED: "Removed", GEOMETRY_CHANGED: "Geometry", PARAMETER_CHANGED: "Parameter",
  SPATIAL_CHANGED: "Spatial", CLASSIFICATION_CHANGED: "Classification", METADATA_CHANGED: "Metadata",
  REFERENCE_CHANGED: "Reference",
};
export const SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;

export const formatDate = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

export const formatSize = (bytes: number) =>
  bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;

export const RELATIONSHIPS: Record<RelationshipType, { label: string; phrase: (s: string, t: string) => string; hint: string }> = {
  depends_on: { label: "Depends on", phrase: (s, t) => `${s} depends on ${t}`, hint: "Strongest. Use when the source is designed from the target." },
  affects: { label: "Affects", phrase: (s, t) => `${s} affects ${t}`, hint: "Changes to the source can outdate the target." },
  quantity_based_on: { label: "Quantities based on", phrase: (s, t) => `${s} quantities are based on ${t}`, hint: "Take-offs and schedules measured from the target." },
  derived_from: { label: "Derived from", phrase: (s, t) => `${s} is derived from ${t}`, hint: "Content copied or computed from the target." },
  generated_from: { label: "Generated from", phrase: (s, t) => `${s} is generated from ${t}`, hint: "Output produced from the target model." },
  validation_source: { label: "Validated against", phrase: (s, t) => `${s} is validated against ${t}`, hint: "The target is the reference used to check the source." },
  approval_dependency: { label: "Needs approval of", phrase: (s, t) => `${s} needs approval of ${t}`, hint: "The source cannot be issued before the target is approved." },
  spatially_related_to: { label: "Spatially related to", phrase: (s, t) => `${s} is spatially related to ${t}`, hint: "Share space, for example HVAC next to structure. Works both ways." },
  references: { label: "References", phrase: (s, t) => `${s} references ${t}`, hint: "Weakest. A mention, not a design dependency." },
};

// Mirrors the server's flow table (app/engines/graph/types.py); the server is the source of truth for results.
export const FLOW: Record<RelationshipType, "target_to_source" | "source_to_target" | "both"> = {
  depends_on: "target_to_source", affects: "source_to_target", references: "target_to_source",
  generated_from: "target_to_source", derived_from: "target_to_source", spatially_related_to: "both",
  quantity_based_on: "target_to_source", validation_source: "target_to_source", approval_dependency: "target_to_source",
};

export function flowSentence(flow: "target_to_source" | "source_to_target" | "both", source: string, target: string): string {
  if (flow === "target_to_source") return `A change to ${target} can outdate ${source}.`;
  if (flow === "source_to_target") return `A change to ${source} can outdate ${target}.`;
  return `A change to either ${source} or ${target} can affect the other.`;
}
