"""Tests for scripts/export-for-labeling.py (M28).

Does not hit a running API. Tests the row/CSV building logic, which is
the part that can silently corrupt labels if wrong.
"""
import csv
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "export_for_labeling",
    Path(__file__).resolve().parent.parent.parent / "scripts" / "export-for-labeling.py",
)
export_for_labeling = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_for_labeling)


def _issue(**overrides):
    base = {
        "id": "issue-uuid-1",
        "rule_id": "STALE_DEPENDENCY",
        "document_number": "S-201",
        "element_tag": "",
        "severity": "HIGH",
        "title": "Stale dependency",
        "message": "S-201 v8 is stale against A-101 v13.",
        "recommended_action": "Review S-201 against A-101 v13.",
    }
    base.update(overrides)
    return base


def test_build_row_maps_all_fields():
    row = export_for_labeling.build_row(_issue())
    assert row["finding_id"] == "issue-uuid-1"
    assert row["rule_id"] == "STALE_DEPENDENCY"
    assert row["document_number"] == "S-201"
    assert row["severity"] == "HIGH"
    assert row["labeler_correct"] == ""
    assert row["labeler_severity_ok"] == ""
    assert row["labeler_note"] == ""


def test_build_row_handles_missing_fields_gracefully():
    row = export_for_labeling.build_row({"id": "x"})
    assert row["finding_id"] == "x"
    assert row["rule_id"] == ""
    assert row["document_number"] == ""


def test_write_csv_has_bom_and_correct_header(tmp_path):
    path = tmp_path / "out.csv"
    export_for_labeling.write_csv(path, [export_for_labeling.build_row(_issue())])
    raw = path.read_bytes()
    assert raw[0:3] == b"\xef\xbb\xbf", "CSV must have UTF-8 BOM so Excel opens correctly"
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["finding_id"] == "issue-uuid-1"
    assert rows[0]["rule_id"] == "STALE_DEPENDENCY"
    # Labeler columns must be empty in the exported file
    assert rows[0]["labeler_correct"] == ""
    assert rows[0]["labeler_severity_ok"] == ""
    assert rows[0]["labeler_note"] == ""


def test_write_csv_preserves_all_engine_columns(tmp_path):
    path = tmp_path / "out.csv"
    issue = _issue(element_tag="W-204", severity="CRITICAL")
    export_for_labeling.write_csv(path, [export_for_labeling.build_row(issue)])
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["element_tag"] == "W-204"
    assert rows[0]["severity"] == "CRITICAL"
    # Ensure the exact header order matches COLUMNS
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
    assert header == export_for_labeling.COLUMNS