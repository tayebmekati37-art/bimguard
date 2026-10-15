# Readiness reports

## Goals

- One report, three formats: JSON, CSV, PDF. Identical data in each.
- Built entirely from existing engine output. No new analysis.
- Works for any project, including one that has never been validated.

## Endpoints

- `GET /projects/{id}/reports/readiness.json` - structured data
- `GET /projects/{id}/reports/readiness.csv` - spreadsheet
- `GET /projects/{id}/reports/readiness.pdf` - printable

All three are auth-protected by the standard current-user dependency.

## Data source

`app/services/reports.py:build_readiness_report(db, project)` builds one
dict from `health_service.project_health` and the latest validation run.
The dict is the single source of truth; exporters only serialize it.

## Schema version

The JSON contains `schema_version: 1`. Bump it if the shape changes.

## CSV shape

Metadata block, blank line, header row, one row per issue.
Columns: Severity, Document, Element, Rule ID, Title, Status, Message,
Recommended action, Acknowledged by, Note. UTF-8 with BOM for Excel.

## PDF shape

Built with reportlab. A4, 18mm margins. Title, summary table, issue
table, document health table. Paginated.

## Why reportlab

Pure Python, no system dependencies on Windows (weasyprint needs GTK).

## Adding a new format

1. Add `to_<format>(report) -> bytes` in `report_export.py`.
2. Add an endpoint in `app/api/reports.py`.
3. Add a test in `tests/test_reports.py` checking media type and magic bytes.