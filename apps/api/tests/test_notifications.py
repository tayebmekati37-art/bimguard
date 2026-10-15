from app.models.user import Role, User
from app.services import notifications as service


def _find_user(session_factory, email: str) -> User:
    with session_factory() as db:
        u = db.query(User).filter(User.email == email).one()
        return u


def test_list_requires_auth(client):
    r = client.get("/notifications")
    assert r.status_code == 401


def test_unread_count_starts_zero(client, auth):
    r = client.get("/notifications/unread-count", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    assert r.json() == {"count": 0}


def test_notification_list_empty(client, auth):
    r = client.get("/notifications", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_create_and_list_notification(client, auth, session_factory):
    engineer = _find_user(session_factory, "engineer@test.local")
    with session_factory() as db:
        service.notify(db, user_id=engineer.id, kind="test.hello",
                       title="Hello", body="world", link="/dashboard")
        db.commit()

    r = client.get("/notifications", headers=auth("engineer"))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "test.hello"
    assert items[0]["title"] == "Hello"
    assert items[0]["read_at"] is None


def test_unread_count_reflects_notifications(client, auth, session_factory):
    engineer = _find_user(session_factory, "engineer@test.local")
    with session_factory() as db:
        for i in range(3):
            service.notify(db, user_id=engineer.id, kind="test", title=f"n{i}")
        db.commit()

    r = client.get("/notifications/unread-count", headers=auth("engineer"))
    assert r.json() == {"count": 3}


def test_mark_read_sets_read_at(client, auth, session_factory):
    engineer = _find_user(session_factory, "engineer@test.local")
    with session_factory() as db:
        n = service.notify(db, user_id=engineer.id, kind="test", title="t")
        db.commit()
        nid = n.id

    r = client.post(f"/notifications/{nid}/read", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    assert r.json()["read_at"] is not None

    r = client.get("/notifications/unread-count", headers=auth("engineer"))
    assert r.json() == {"count": 0}


def test_cannot_read_other_users_notification(client, auth, session_factory):
    admin = _find_user(session_factory, "admin@test.local")
    with session_factory() as db:
        n = service.notify(db, user_id=admin.id, kind="test", title="private")
        db.commit()
        nid = n.id

    r = client.post(f"/notifications/{nid}/read", headers=auth("engineer"))
    assert r.status_code == 404


def test_mark_all_read(client, auth, session_factory):
    engineer = _find_user(session_factory, "engineer@test.local")
    with session_factory() as db:
        for i in range(4):
            service.notify(db, user_id=engineer.id, kind="test", title=f"n{i}")
        db.commit()

    r = client.post("/notifications/read-all", headers=auth("engineer"))
    assert r.status_code == 200
    assert r.json() == {"count": 0}

    r = client.get("/notifications?unread_only=true", headers=auth("engineer"))
    assert r.json()["total"] == 0


def test_blocked_validation_notifies_coordinators(client, auth, session_factory):
    # Engineer creates a project, adds a document with no revision → validation is BLOCKED
    p = client.post("/projects", json={"name": "Notify Test", "client": "C"},
                    headers=auth("bim_coordinator"))
    assert p.status_code == 201, p.text
    pid = p.json()["id"]

    client.post(f"/projects/{pid}/documents", headers=auth("engineer"),
                json={"document_number": "A-1", "name": "x", "discipline": "architecture"})

    rv = client.post(f"/projects/{pid}/validate", headers=auth("engineer"))
    assert rv.status_code == 201, rv.text

    if rv.json()["status"] == "BLOCKED":
        coord = client.get("/notifications/unread-count", headers=auth("bim_coordinator"))
        assert coord.json()["count"] >= 1

        listing = client.get("/notifications", headers=auth("bim_coordinator"))
        kinds = [i["kind"] for i in listing.json()["items"]]
        assert "validation.blocked" in kinds

        # actor should not be notified
        eng = client.get("/notifications", headers=auth("engineer"))
        kinds_eng = [i["kind"] for i in eng.json()["items"]]
        assert "validation.blocked" not in kinds_eng