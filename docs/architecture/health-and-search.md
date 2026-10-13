# Health, dashboard and search (Milestone 8)

Everything here is derived on read from data the earlier milestones store. Nothing is cached or stored, so a summary
can never disagree with the underlying records.

## Document health
Four states, from the dependency graph, the open impacts and the document's status (`app/services/health.py`):

| State | Meaning |
|---|---|
| critical | stale, and also hit by a High or Critical impact nobody has reviewed; or hit by a Critical impact |
| stale | depends on a document that has moved past the revision it was reviewed against |
| warning | an open impact, a current revision that is not approved or issued, or no revision at all |
| healthy | none of the above |

Each document carries the reasons behind its state as plain sentences, shown on hover, in the graph's side panel and in
screen-reader labels. Colour is never the only signal: the state name is always written next to it.

## Project health (`GET /projects/{id}/health`)
Documents and how many have a current revision, stale dependencies, open impacts by severity, the document-health
split, the latest validation (status, counts, and whether it is **outdated**), and recent activity from the audit log.
A validation is outdated when documents, revisions, dependencies or rules changed after it ran, and the UI says so
instead of showing a status that may no longer be true.

## Dashboard (`GET /dashboard`)
The same health computed for every active project (archived ones on request), with totals. It computes per project on
each request, which is fine for tens of projects; caching or incremental summaries would be the next step at hundreds.

## Interactive graph
Nodes are coloured by health. Selecting a document opens a panel with its discipline, revision, status, health
reasons, what it relies on, what relies on it, how far its changes can reach, its latest detected changes (linked to the
comparison view) and its open impacts. "Show how it spreads" replays the downstream propagation one step at a time; it
runs once automatically when the project has stale dependencies, and is skipped when the visitor prefers reduced motion.

## Search (`GET /search?q=`)
One box (Ctrl+K) finds projects (name, client), documents (number, name, author, status, discipline, or revision such
as `v13`), elements in current revisions (tag, name or id) and issues in each project's latest validation (title,
message or rule). Results are grouped, capped per group, and navigable by keyboard.

## Filters
Document lists filter by discipline, status, text, file type, current revision and modified-since date. Impact and issue
lists filter by severity and state, and the change comparison by severity and change type.

## Limitations
Search uses case-insensitive substring matching, which suits a prototype; large deployments would add trigram or
full-text indexes. Any signed-in user can see all projects: per-project membership is on the roadmap.
