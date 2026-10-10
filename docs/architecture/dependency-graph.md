# Dependency graph (Milestone 5)

## Model
`dependencies` rows connect two documents of one project: `source`, `target`, `relationship_type`,
`confidence` (0 to 1), `reason`, who created it and when. Unique per (source, target, type); a document cannot depend on
itself (also enforced by a database check). The graph is stored relationally and loaded per project into an in-memory
`DependencyGraph` (see ADR-005).

## Direction: which way a change travels
Every relationship type has a fixed flow. "S-201 depends on A-101" means information flows A-101 to S-201, so a
change to A-101 can outdate S-201 and not the reverse. `affects` flows source to target. `spatially_related_to` flows
both ways. The table lives in `app/engines/graph/types.py` and is mirrored in the UI only to phrase sentences.

## Strength
`edge strength = type weight x edge confidence`. Weights are configurable (`GraphConfig`): depends_on 1.0, affects and
quantity_based_on 0.9, derived_from and generated_from 0.85, approval_dependency and validation_source 0.7,
spatially_related_to 0.6, references 0.3. A structural dependency therefore outweighs a mere reference. A path's
strength is the product of its edges, so weak or distant links fade.

## Traversal (`DependencyGraph`)
- `impact_from(doc)`: everything a change can reach. `dependencies_of(doc)`: everything the document relies on.
- Breadth-first with a visited set: cycles cannot loop, no document is reported twice, the start document is never
  reported. Iterative, so a 3000-document chain works.
- Each reached document gets its shortest distance and, among equally short paths, the strongest one, with the path
  itself (every edge and its reason), so results can be explained.
- Results are ranked by strength, then distance, then document number, and are identical for any input order.
- `find_cycles()` (iterative Tarjan) reports groups of mutually dependent documents. Symmetric relationships are
  ignored, since they are mutual by nature. A cycle is a warning, not an error.
- `impact_radius(doc)` is the number of hops to the furthest document reached.

## Staleness
`validated_against_revision` is the revision of the providing document that the dependent document was last
reviewed against. A dependency is stale when the provider's current revision is higher, or when it was never
validated. New dependencies are registered as consistent with the providers' current revisions. "Mark reviewed" records
the review (who and when, audit-logged). Symmetric relationships carry no direction and are never stale. The
validation engine (Milestone 7) turns stale dependencies into release-blocking issues.

## API
`POST /dependencies`, `GET /projects/{id}/dependencies` (filters: document, type, stale), `GET|PATCH|DELETE /dependencies/{id}`,
`POST /dependencies/{id}/validate`, `GET /projects/{id}/graph`, `GET /documents/{id}/impact?direction=&max_depth=`.

## Limitations
Relationships are registered by people; nothing is inferred from file contents. Combining a changed document's
detected changes with this graph into scored, explained impact is Milestone 6.
