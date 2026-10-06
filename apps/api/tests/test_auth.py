import os

os.environ["DATABASE_URL"] = "sqlite://"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import Role, User  # noqa: E402


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as db:
        db.add(User(email="engineer@example.local", full_name="E", role=Role.ENGINEER,
                    password_hash=hash_password("pw-test-123")))
        db.commit()

    def override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client, pw="pw-test-123"):
    return client.post("/auth/login", data={"username": "engineer@example.local", "password": pw})


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_login_success_and_me(client):
    token = login(client).json()["access_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["role"] == "engineer"


def test_login_wrong_password(client):
    assert login(client, "wrong").status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401
