"""Tests for scripts/eval-from-labels.py (M28)."""
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "eval_from_labels",
    Path(__file__).resolve().parent.parent.parent / "scripts" / "eval-from-labels.py",
)
eval_from_labels = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_from_labels)


def _row(fid="", rule="", doc="", correct="", sev_ok="", note=""):
    return {
        "finding_id": fid, "rule_id": rule, "document_number": doc,
        "element_tag": "", "severity": "HIGH", "title": "", "message": "",
        "recommended_action": "", "labeler_correct": correct,
        "labeler_severity_ok": sev_ok, "labeler_note": note,
    }


def test_all_correct_yields_perfect_metrics():
    rows = [
        _row("f1", "MISSING_REVISION", "G-100", "Y"),
        _row("f2", "MISSING_REVISION", "G-101", "Y"),
        _row("f3", "STALE_DEPENDENCY", "S-201", "Y"),
    ]
    m = eval_from_labels.compute_metrics(rows)
    assert m["overall"]["precision"] == 1.0
    assert m["overall"]["recall"] == 1.0
    assert m["overall"]["f1"] == 1.0
    assert m["counts"]["engine_findings"] == 3
    assert m["counts"]["labeled"] == 3


def test_false_positive_reduces_precision():
    rows = [
        _row("f1", "MISSING_REVISION", "G-100", "Y"),
        _row("f2", "MISSING_REVISION", "G-101", "Y"),
        _row("f3", "MISSING_REVISION", "G-102", "N"),  # false positive
    ]
    m = eval_from_labels.compute_metrics(rows)
    assert m["per_rule"]["MISSING_REVISION"]["tp"] == 2
    assert m["per_rule"]["MISSING_REVISION"]["fp"] == 1
    assert m["per_rule"]["MISSING_REVISION"]["precision"] == round(2/3, 4)
    assert m["per_rule"]["MISSING_REVISION"]["recall"] == 1.0


def test_labeler_addition_is_false_negative():
    rows = [
        _row("f1", "STALE_DEPENDENCY", "S-201", "Y"),
        # Addition: engine missed a finding
        _row("", "STALE_DEPENDENCY", "S-202", note="engine missed this"),
    ]
    m = eval_from_labels.compute_metrics(rows)
    assert m["per_rule"]["STALE_DEPENDENCY"]["tp"] == 1
    assert m["per_rule"]["STALE_DEPENDENCY"]["fn"] == 1
    assert m["per_rule"]["STALE_DEPENDENCY"]["recall"] == 0.5
    assert m["counts"]["labeler_additions"] == 1


def test_unlabeled_rows_excluded_from_metrics():
    rows = [
        _row("f1", "STALE_DEPENDENCY", "S-201", "Y"),
        _row("f2", "STALE_DEPENDENCY", "S-202", ""),  # not labeled
        _row("f3", "STALE_DEPENDENCY", "S-203", ""),  # not labeled
    ]
    m = eval_from_labels.compute_metrics(rows)
    assert m["per_rule"]["STALE_DEPENDENCY"]["tp"] == 1
    assert m["per_rule"]["STALE_DEPENDENCY"]["unlabeled"] == 2
    assert m["counts"]["labeled"] == 1
    assert m["counts"]["unlabeled"] == 2
    assert m["counts"]["unlabeled_rate"] == round(2/3, 4)


def test_yes_no_normalization():
    """Y/YeS/TRUE/1 should all be True; N/NO/false/0 all False."""
    rows = [
        _row("f1", "R1", "D1", "yes"),
        _row("f2", "R1", "D2", "TRUE"),
        _row("f3", "R1", "D3", "1"),
        _row("f4", "R1", "D4", "no"),
        _row("f5", "R1", "D5", "false"),
        _row("f6", "R1", "D6", "0"),
    ]
    m = eval_from_labels.compute_metrics(rows)
    assert m["per_rule"]["R1"]["tp"] == 3
    assert m["per_rule"]["R1"]["fp"] == 3


def test_severity_accuracy_only_counts_when_checked():
    rows = [
        _row("f1", "R", "D1", "Y", sev_ok="Y"),
        _row("f2", "R", "D2", "Y", sev_ok="N"),
        _row("f3", "R", "D3", "Y", sev_ok=""),  # not judged
    ]
    m = eval_from_labels.compute_metrics(rows)
    assert m["per_rule"]["R"]["severity_checked"] == 2
    assert m["per_rule"]["R"]["severity_accuracy"] == 0.5


def test_empty_csv_returns_zero_metrics():
    m = eval_from_labels.compute_metrics([])
    assert m["counts"]["engine_findings"] == 0
    assert m["counts"]["labeler_additions"] == 0


def test_roundtrip_csv(tmp_path):
    """Write a realistic CSV, read it back, verify metrics."""
    path = tmp_path / "labeled.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "finding_id", "rule_id", "document_number", "element_tag",
            "severity", "title", "message", "recommended_action",
            "labeler_correct", "labeler_severity_ok", "labeler_note",
        ])
        w.writeheader()
        w.writerow(_row("f1", "MISSING_REVISION", "G-100", "Y", "Y"))
        w.writerow(_row("f2", "MISSING_REVISION", "G-101", "Y", "N"))
        w.writerow(_row("f3", "MISSING_REVISION", "G-102", "N"))
        w.writerow(_row("", "STALE_DEPENDENCY", "S-201", note="engine missed"))

    rows = eval_from_labels._read_csv(path)
    m = eval_from_labels.compute_metrics(rows)

    assert m["per_rule"]["MISSING_REVISION"]["tp"] == 2
    assert m["per_rule"]["MISSING_REVISION"]["fp"] == 1
    assert m["per_rule"]["MISSING_REVISION"]["severity_accuracy"] == 0.5
    assert m["per_rule"]["STALE_DEPENDENCY"]["fn"] == 1