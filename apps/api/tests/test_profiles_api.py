from app.engines.profiles.registry import default_dir
from app.models.profile import ProfileActivation


def test_list_profiles_requires_auth(client):
    r = client.get("/profiles")
    assert r.status_code == 401


def test_list_profiles_returns_bundled_sample(client, auth):
    r = client.get("/profiles", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    ids = [p["id"] for p in r.json()]
    assert "jp-bimcim-v1" in ids


def test_get_profile_detail(client, auth):
    r = client.get("/profiles/jp-bimcim-v1", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "jp-bimcim-v1"
    assert body["illustrative"] is True
    assert "STALE_DEPENDENCY" in body["rules"]
    assert body["rules"]["STALE_DEPENDENCY"]["severity"] == "CRITICAL"


def test_get_unknown_profile_404(client, auth):
    r = client.get("/profiles/does-not-exist", headers=auth("engineer"))
    assert r.status_code == 404


def test_current_profile_without_activation(client, auth, project):
    r = client.get(f"/projects/{project['id']}/profile", headers=auth("engineer"))
    assert r.status_code == 200
    body = r.json()
    assert body["profile_id"] is None


def test_activate_and_read_and_deactivate(client, auth, project, session_factory):
    r = client.put(
        f"/projects/{project['id']}/profile",
        headers=auth("bim_coordinator"),
        json={"profile_id": "jp-bimcim-v1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["profile_id"] == "jp-bimcim-v1"

    r = client.get(f"/projects/{project['id']}/profile", headers=auth("engineer"))
    assert r.json()["profile_id"] == "jp-bimcim-v1"

    with session_factory() as db:
        row = db.get(ProfileActivation, project["id"])
        assert row is not None and row.profile_id == "jp-bimcim-v1"

    r = client.delete(f"/projects/{project['id']}/profile", headers=auth("bim_coordinator"))
    assert r.status_code == 200
    assert r.json()["profile_id"] is None

    with session_factory() as db:
        assert db.get(ProfileActivation, project["id"]) is None


def test_engineer_cannot_activate(client, auth, project):
    r = client.put(
        f"/projects/{project['id']}/profile",
        headers=auth("engineer"),
        json={"profile_id": "jp-bimcim-v1"},
    )
    assert r.status_code == 403


def test_activate_unknown_profile_404(client, auth, project):
    r = client.put(
        f"/projects/{project['id']}/profile",
        headers=auth("bim_coordinator"),
        json={"profile_id": "does-not-exist"},
    )
    assert r.status_code == 404


def test_activation_changes_run_config(client, auth, project, session_factory):
    """Activating a profile changes the effective config used by the next run."""
    from app.services import validation as v

    with session_factory() as db:
        before = v.rule_configs(db, project["id"])
        assert before["STALE_DEPENDENCY"].severity == "HIGH"

    r = client.put(
        f"/projects/{project['id']}/profile",
        headers=auth("bim_coordinator"),
        json={"profile_id": "jp-bimcim-v1"},
    )
    assert r.status_code == 200

    with session_factory() as db:
        after = v.rule_configs(db, project["id"])
        assert after["STALE_DEPENDENCY"].severity == "CRITICAL"

    # Deactivate, confirm we are back to the DB override
    client.delete(f"/projects/{project['id']}/profile", headers=auth("bim_coordinator"))
    with session_factory() as db:
        restored = v.rule_configs(db, project["id"])
        assert restored["STALE_DEPENDENCY"].severity == "HIGH"