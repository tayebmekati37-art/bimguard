"""RBAC matrix: every (route, method, role) with its expected auth decision.

Two mechanisms protect the boundary:

1. `rbac_matrix.json` records the current decision for every combination.
   Any change to a role guard makes this drift; the test fails with a diff.
2. A hardcoded small set of admin-only and public routes that must always
   behave as documented, even if the fixture is regenerated.

The fixture is intentionally regenerable, but regenerating it forces a
reviewer to see the diff. If you change a role boundary, delete the
fixture, run the tests, and commit the new one.
"""
import json
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from app.main import app


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "rbac_matrix.json"
ROLES = ["admin", "bim_coordinator", "engineer", "reviewer", "viewer"]
PUBLIC_ROUTES = {("POST", "/auth/login"), ("GET", "/health")}
# Excluded because testing it revokes the cached token mid-run.
EXCLUDE_FROM_MATRIX = {("POST", "/auth/logout")}
DUMMY_ID = "00000000-0000-0000-0000-000000000000"
ALLOWED_STATUSES = {200, 201, 202, 204, 400, 404, 405, 409, 422}


def _path_with_dummy_id(path: str) -> str:
    """Replace every {param} with a UUID-shaped dummy."""
    return re.sub(r"\{[^}]+\}", DUMMY_ID, path)


def _discover_routes():
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            yield method, route.path


def _classify(status: int, authenticated: bool) -> str:
    if not authenticated:
        return f"anon-{status}"
    if status == 401:
        return "role-401-unexpected"
    if status == 403:
        return "role-403"
    if status in ALLOWED_STATUSES:
        return "role-allowed"
    return f"role-error-{status}"


@pytest.fixture
def tokens(client, auth):
    """One valid token per role, computed once per test."""
    return {role: auth(role) for role in ROLES}


def _hit_all(client, tokens) -> dict[str, str]:
    actual: dict[str, str] = {}
    for method, path in _discover_routes():
        if (method, path) in EXCLUDE_FROM_MATRIX:
            continue
        url = _path_with_dummy_id(path)
        key_base = f"{method} {path}"

        if (method, path) in PUBLIC_ROUTES:
            r = client.request(method, url)
            actual[f"{key_base} [anon]"] = f"public-{r.status_code}"
            continue

        # Unauthenticated
        r = client.request(method, url)
        actual[f"{key_base} [anon]"] = _classify(r.status_code, authenticated=False)

        # Authenticated, one request per role
        for role, headers in tokens.items():
            r = client.request(method, url, headers=headers)
            actual[f"{key_base} [{role}]"] = _classify(r.status_code, authenticated=True)
    return actual


def test_rbac_matrix(client, tokens):
    """Assert the current auth boundary matches the recorded fixture."""
    actual = _hit_all(client, tokens)

    if not FIXTURE.exists():
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(
            json.dumps(actual, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pytest.skip(f"Created {FIXTURE.name}. Review the diff and rerun.")

    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))

    mismatches: list[str] = []
    for key in sorted(set(expected) | set(actual)):
        exp = expected.get(key)
        act = actual.get(key)
        if exp != act:
            mismatches.append(f"{key}: expected {exp!r}, got {act!r}")

    if mismatches:
        msg = "RBAC drift detected:\n" + "\n".join(mismatches[:30])
        if len(mismatches) > 30:
            msg += f"\n... and {len(mismatches) - 30} more"
        msg += (
            "\n\nIf the change is intentional, delete "
            "tests/fixtures/rbac_matrix.json and rerun to regenerate."
        )
        pytest.fail(msg)


def test_fixture_has_no_unexpected_classifications():
    """No route may return a 5xx or an unauthenticated 401 slip through."""
    if not FIXTURE.exists():
        pytest.skip("No fixture yet")
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bad = {k: v for k, v in data.items() if "unexpected" in v or "-error-" in v}
    if bad:
        snippet = json.dumps(bad, indent=2)
        if len(snippet) > 2000:
            snippet = snippet[:2000] + "\n..."
        pytest.fail(
            "Fix these routes before committing the fixture (they returned 5xx "
            "or otherwise unexpected status):\n" + snippet
        )


def test_fixture_covers_all_routes():
    """If a new route is added, the fixture must be updated to include it."""
    if not FIXTURE.exists():
        pytest.skip("No fixture yet")
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture_routes: set[tuple[str, str]] = set()
    for key in data:
        method, rest = key.split(" ", 1)
        path = rest.rsplit(" [", 1)[0]
        fixture_routes.add((method, path))
    discovered = {
        (m, p) for m, p in _discover_routes() if (m, p) not in EXCLUDE_FROM_MATRIX
    }
    missing = discovered - fixture_routes
    assert not missing, (
        f"Routes present in the app but missing from the fixture: {missing}\n"
        "Delete tests/fixtures/rbac_matrix.json and rerun to regenerate."
    )


def test_known_admin_routes_reject_non_admin(client, tokens):
    """Belt-and-suspenders: these specific routes MUST reject non-admin.

    Even if the fixture is regenerated with wrong values, this test catches
    it. Only list routes whose correct behaviour is unambiguous.
    """
    admin_only = {
        ("POST", "/admin/backup"),
        ("PATCH", "/rules/{rule_id}"),
        ("POST", "/rules/{rule_id}/reset"),
    }
    for method, path in admin_only:
        url = _path_with_dummy_id(path)
        for role in ROLES:
            if role == "admin":
                continue
            r = client.request(method, url, headers=tokens[role])
            assert r.status_code == 403, (
                f"{method} {path} should reject {role}, got {r.status_code}"
            )


def test_single_tenant_scope_is_documented():
    """The deployment doc must state the single-tenant boundary explicitly.

    This is what protects against a future contributor assuming BIMGuard is
    meant to be multi-tenant and quietly adding a tenant_id column. The doc
    is the contract.
    """
    doc = (
        Path(__file__).resolve().parent.parent.parent
        / "docs"
        / "architecture"
        / "deployment.md"
    )
    if not doc.exists():
        pytest.skip("deployment.md not present")
    text = doc.read_text(encoding="utf-8").lower()
    assert (
        "single-tenant" in text or "single tenant" in text
    ), "deployment.md must document the single-tenant boundary"