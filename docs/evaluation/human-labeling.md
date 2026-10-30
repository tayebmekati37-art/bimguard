# Human-labeled evaluation (M28)

M22 ships a synthetic benchmark: fixture data, labels by construction,
seven rules measured. That answers "does the engine do what we think it
should do?"

M28 is the answer to the harder question: **"are we right about what it
should do?"** That can only be measured by a BIM engineer looking at
real findings on real data and marking each one correct or incorrect.

## What ships

Two tools and this doc. **No labeled data.** The data comes from a real
project and a real engineer; faking either would defeat the purpose.

    scripts/export-for-labeling.py   produces the CSV a labeler fills in
    scripts/eval-from-labels.py      reads the returned CSV and reports metrics

## Workflow

### 1. Prepare a real project

Load a real project into BIMGuard (or use a demo project loaded with real data).
Run validation so it has at least one `ValidationRun`. Confirm the latest run
looks sensible:

    python scripts/export-for-labeling.py --list-projects
    # verify the project you want appears, with a reasonable document count

### 2. Export findings

    python scripts/export-for-labeling.py --project <uuid> --out labeled.csv

Output:
- `labeled.csv` — one row per finding, mostly engine data, three empty columns for the labeler
- `labeled.csv.readme.txt` — instructions for the labeler (do not send the CSV without this)

### 3. Send to the BIM engineer

The engineer:
- Opens `labeled.csv` in Excel
- Reads `labeled.csv.readme.txt` for context
- For each row: `labeler_correct` (Y/N), optionally `labeler_severity_ok`, `labeler_note`
- Adds rows at the bottom for findings the engine missed
- Returns the CSV

### 4. Compute metrics

    python scripts/eval-from-labels.py --labeled returned.csv
    python scripts/eval-from-labels.py --labeled returned.csv --json metrics.json

Output:
- Per-rule precision, recall, F1
- Overall micro-averaged precision, recall, F1
- Severity accuracy (only if `labeler_severity_ok` was filled)
- Unlabeled rate (rows the engineer skipped)

## What "correct" means

The labeler is asked a narrow question: **did the engine correctly apply the rule as stated?**

A finding is `Y` when:
- The rule's stated description matches what the engine reported
- The evidence supports it (the engine's message names a real problem with a real document/element)
- The severity is a reasonable interpretation of the rule's own severity

A finding is `N` when:
- The engine fired a rule whose conditions are not actually met
- The message references an element or document that does not have the problem described
- The rule fired for a reason that contradicts its own description

A finding is `unlabeled` when:
- The labeler is genuinely unsure
- The finding requires business context not present in the CSV
- The document is out of scope for this review

**Unlabeled rows are excluded from metrics.** The unlabeled rate is reported separately. High unlabeled rate (>20%) means the CSV needs a second pass or the labels need more context.

## Labeler additions

If the labeler spots a problem the engine missed, they add a row with:
- `finding_id`: **empty**
- `rule_id`: which rule should have fired
- `document_number`: which document
- `element_tag`: optional
- `labeler_note`: one sentence explaining what the engine missed

These count as **false negatives** for that rule. The `rule_id` must be a rule the engine already has — otherwise the addition cannot be mapped to a rule and will be dropped by the evaluator.

This means M28 does **not** measure what the engine should have caught via rules it does not have. If the labeler spots "there's no rule for X", that goes in a separate `docs/evaluation/missing-rules.md` file (manual, not this tool).

## What this measures, precisely

**Precision** = TP / (TP + FP)
Of the findings the engine reported and the labeler reviewed, what fraction did the labeler agree with.

**Recall** = TP / (TP + FN)
Of the findings the labeler identified (engine + additions), what fraction did the engine report.

**F1** = harmonic mean of the two.

**Severity accuracy** = fraction of TP findings where `labeler_severity_ok=Y`. A finding can be correct but with the wrong severity. That is counted as TP with low severity accuracy, not FP.

## What this does NOT measure

- **Rule-set alignment with the labeler's preferences.** A rule the labeler would never have in their own system, but which fires correctly per its description, is still a `Y`. Disagreement about the rule's existence is not precision loss.
- **Rule-set completeness.** A problem the labeler spots for which no rule exists is not an FN for any rule. It is out of scope for this tool.
- **Cross-labeler agreement.** One labeler assumed. Two-labeler reconciliation is a bigger tool that this milestone does not ship.
- **Cross-project generalization.** Precision on one project does not imply precision on another. Run the drill on multiple projects to get a range.
- **Performance over time.** No tracking of drift between runs on the same project. That would be a separate milestone.

## Interpreting the results

If the overall precision comes out at, say, 0.82, that means:

> "On project X, of the engine findings that a BIM engineer reviewed, 82% were ones they agreed were real. The remaining 18% were false positives."

If recall comes out at 0.65:

> "The engineer identified 100 findings that should have been reported (including ones the engine missed). The engine reported 65 of them."

Recall is usually harder to raise because it depends on identifying what the engine missed. Precision is easier to improve because a false positive is directly visible.

If both are low, the likely cause is not the engine's logic but the rule set itself being mismatched to the project's actual standards. That is a feedback loop: use the results to inform which rules need revision, then re-measure.

## What this needs before results can be claimed

1. **A real project** — not the synthetic demo, not the eval fixtures
2. **A named BIM engineer** — who agrees to review the CSV
3. **Their actual time** — one CSV with 50-100 findings takes 4-8 hours of focused review

The tools ship today. The results ship when a real project and a real engineer have been paired.

## What the README and demo should say until results exist

*"The engine has been tested against a labeled synthetic dataset (M22): 100% precision and recall on the 7 rules that could be measured. Accuracy on real projects has not been independently measured; see `docs/evaluation/human-labeling.md` for the workflow and what would be required."*

Do not claim real-world accuracy until a returned CSV exists. The M28 tools are the infrastructure for a claim, not the claim itself.