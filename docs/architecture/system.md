# BIMGuard — System Architecture & Plan

## 1. Architecture
Next.js (TS) web app -> FastAPI REST API -> PostgreSQL. Deterministic engines live in `services/`
as pure Python packages with no web/DB imports (they take domain objects, return domain objects):
- change_detection: diff two element sets -> list[DetectedChange]
- graph: build DiGraph from dependencies; BFS with visited-set (cycle-safe); distance, ranking
- impact_analysis: score = dep_weight x change_weight x propagation(distance) x status_weight, configurable
- validation: rule registry; each rule = function(ctx) -> list[Issue]; enable/severity/threshold from DB
- ai: provider abstraction (OpenAI-compatible / local); receives ONLY structured engine output
Layering in apps/api: api (routers) -> services (use-cases) -> repositories -> models. BIMProvider
interface (import_model, list_elements, get_element, get_properties, get_geometry, compare_models)
with IfcProvider (IfcOpenShell) and MockProvider; APS adapter later.
Graph stays in PostgreSQL (`dependencies` edge table, indexed on source/target); traversal in Python
(networkx or hand-rolled BFS). Heavy work (IFC parsing, compare) goes through a background task queue
(FastAPI BackgroundTasks first; Redis worker only if needed).

## 2. Domain model
Project 1-n Document 1-n Revision (immutable, previous_revision_id chain, sha256).
Revision 1-n BimElement (guid, type, level, room, properties JSONB, geometry JSONB).
Dependency(source_doc, target_doc, type, weight, confidence, reason, validated_against_revision_id).
DetectedChange(revision_id, prev_revision_id, element_id, change_type, field, old, new, severity, confidence).
ImpactEvent(change_run, doc_id, distance, score, severity, confidence, factors JSONB, reason).
ValidationRun 1-n ValidationIssue(rule_id, severity, doc_id, status open|acknowledged|resolved, action).
Rule(rule_id, enabled, severity, params JSONB). Notification, AuditLog (append-only), AiQuery.
Key stale rule: dependency.validated_against_revision < source.current_revision.

## 3. Schema (tables)
users, roles(enum), projects, documents(unique project_id+document_number), document_revisions
(unique document_id+revision_number, unique checksum per document), bim_elements(index revision_id,
guid), dependencies(unique source+target+type), detected_changes, impact_events, validation_runs,
validation_issues, rules, notifications, audit_logs, ai_queries. Cascade: project -> all children;
revisions never updated/deleted (DB trigger + service guard).

## 4. API (as specified in brief, plus)
/auth/login, /auth/me, /projects CRUD, /projects/{id}/documents, /documents/{id}/revisions,
/revisions/{id}/compare, /projects/{id}/dependencies|impact-analysis|validate|graph|report,
/validation-runs/{id}/issues, /issues/{id}/acknowledge, /search, /notifications, /audit-logs,
/rules, /ai/explain-issue, /ai/query. All list endpoints paginated.

## 5. Frontend
Next.js App Router, Tailwind, TanStack Query, typed client generated from OpenAPI, React Flow for the
graph, dense table component, severity/status badges, role-aware navigation. Pages as per brief.

## 6. Milestones / order
M1 repo+auth (this commit) -> M2 projects/documents/revisions + Alembic + audit -> M3 IFC provider ->
M4 compare -> M5 graph -> M6 impact -> M7 validation+rules -> M8 dashboard/graph UI -> M9 AI ->
M10 reports/notifications -> M11 tests/e2e -> M12 docs/demo.
