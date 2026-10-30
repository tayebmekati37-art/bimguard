"""Compute precision, recall and F1 from a human-labeled findings CSV (M28).

Input: a CSV produced by export-for-labeling.py, filled in by a BIM engineer.

Two kinds of row:

  1. Engine finding — a row with a non-empty finding_id. The labeler marked
     labeler_correct as Y (engine was right to report it) or N (wrong).

  2. Labeler addition — a row with an empty finding_id. The labeler spotted
     a finding the engine missed. The labeler filled rule_id, document_number,
     and labeler_note explaining what should have been reported.

Usage:
    python scripts/eval-from-labels.py --labeled returned.csv
    python scripts/eval-from-labels.py --labeled returned.csv --json out.json

Output: per-rule and overall precision/recall/F1, plus unlabeled rate and
severity-accuracy rate. Exit 0 on success, 1 on error, 2 if nothing is
labeled.

What this measures:
    Precision — of the findings the engine reported, how many the labeler agreed were real
    Recall    — of the findings the labeler identified (engine + additions), how many the engine reported
    F1        — harmonic mean

What this does NOT measure:
    - Whether the rule definitions are the right rules for real projects
      (a rule the labeler disagrees with on principle is not a precision failure)
    - Cross-labeler agreement (single labeler assumed; two-labeler reconciliation is out of scope)
    - Accuracy on findings the labeler chose not to review (unlabeled rate is reported separately)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

TRUE_VALUES = {"y", "yes", "true", "1", "correct", "ok", "good"}
FALSE_VALUES = {"n", "no", "false", "0", "incorrect", "wrong", "bad", "bad-finding"}


def _parse_bool(value: str) -> bool | None:
    v = (value or "").strip().lower()
    if not v:
        return None
    if v in TRUE_VALUES:
        return True
    if v in FALSE_VALUES:
        return False
    return None


def _read_csv(path: Path) -> list[dict]:
    # utf-8-sig so the BOM the exporter wrote does not end up in the first header.
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _split_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    engine: list[dict] = []
    additions: list[dict] = []
    for r in rows:
        fid = (r.get("finding_id") or "").strip()
        if fid:
            engine.append(r)
        else:
            # Only a labeler addition if it names a rule and a document.
            rule = (r.get("rule_id") or "").strip()
            doc = (r.get("document_number") or "").strip()
            if rule and doc:
                additions.append(r)
    return engine, additions


def compute_metrics(rows: list[dict]) -> dict:
    """Pure function: takes parsed CSV rows, returns metrics dict."""
    engine, additions = _split_rows(rows)

    per_rule: dict[str, dict] = defaultdict(lambda: {
        "tp": 0, "fp": 0, "fn": 0, "unlabeled": 0,
        "severity_ok": 0, "severity_checked": 0,
    })

    for r in engine:
        rule = (r.get("rule_id") or "").strip()
        if not rule:
            continue
        correct = _parse_bool(r.get("labeler_correct", ""))
        if correct is None:
            per_rule[rule]["unlabeled"] += 1
            continue
        if correct:
            per_rule[rule]["tp"] += 1
            sev = _parse_bool(r.get("labeler_severity_ok", ""))
            if sev is not None:
                per_rule[rule]["severity_checked"] += 1
                if sev:
                    per_rule[rule]["severity_ok"] += 1
        else:
            per_rule[rule]["fp"] += 1

    for r in additions:
        rule = (r.get("rule_id") or "").strip()
        if rule:
            per_rule[rule]["fn"] += 1

    total = {"tp": 0, "fp": 0, "fn": 0, "unlabeled": 0,
             "severity_ok": 0, "severity_checked": 0}
    out_rules: dict[str, dict] = {}
    for rule in sorted(per_rule):
        m = per_rule[rule]
        tp, fp, fn = m["tp"], m["fp"], m["fn"]
        precision = tp / (tp + fp) if (tp + fp) > 0 else None
        recall = tp / (tp + fn) if (tp + fn) > 0 else None
        if precision is not None and recall is not None and (precision + recall) > 0:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = None
        sev_acc = (m["severity_ok"] / m["severity_checked"]) if m["severity_checked"] > 0 else None
        out_rules[rule] = {
            "tp": tp, "fp": fp, "fn": fn, "unlabeled": m["unlabeled"],
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
            "severity_accuracy": round(sev_acc, 4) if sev_acc is not None else None,
            "severity_checked": m["severity_checked"],
        }
        for k in total:
            total[k] += m[k]

    tp, fp, fn = total["tp"], total["fp"], total["fn"]
    micro_precision = tp / (tp + fp) if (tp + fp) > 0 else None
    micro_recall = tp / (tp + fn) if (tp + fn) > 0 else None
    if micro_precision is not None and micro_recall is not None and (micro_precision + micro_recall) > 0:
        micro_f1 = 2 * micro_precision * micro_recall / (micro_precision + micro_recall)
    else:
        micro_f1 = None
    sev_acc = (total["severity_ok"] / total["severity_checked"]) if total["severity_checked"] > 0 else None

    engine_total = len(engine)
    labeled_total = engine_total - total["unlabeled"]
    unlabeled_rate = (total["unlabeled"] / engine_total) if engine_total > 0 else 0.0

    return {
        "per_rule": out_rules,
        "overall": {
            "tp": tp, "fp": fp, "fn": fn, "unlabeled": total["unlabeled"],
            "precision": round(micro_precision, 4) if micro_precision is not None else None,
            "recall": round(micro_recall, 4) if micro_recall is not None else None,
            "f1": round(micro_f1, 4) if micro_f1 is not None else None,
            "severity_accuracy": round(sev_acc, 4) if sev_acc is not None else None,
        },
        "counts": {
            "engine_findings": engine_total,
            "labeled": labeled_total,
            "unlabeled": total["unlabeled"],
            "unlabeled_rate": round(unlabeled_rate, 4),
            "labeler_additions": len(additions),
        },
    }


def _fmt(x) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def print_report(metrics: dict) -> None:
    print()
    print("=== Per rule ===")
    print(f"{'rule':32s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'unlbl':>5s}  {'P':>5s} {'R':>5s} {'F1':>5s}  {'sev':>5s}")
    for rule, m in metrics["per_rule"].items():
        print(f"{rule:32s} {m['tp']:4d} {m['fp']:4d} {m['fn']:4d} {m['unlabeled']:5d}  "
              f"{_fmt(m['precision']):>5s} {_fmt(m['recall']):>5s} {_fmt(m['f1']):>5s}  {_fmt(m['severity_accuracy']):>5s}")
    print()
    o = metrics["overall"]
    c = metrics["counts"]
    print("=== Overall ===")
    print(f"  engine findings   : {c['engine_findings']}")
    print(f"  labeled           : {c['labeled']}")
    print(f"  unlabeled         : {c['unlabeled']} ({c['unlabeled_rate']*100:.1f}%)")
    print(f"  labeler additions : {c['labeler_additions']}")
    print()
    print(f"  precision : {_fmt(o['precision'])}")
    print(f"  recall    : {_fmt(o['recall'])}")
    print(f"  F1        : {_fmt(o['f1'])}")
    print(f"  severity  : {_fmt(o['severity_accuracy'])}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labeled", required=True, help="Returned CSV from the labeler")
    ap.add_argument("--json", default="", help="Optional: write metrics as JSON to this path")
    args = ap.parse_args()

    path = Path(args.labeled)
    if not path.exists():
        print(f"[FAIL] file not found: {path}", file=sys.stderr)
        return 1

    try:
        rows = _read_csv(path)
    except Exception as e:
        print(f"[FAIL] could not read CSV: {e}", file=sys.stderr)
        return 1

    if not rows:
        print("[FAIL] CSV has no rows", file=sys.stderr)
        return 1

    metrics = compute_metrics(rows)

    c = metrics["counts"]
    if c["labeled"] == 0 and c["labeler_additions"] == 0:
        print("[FAIL] no rows are labeled and no additions were made. "
              "Fill in labeler_correct for engine findings, or add rows for missed findings.",
              file=sys.stderr)
        return 2

    print_report(metrics)

    if args.json:
        Path(args.json).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"Wrote {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())