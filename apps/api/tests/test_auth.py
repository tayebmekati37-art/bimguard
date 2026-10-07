def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_login_success_and_me(client, auth):
    r = client.get("/auth/me", headers=auth("engineer"))
    assert r.status_code == 200 and r.json()["role"] == "engineer"


def test_login_wrong_password(client):
    r = client.post("/auth/login", data={"username": "engineer@test.local", "password": "wrong"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_login_is_audited(client, auth):
    auth("admin")
    logs = client.get("/audit-logs", headers=auth("admin")).json()
    assert any(item["action"] == "auth.login" for item in logs["items"])
