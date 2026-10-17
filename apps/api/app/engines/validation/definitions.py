"""The catalogue of rules, with their defaults and parameter validation. A rule's current configuration
lives in the database; these are the factory defaults and the schema of what may be changed."""
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.engines.validation.types import SEVERITIES

DISCIPLINES = ("architecture", "structure", "mep", "equipment", "quantity", "general")
METADATA_FIELDS = ("author", "name", "source_system", "change_summary")
STATUSES = ("draft", "in_review", "approved", "issued", "superseded", "rejected")


@dataclass(frozen=True)
class RuleDefinition:
    id: str
    name: str
    description: str
    category: str
    default_severity: str
    default_enabled: bool = True
    default_params: dict[str, Any] = field(default_factory=dict)
    configurable_severity: bool = True
    can_disable: bool = True


def _check_positive(params: dict, key: str, minimum: float = 0.0) -> None:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
        raise ValueError(f"'{key}' must be a number of at least {minimum:g}.")


def _only_keys(params: dict, allowed: set[str]) -> None:
    unknown = set(params) - allowed
    if unknown:
        raise ValueError(f"Unknown parameter {', '.join(sorted(unknown))}. Allowed: {', '.join(sorted(allowed)) or 'none'}.")


def _no_params(params: dict) -> None:
    _only_keys(params, set())


def _max_gap(params: dict) -> None:
    _only_keys(params, {"max_gap"})
    _check_positive(params, "max_gap", 1)


def _required_dependencies(params: dict) -> None:
    _only_keys(params, {"required"})
    required = params.get("required")
    if not isinstance(required, list):
        raise ValueError("'required' must be a list of {discipline, on_discipline} pairs.")
    for item in required:
        if not isinstance(item, dict) or set(item) != {"discipline", "on_discipline"} or \
                item["discipline"] not in DISCIPLINES or item["on_discipline"] not in DISCIPLINES:
            raise ValueError(f"Each entry needs 'discipline' and 'on_discipline', each one of: {', '.join(DISCIPLINES)}.")


def _unreviewed(params: dict) -> None:
    _only_keys(params, {"min_score", "use_impact_severity"})
    _check_positive(params, "min_score", 0)
    if not isinstance(params.get("use_impact_severity"), bool):
        raise ValueError("'use_impact_severity' must be true or false.")


def _clearance(params: dict) -> None:
    _only_keys(params, {"clearance_mm"})
    _check_positive(params, "clearance_mm", 0)


def _mismatch(params: dict) -> None:
    _only_keys(params, {"checks"})
    checks = params.get("checks")
    if not isinstance(checks, list):
        raise ValueError("'checks' must be a list.")
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"name", "left", "right", "tolerance"}:
            raise ValueError("Each check needs 'name', 'left', 'right' and 'tolerance'.")
        if not isinstance(check["name"], str) or not check["name"].strip():
            raise ValueError("A check needs a name.")
        _check_positive(check, "tolerance", 0)
        for side in ("left", "right"):
            ref = check[side]
            if not isinstance(ref, dict) or set(ref) != {"discipline", "tag", "property"} or \
                    ref["discipline"] not in DISCIPLINES or not ref["tag"] or not ref["property"]:
                raise ValueError(f"'{side}' needs a discipline ({', '.join(DISCIPLINES)}), a 'tag' and a 'property'.")


def _metadata(params: dict) -> None:
    _only_keys(params, {"required_fields"})
    fields = params.get("required_fields")
    if not isinstance(fields, list) or any(f not in METADATA_FIELDS for f in fields):
        raise ValueError(f"'required_fields' must be a list of: {', '.join(METADATA_FIELDS)}.")


def _naming(params: dict) -> None:
    _only_keys(params, {"pattern", "check_prefix", "prefixes"})
    try:
        re.compile(params.get("pattern", ""))
    except (re.error, TypeError) as exc:
        raise ValueError(f"'pattern' is not a valid regular expression ({exc}).") from exc
    if not params.get("pattern"):
        raise ValueError("'pattern' is required.")
    if not isinstance(params.get("check_prefix"), bool):
        raise ValueError("'check_prefix' must be true or false.")
    prefixes = params.get("prefixes")
    if not isinstance(prefixes, dict) or any(k not in DISCIPLINES or not isinstance(v, str) or not v
                                             for k, v in prefixes.items()):
        raise ValueError("'prefixes' maps a discipline to its document-number prefix, for example {\"structure\": \"S\"}.")


