from collections.abc import Iterable, Mapping

from app.engines.validation.definitions import BY_ID, RULES
from app.engines.validation.rules import CHECKS, _Context
from app.engines.validation.types import Finding, Readiness, RuleConfig, Snapshot, severity_rank


def default_configs() -> dict[str, RuleConfig]:
    return {r.id: RuleConfig(r.id, r.default_enabled, r.default_severity, dict(r.default_params)) for r in RULES}


def run_rules(snapshot: Snapshot, configs: Mapping[str, RuleConfig] | None = None) -> list[Finding]:
    """Runs every enabled rule. Deterministic: the same snapshot and configuration give the same ordered findings."""
    configs = configs or default_configs()
    ctx = _Context(snapshot)
    findings: list[Finding] = []
    for definition in RULES:
        check = CHECKS.get(definition.id)
        config = configs.get(definition.id)
        if check is None or config is None or not config.enabled:
            continue
        findings.extend(check(ctx, config))
    return sorted(findings, key=lambda f: (-severity_rank(f.severity), f.document_number, f.rule_id, f.element_tag, f.subject))


def blocking_severity(configs: Mapping[str, RuleConfig] | None) -> str:
    config = (configs or {}).get("READINESS_POLICY")
    return config.params.get("blocking_severity", "HIGH") if config else BY_ID["READINESS_POLICY"].default_params["blocking_severity"]


def assess(findings: Iterable[Finding], acknowledged: set[str], blocking: str) -> Readiness:
    """BLOCKED when an open issue is at or above the blocking severity. Critical issues can never be acknowledged."""
    open_by_severity: dict[str, int] = {}
    by_rule: dict[str, int] = {}
    open_count = acknowledged_count = blocking_count = 0
    for f in findings:
        by_rule[f.rule_id] = by_rule.get(f.rule_id, 0) + 1
        if f.fingerprint in acknowledged and f.severity != "CRITICAL":
            acknowledged_count += 1
            continue
        open_count += 1
        open_by_severity[f.severity] = open_by_severity.get(f.severity, 0) + 1
        if severity_rank(f.severity) >= severity_rank(blocking):
            blocking_count += 1
    status = "BLOCKED" if blocking_count else "READY_WITH_WARNINGS" if open_count else "READY"
    ordered = {s: open_by_severity[s] for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW") if s in open_by_severity}
    return Readiness(status, open_count, acknowledged_count, blocking_count, ordered, by_rule)
