"""Mechanical proof that every route requires authentication.

If someone adds an endpoint in a future milestone and forgets
Depends(get_current_user), this test fails loudly.
"""
from fastapi.routing import APIRoute

from app.api.deps import get_current_user
from app.main import app

# Routes that are intentionally public.
_ALLOWLIST = {
    ("POST", "/auth/login"),
    ("GET", "/health"),
}


def _depends_on_auth(dependant) -> bool:
    """Walk the dependency tree; True if get_current_user appears anywhere."""
    if dependant.call is get_current_user:
        return True
    return any(_depends_on_auth(sub) for sub in dependant.dependencies)


def test_every_api_route_requires_auth():
    offenders: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods):
            if (method, route.path) in _ALLOWLIST:
                continue
            if not _depends_on_auth(route.dependant):
                offenders.append((method, route.path))
    assert not offenders, (
        f"Endpoints reachable without auth: {offenders}. "
        "Add Depends(get_current_user) or a require_roles(...) guard, or add to _ALLOWLIST if intentional."
    )


def test_health_is_public_by_design():
    """A canary: if /health ever gets protected, this test flags it so we
    can decide whether that was intentional."""
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == "/health":
            assert not _depends_on_auth(route.dependant), (
                "/health is protected. Container healthchecks will fail unless "
                "this was intentional. Remove it from _ALLOWLIST if so."
            )
            return
    raise AssertionError("/health route not found")