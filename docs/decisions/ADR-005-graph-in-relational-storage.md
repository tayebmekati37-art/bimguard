# ADR-005: Document graph in relational storage

**Status:** accepted

**Context.** Projects have 100 to 10 000 documents and typically a few relationships per document. Queries are
"what does a change to X reach" and "which dependencies are stale", always within one project.

**Decision.** Store edges in a `dependencies` table (indexed by project and target) and traverse in application
code. No graph database. The traversal is a small pure module that takes nodes and edges, so storage could change
without touching it.

**Consequences.** One database to run, back up and migrate; transactional consistency with documents and revisions;
foreign-key cascades remove edges with their documents. Loading one project's edges is a single indexed query, which is
cheap at this scale. A graph database would become attractive only for deep cross-project path queries over millions of
edges, which is not this product's workload.
