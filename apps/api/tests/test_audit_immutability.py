"""Grep-based proof that AuditLog is write-once.

The audit service is the only code allowed to write AuditLog rows, and
nothing outside it may delete or update them. If a future change breaks
this invariant, this test fails.
"""
import re
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"
AUDIT_SERVICE = APP_ROOT / "services" / "audit.py"

_FORBIDDEN = re.compile(
    r"\bAuditLog\b.*\.delete\(|db\.delete\(\s*AuditLog|delete\(\s*AuditLog\b|AuditLog\b.*\.update\(",
)


def _python_files():
    return (p for p in APP_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def test_only_audit_service_constructs_auditlog():
    offenders: list[tuple[str, int, str]] = []
    for path in _python_files():
        if path == AUDIT_SERVICE:
            continue
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            # Only flag actual constructions, not imports
            if re.search(r"\bAuditLog\s*\(", line) and "import" not in line and "class AuditLog" not in line:
                offenders.append((str(path.relative_to(APP_ROOT)), i, line.strip()))
    assert not offenders, (
        "AuditLog is constructed outside services/audit.py. "
        "Route every write through app.services.audit.record(). "
        f"Offenders: {offenders}"
    )


def test_nothing_deletes_or_updates_auditlog():
    offenders: list[tuple[str, int, str]] = []
    for path in _python_files():
        if path == AUDIT_SERVICE:
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            if _FORBIDDEN.search(line):
                offenders.append((str(path.relative_to(APP_ROOT)), i, line.strip()))
    assert not offenders, (
        "AuditLog is deleted or updated outside services/audit.py. "
        "The audit log is write-once by design. "
        f"Offenders: {offenders}"
    )


def test_audit_service_has_record_function():
    text = AUDIT_SERVICE.read_text(encoding="utf-8")
    assert "def record(" in text, "services/audit.py must expose record()"