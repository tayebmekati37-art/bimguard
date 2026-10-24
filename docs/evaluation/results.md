# Benchmark results

Generated: 2026-10-24T23:13:48.044134+00:00

## What this measures

Precision and recall for the rules listed under *Measured rules*, on a synthetic dataset whose expected findings are defined by construction. See `docs/evaluation/methodology.md` for the full scope and limitations.

## Readiness assertions

| Project | Expected | Actual | Pass |
| :--- | :--- | :--- | :--- |
| `eval-clean` | READY | READY | PASS |
| `eval-problems` | BLOCKED | BLOCKED | PASS |

## Measured rules

| Rule | TP | FP | FN | Precision | Recall | F1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `MISSING_REVISION` | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| `INVALID_REVISION_SEQUENCE` | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| `STALE_DEPENDENCY` | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| `UNREVIEWED_DOWNSTREAM` | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| `MISSING_DEPENDENCY` | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| `NAMING_CONVENTION` | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| `APPROVAL_REQUIRED` | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 |

No mismatches. Every measured rule fired on exactly the documents it was expected to, and on none it was not.

## Findings from unmeasured rules

None. Every finding came from a rule that was measured.

## Not measured

The following rules are documented as out of scope for this evaluation and why:

- `READINESS_POLICY` — Config rule. Determines aggregate status rather than emitting a finding. Measured separately as a project-level readiness assertion.
- `DUPLICATE_REVISION_CONTENT` — Upload API may reject duplicate checksums before the rule runs. Not reliably constructible via HTTP.
- `MISSING_METADATA` — The create-document API auto-fills author from the current authenticated user, so an empty-author document cannot be constructed via HTTP.
- `UNRESOLVED_REFERENCE` — Requires bimguard.elements/1 fixtures with element-level BasedOn properties. Deferred to v2.
- `SPATIAL_CONFLICT` — Requires real IFC geometry with actual clearance computation. Deferred.
- `OUTDATED_REFERENCE` — Requires element-level BasedOn chains across revisions. Deferred.
- `PARAMETER_MISMATCH` — Requires coordinated psets across two documents via matching element tags. Deferred.
- `CROSS_DOC_TAG_MISSING` — Requires JSON fixtures with distinct element sets across two documents.
- `CROSS_DOC_PROPERTY_DIVERGENCE` — Requires JSON fixtures with property-level diffs across two documents.
- `CROSS_DOC_TAG_UNEXPECTED` — Requires JSON fixtures with distinct element sets.
- `PART_COVERAGE` — Manufacturing-domain only. Deferred to a separate manufacturing evaluation.

## Limitations

- **Synthetic dataset.** The labels come from the designer's intent, not from a BIM engineer's review of real project data. Precision and recall here measure whether the engine finds what the fixture designer said it should find.
- **8 of 18 rules measured.** The remaining 10 need fixtures the current HTTP-only setup cannot construct (element-level geometry, cross-document psets, manufacturing-domain setup).
- **Single project per scenario.** One clean project and one problem project. Real projects have many more permutations and false-positive opportunities.
- **No cross-machine testing.** These numbers were produced on one machine with one API version.
- **Do not interpret as real-world accuracy.** These numbers do not generalize to commercial BIM projects. That would require an independently labelled dataset from a real project.
