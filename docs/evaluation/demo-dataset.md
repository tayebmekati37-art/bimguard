# Demo dataset - expected state

The demo project is loaded by `scripts/load-sample-project.ps1` and
verified by `scripts/verify-demo.ps1`. This document is the reference for
what the demo should show. `verify-demo.ps1` asserts the parts marked
**asserted**; anything marked **informational** is printed for review but
not gated on, because the exact number depends on rule configuration.

## Documents

| Number | Discipline | Baseline revision | Demo revision | File |
| :--- | :--- | :--- | :--- | :--- |
| A-101 | architecture | v12 | **v13 (in_review)** | `architecture_v2.ifc` |
| S-201 | structure | v8 | (unchanged) | — |
| M-301 | mep | v5 | (unchanged) | — |
| Q-101 | quantity | v6 | (unchanged) | — |
| E-020 | equipment | v3 | (unchanged) | — |

## Dependencies

| Source | Type | Target | Confidence |
| :--- | :--- | :--- | :--- |
| S-201 | `depends_on` | A-101 | 0.95 |
| M-301 | `depends_on` | A-101 | 0.90 |
| Q-101 | `quantity_based_on` | A-101 | 1.00 |
| E-020 | `depends_on` | M-301 | 0.80 |
| M-301 | `spatially_related_to` | S-201 | 0.60 |

## Changes in A-101 v13

- Wall `W-204` moved 300 mm
- Door `D-202A` relocated
- Room `204` parameters changed
- Wall `W-207` added

## Expected health states after A-101 v13

| Document | State | Why |
| :--- | :--- | :--- |
| A-101 | **warning** (asserted) | v13 is `in_review`, not `approved` |
| S-201 | **critical** (asserted) | Stale against A-101, hit by high-severity impact |
| M-301 | **critical** (asserted) | Stale against A-101, hit by high-severity impact |
| Q-101 | **critical** (asserted) | Stale against A-101, hit by high-severity impact |
| E-020 | **warning** (asserted) | Reached indirectly through M-301, not direct staleness |

## Expected dependency staleness

| Edge | Stale? | Why |
| :--- | :--- | :--- |
| S-201 → A-101 | **stale** (asserted) | Validated against v12, A-101 is now v13 |
| M-301 → A-101 | **stale** (asserted) | Same |
| Q-101 → A-101 | **stale** (asserted) | Same |
| E-020 → M-301 | not stale | M-301 has not changed |
| M-301 ↔ S-201 | never stale | `spatially_related_to` is two-way; the engine does not flag two-way edges as stale |

The three stale dependencies are asserted by `verify-demo.ps1`. The
two-way edge not being stale is confirmed by the same test.

## Expected validation result

| Field | Expected |
| :--- | :--- |
| `status` | **BLOCKED** (asserted) |
| `total` issues | greater than 0 (asserted) |
| `blocking` issues | greater than 0 (asserted) |
| `STALE_DEPENDENCY` findings | **3** (asserted) |

Other per-rule counts are printed by `verify-demo.ps1` but not asserted,
because they depend on which rules a project has enabled. The three stale
dependencies are the invariant; the rest are configuration-dependent.

## After resolve-demo.ps1

`scripts/resolve-demo.ps1` marks each stale dependency as reviewed against
the current revision. After running it:

- Every document should be `healthy`
- The next validation run should be `READY_WITH_WARNINGS` or `READY`
- `STALE_DEPENDENCY` findings should be zero

The demo document does not assert exact counts for the "after" state
because the demo currently verifies only the "after A-101 v13" state. A
future iteration could add post-resolve assertions to `verify-demo.ps1`.

## What this dataset is NOT

- Not a real building. Every element, tag, and dimension is synthetic.
- Not a benchmark for accuracy. It exercises the pipeline; it does not
  measure whether the rules match real engineering judgement.
- Not stable across engine versions in terms of scores. Health states
  and staleness flags are stable; numeric impact scores may change if
  the scoring formula is revised.