def _approval(params: dict) -> None:
    _only_keys(params, {"required_status"})
    statuses = params.get("required_status")
    if not isinstance(statuses, list) or not statuses or any(s not in STATUSES for s in statuses):
        raise ValueError(f"'required_status' must be a non-empty list of: {', '.join(STATUSES)}.")


def _policy(params: dict) -> None:
    _only_keys(params, {"blocking_severity"})
    if params.get("blocking_severity") not in SEVERITIES:
        raise ValueError(f"'blocking_severity' must be one of: {', '.join(SEVERITIES)}.")


_CROSS_DOC_COMPARE_FIELDS = ("level", "room", "material")
_CROSS_DOC_DEFAULT_RELATIONSHIPS = (
    "depends_on", "references", "generated_from", "derived_from", "quantity_based_on",
)


def _cross_doc_relationship_types(params: dict) -> None:
    _only_keys(params, {"relationship_types"})
    types_list = params.get("relationship_types")
    if not isinstance(types_list, list) or not types_list:
        raise ValueError("'relationship_types' must be a non-empty list of relationship type names.")
    for item in types_list:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("Each entry in 'relationship_types' must be a non-empty string.")


def _cross_doc_compare(params: dict) -> None:
    _only_keys(params, {"relationship_types", "compare"})
    _cross_doc_relationship_types({"relationship_types": params.get("relationship_types")})
    compare = params.get("compare")
    if not isinstance(compare, list) or not compare:
        raise ValueError(f"'compare' must be a non-empty list of: {', '.join(_CROSS_DOC_COMPARE_FIELDS)}.")
    for name in compare:
        if name not in _CROSS_DOC_COMPARE_FIELDS:
            raise ValueError(f"Unknown comparison field '{name}'. Allowed: {', '.join(_CROSS_DOC_COMPARE_FIELDS)}.")

_VALIDATORS: dict[str, Callable[[dict], None]] = {}


def _rule(definition: RuleDefinition, validator: Callable[[dict], None]) -> RuleDefinition:
    _VALIDATORS[definition.id] = validator
    return definition


