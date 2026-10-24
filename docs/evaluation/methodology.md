# Evaluation methodology

This document describes exactly what the benchmark measures, what "ground truth" means here, and what the resulting numbers do and do not claim.

## What "ground truth" means in this dataset

The labels in `benchmark/dataset.json` are **defined by construction**, not derived from a BIM engineer's review of real project data.

Every fixture was built to answer a specific question with a known-correct answer:

- "A document with no revisions — should `MISSING_REVISION` fire on it?" → Yes, that is the definition of the rule.
- "A document with a proper revision — should `MISSING_REVISION` fire on it?" → No, that is a false positive.
- "A structure document with no architecture provider in the project — should `MISSING_DEPENDENCY` fire?" → Yes.

The dataset records those expected answers, and the evaluator compares what the engine actually produced against them.

**This means the labels are only as good as the fixture designer's understanding of each rule.** A label error causes a false metric: either the rule is wrongly reported as failing when it worked correctly, or a real bug is hidden behind a wrong expectation. The labels are reviewed once (in the dataset's `notes` block) and should be reviewed again if a rule's semantics change.

## What is measured

- **Readiness assertions** (project-level): does each project's final `status` match the dataset's `expected_readiness`?
- **Per-rule precision and recall**: for each rule in `measured_rules`, compute:
  - TP — the rule fired on a document where the dataset says it should
  - FP — the rule fired on a document where the dataset says it should not
  - FN — the rule did not fire on a document where the dataset says it should
  - Precision = TP / (TP + FP) — of the fires it produced, how many were correct
  - Recall = TP / (TP + FN) — of the fires it should have produced, how many happened
  - F1 = harmonic mean

Findings from unmeasured rules are reported separately and not scored.

## What is NOT measured

`benchmark/dataset.json` contains a `not_measured` block with the reason for each excluded rule. Summary:

- **Rules requiring element-level data**: `UNRESOLVED_REFERENCE`, `OUTDATED_REFERENCE`, `PARAMETER_MISMATCH`, `CROSS_DOC_*`. All of these need fixtures with actual elements, psets, and element-to-element relationships. The dataset ships zero-element JSON fixtures and does not construct these cases.
- **`SPATIAL_CONFLICT`**: requires real IFC geometry with clearance computation. Deferred.
- **`PART_COVERAGE`**: manufacturing-domain only.
- **`DUPLICATE_REVISION_CONTENT`**: the upload API may reject same-checksum uploads before the rule can run.
- **`READINESS_POLICY`**: not a rule that emits a finding; it determines the aggregate status. Handled as a project-level assertion, not a per-rule metric.

## What the numbers mean

Correct interpretation:

> "On a synthetic dataset of X scenarios whose correct answers were established by construction, the engine found Y% of the expected fires for the 8 measured rules, with Z% precision."

Incorrect interpretations (all of which are wrong):

- ❌ "The engine is X% accurate on real BIM projects."
- ❌ "Precision of 100% here means the engine will not produce false positives on real data."
- ❌ "The 8 measured rules represent the engine's overall reliability."
- ❌ "The 10 unmeasured rules are broken or unimplemented."

## Reproducibility

Every run produces:

- `benchmark/last-run.json` — machine-readable results, including the exact dataset version, the UTC start time, per-rule TP/FP/FN, and every raw issue produced by the engine
- `docs/evaluation/results.md` — human-readable tables, regenerated on each run

To reproduce: start the API on `:8000`, run `scripts/run-evaluation.ps1`, and compare `last-run.json` against a previous run. `git diff` on the JSON file shows precisely what changed.

## Limitations

- **Synthetic dataset.** Never claims to represent a real building, real change log, or real modelling workflow.
- **Labels are designer intent.** Not a human review of actual BIM correctness.
- **Small N.** One clean project, one problem project. Real projects have many more permutations per rule.
- **Single API version.** No cross-version comparison. If a rule's implementation changes, the labels may need adjustment.
- **No cross-machine testing.** The APi is SQLite-in-memory for the fixtures; no performance claim is made.

## How to add a rule to the measured set

1. Add fixtures to `benchmark/dataset.json` for both a positive case (rule should fire) and a negative case (rule should not fire).
2. Add the rule ID to `measured_rules`.
3. Remove it from `not_measured` and note why it is now measurable.
4. Run `scripts/run-evaluation.ps1`.
5. If the rule produces FP or FN, either the rule is buggy or the label is wrong. Investigate before adjusting the label.

Do not add a rule to `measured_rules` without a positive fixture. A rule with only negative cases has recall 0/0 (undefined) and precision defined but empty, which is misleading.