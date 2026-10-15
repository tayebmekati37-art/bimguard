# Changelog

## 1.0.0

Feature-complete prototype: change-impact and information-consistency engine for BIM projects.

### Deterministic core
- Project, document, and revision model with immutable revision history.
- IFC and JSON model extraction into a per-revision element table.
- Revision comparison with detected changes (added, removed, modified, moved).
- Dependency graph with typed, directional relationships and validation state.
- Impact analysis: severity, score, formula, path, affected elements.
- Validation rules engine with acknowledgement, readiness decision (READY / READY_WITH_WARNINGS / BLOCKED).
- Document and project health: Healthy, Warning, Stale, Critical, with reasons.

### Insights
- Project health panel with readiness banner, stale dependencies, open impacts, validation issues.
- Dashboard with one card per active project, aggregate totals.
- Interactive dependency graph, colour-coded by health, animated spread replay.
- Global search (Ctrl+K) across projects, documents, elements, issues.

### AI explanation layer (Milestone 9)
- Facts-first architecture: facts built only from engine output.
- Deterministic router with ordered rules.
- Grounding check discards any reply with an identifier not in the facts.
- Template answers always available; AI is optional and rewords only.
- Hourly limit per project; every call logged to `ai_queries`.
- Ask page, Explain button, Settings page showing AI status.

### Reports (Milestone 10)
- Readiness report as JSON, CSV, PDF.
- Same data in all three; generated from live engine output.

### Notifications (Milestone 10)
- In-app notifications table, service, and endpoints.
- Validation runs with status BLOCKED notify coordinators, reviewers, admins.
- Notification bell in the header, notifications page with unread filter.

### Audit (Milestone 10)
- Audit log page with project and action filters.
- All domain events recorded via the audit service.

### Testing (Milestone 11)
- 285 backend tests (pytest).
- 12 end-to-end tests (Playwright, headed locally, headless in CI).

## 0.8.0

Health dashboard, interactive graph, global search, filters.