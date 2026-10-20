"""Canonical capability map.

Single source of truth for what each role can do. The API exposes this at
GET /me/permissions so the frontend can hide controls the backend would
reject anyway. Every capability here mirrors a `require_roles(...)` guard
somewhere in app/api.
"""
from __future__ import annotations


_CAPS = (
    "view_projects",
    "edit_documents",
    "change_status",
    "run_validation",
    "run_impact",
    "acknowledge_issues",
    "manage_projects",
    "delete_projects",
    "activate_profile",
    "read_audit",
    "admin_backup",
)

_ALL_FALSE = {c: False for c in _CAPS}

ROLE_CAPABILITIES: dict[str, dict[str, bool]] = {
    "admin": {
        "view_projects": True, "edit_documents": True, "change_status": True,
        "run_validation": True, "run_impact": True, "acknowledge_issues": True,
        "manage_projects": True, "delete_projects": True,
        "activate_profile": True, "read_audit": True, "admin_backup": True,
    },
    "bim_coordinator": {
        "view_projects": True, "edit_documents": True, "change_status": True,
        "run_validation": True, "run_impact": True, "acknowledge_issues": True,
        "manage_projects": True, "delete_projects": False,
        "activate_profile": True, "read_audit": True, "admin_backup": False,
    },
    "engineer": {
        "view_projects": True, "edit_documents": True, "change_status": True,
        "run_validation": True, "run_impact": True, "acknowledge_issues": False,
        "manage_projects": False, "delete_projects": False,
        "activate_profile": False, "read_audit": False, "admin_backup": False,
    },
    "reviewer": {
        "view_projects": True, "edit_documents": False, "change_status": True,
        "run_validation": True, "run_impact": True, "acknowledge_issues": True,
        "manage_projects": False, "delete_projects": False,
        "activate_profile": False, "read_audit": True, "admin_backup": False,
    },
    "viewer": dict(_ALL_FALSE, view_projects=True),
}


def capabilities_for(role_value: str) -> dict[str, bool]:
    """Return a copy of the capability map. Unknown roles get viewer defaults."""
    return dict(ROLE_CAPABILITIES.get(role_value, _ALL_FALSE))