RULES: tuple[RuleDefinition, ...] = (
    _rule(RuleDefinition("MISSING_REVISION", "Missing revision",
                         "Every document must have at least one revision.", "revision", "HIGH"), _no_params),
    _rule(RuleDefinition("INVALID_REVISION_SEQUENCE", "Invalid revision sequence",
                         "Revision numbers must not skip more than the allowed gap.", "revision", "LOW",
                         default_params={"max_gap": 1}), _max_gap),
    _rule(RuleDefinition("DUPLICATE_REVISION_CONTENT", "Duplicate revision content",
                         "Two revisions of one document must not have identical content.", "revision", "LOW"), _no_params),
    _rule(RuleDefinition("STALE_DEPENDENCY", "Stale dependency",
                         "A dependent document must be validated against the latest revision of the document it depends on.",
                         "dependency", "HIGH"), _no_params),
    _rule(RuleDefinition("MISSING_DEPENDENCY", "Missing dependency",
                         "Documents of a discipline must depend on the listed discipline when the project has one.",
                         "dependency", "MEDIUM",
                         default_params={"required": [{"discipline": "structure", "on_discipline": "architecture"},
                                                      {"discipline": "mep", "on_discipline": "architecture"},
                                                      {"discipline": "quantity", "on_discipline": "architecture"}]}),
          _required_dependencies),
    _rule(RuleDefinition("UNRESOLVED_REFERENCE", "Unresolved reference",
                         "Elements that say what they are based on must refer to elements that exist in the source documents.",
                         "dependency", "MEDIUM"), _no_params),
    _rule(RuleDefinition("UNREVIEWED_DOWNSTREAM", "Downstream document not reviewed",
                         "A document reached indirectly by a change must be reviewed. The issue takes the impact's severity.",
                         "dependency", "MEDIUM", default_params={"min_score": 25.0, "use_impact_severity": True}),
          _unreviewed),
    _rule(RuleDefinition("SPATIAL_CONFLICT", "Potential spatial conflict",
                         "An element must keep the clearance from an element that changed in a source document.",
                         "consistency", "HIGH", default_params={"clearance_mm": 300.0}), _clearance),
    _rule(RuleDefinition("OUTDATED_REFERENCE", "Information based on changed elements",
                         "Elements based on elements that changed in a source document may be outdated.",
                         "consistency", "MEDIUM"), _no_params),
    _rule(RuleDefinition("PARAMETER_MISMATCH", "Shared parameter mismatch",
                         "Values that appear in two documents must agree within a tolerance.", "consistency", "HIGH",
                         default_params={"checks": [{
                             "name": "Room 204 floor area",
                             "left": {"discipline": "quantity", "tag": "QTO-ROOM-204-AREA", "property": "Quantity"},
                             "right": {"discipline": "architecture", "tag": "204",
                                       "property": "Qto_SpaceBaseQuantities.NetFloorArea"},
                             "tolerance": 0.01}]}), _mismatch),
    _rule(RuleDefinition("MISSING_METADATA", "Missing metadata",
                         "Required document information must be filled in.", "metadata", "MEDIUM",
                         default_params={"required_fields": ["author"]}), _metadata),
    _rule(RuleDefinition("NAMING_CONVENTION", "Naming convention",
                         "Document numbers must follow the project's naming convention.", "naming", "MEDIUM",
                         default_params={"pattern": r"^[A-Z]{1,2}-\d{3}[A-Z]?$", "check_prefix": True,
                                         "prefixes": {"architecture": "A", "structure": "S", "mep": "M",
                                                      "equipment": "E", "quantity": "Q", "general": "G"}}), _naming),
    _rule(RuleDefinition("APPROVAL_REQUIRED", "Approval required",
                         "The current revision must have one of the required statuses before it can be issued.",
                         "approval", "HIGH", default_params={"required_status": ["approved", "issued"]}), _approval),
    _rule(RuleDefinition("CROSS_DOC_TAG_MISSING", "Element missing from dependent document",
                         "An element present in a provider document must also appear in the document that depends on it. "
                         "Off by default: enable per project through a quality profile.",
                         "consistency", "MEDIUM", default_enabled=False,
                         default_params={"relationship_types": list(_CROSS_DOC_DEFAULT_RELATIONSHIPS)}),
          _cross_doc_relationship_types),
    _rule(RuleDefinition("CROSS_DOC_PROPERTY_DIVERGENCE", "Element property disagrees across documents",
                         "An element tag shared between two linked documents must agree on level, room and material. "
                         "Off by default: enable per project through a quality profile.",
                         "consistency", "MEDIUM", default_enabled=False,
                         default_params={"relationship_types": list(_CROSS_DOC_DEFAULT_RELATIONSHIPS),
                                         "compare": list(_CROSS_DOC_COMPARE_FIELDS)}),
          _cross_doc_compare),
    _rule(RuleDefinition("CROSS_DOC_TAG_UNEXPECTED", "Unexpected element in dependent document",
                         "A dependent document contains a tag the provider document does not have. "
                         "Off by default: some dependent documents legitimately add elements.",
                         "consistency", "LOW", default_enabled=False,
                         default_params={"relationship_types": list(_CROSS_DOC_DEFAULT_RELATIONSHIPS)}),
          _cross_doc_relationship_types),    _rule(RuleDefinition("READINESS_POLICY", "Release policy",
                         "Open issues at or above this severity block the release. Lower ones are warnings.",
                         "policy", "HIGH", default_params={"blocking_severity": "HIGH"},
                         configurable_severity=False, can_disable=False), _policy),
)
BY_ID = {r.id: r for r in RULES}


def validate_configuration(rule_id: str, severity: str | None, params: dict[str, Any] | None) -> None:
    """Raises ValueError with a user-facing message when a proposed configuration is not acceptable."""
    if rule_id not in BY_ID:
        raise ValueError(f"Unknown rule {rule_id}.")
    if severity is not None and severity not in SEVERITIES:
        raise ValueError(f"Severity must be one of: {', '.join(SEVERITIES)}.")
    if params is not None:
        _VALIDATORS[rule_id](params)
