import os

os.environ["DATABASE_URL"] = "sqlite://"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.api.deps import get_session_factory  # noqa: E402
from app.db.session import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import Role, User  # noqa: E402

PASSWORD = "pw-test-123"
IFC_V1 = b"ISO-10303-21;\nHEADER;\nFILE_NAME('a.ifc');\nENDSEC;\nDATA;\n#1=IFCWALL('w1');\nENDSEC;\nEND-ISO-10303-21;\n"
IFC_V2 = IFC_V1.replace(b"w1", b"w1-moved")


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        for role in Role:
            db.add(User(email=f"{role.value}@test.local", full_name=role.value.title(), role=role,
                        password_hash=hash_password(PASSWORD)))
        db.commit()
    yield factory
    engine.dispose()


@pytest.fixture()
def client(session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path / "storage"))

    def override():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def auth(client):
    def make(role: str = "engineer") -> dict:
        r = client.post("/auth/login", data={"username": f"{role}@test.local", "password": PASSWORD})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return make


@pytest.fixture()
def project(client, auth):
    r = client.post("/projects", json={"name": "Factory Expansion - Building A", "client": "Demo Client"},
                    headers=auth("bim_coordinator"))
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def document(client, auth, project):
    r = client.post(f"/projects/{project['id']}/documents", headers=auth("engineer"),
                    json={"document_number": "A-101", "name": "Level 2 Floor Plan", "discipline": "architecture"})
    assert r.status_code == 201, r.text
    return r.json()


def upload(client, headers, document_id, content=IFC_V1, filename="architecture_v1.ifc", **data):
    return client.post(f"/documents/{document_id}/revisions", headers=headers, data=data,
                       files={"file": (filename, content, "application/octet-stream")})
