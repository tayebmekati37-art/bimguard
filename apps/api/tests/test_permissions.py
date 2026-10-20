from app.services.permissions import ROLE_CAPABILITIES, capabilities_for


def test_permissions_endpoint_requires_auth(client):
    r = client.get("/me/permissions")
    assert r.status_code == 401


def test_permissions_returns_role_and_capabilities(client, auth):
    r = client.get("/me/permissions", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "engineer"
    assert "capabilities" in body
    assert body["capabilities"]["view_projects"] is True
    assert body["capabilities"]["edit_documents"] is True
    assert body["capabilities"]["admin_backup"] is False


def test_permissions_for_every_role(client, auth):
    for role in ("admin", "bim_coordinator", "engineer", "reviewer", "viewer"):
        r = client.get("/me/permissions", headers=auth(role))
        assert r.status_code == 200, f"{role}: {r.text}"
        assert r.json()["role"] == role


def test_admin_has_every_capability():
    admin = capabilities_for("admin")
    assert all(admin.values()), admin


def test_viewer_has_no_write_capabilities():
    viewer = capabilities_for("viewer")
    write_caps = {
        "edit_documents", "change_status", "run_validation", "run_impact",
        "acknowledge_issues", "manage_projects", "delete_projects",
        "activate_profile", "read_audit", "admin_backup",
    }
    for cap in write_caps:
        assert viewer[cap] is False, f"viewer should not have {cap}"


def test_only_admin_can_backup():
    for role in ROLE_CAPABILITIES:
        caps = capabilities_for(role)
        assert caps["admin_backup"] is (role == "admin"), role


def test_unknown_role_gets_all_false():
    caps = capabilities_for("not-a-real-role")
    assert all(v is False for v in caps.values())


def test_capabilities_are_copied_not_shared():
    a = capabilities_for("admin")
    a["admin_backup"] = False
    b = capabilities_for("admin")
    assert b["admin_backup"] is True  # original untouched