import type { Discipline, RevisionStatus, Role } from "./api";

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
};

export const formatDate = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

export const formatSize = (bytes: number) =>
  bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
