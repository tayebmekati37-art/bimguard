"""Development-only demo users. Passwords are for local demo use ONLY."""
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import Role, User

DEMO_USERS = [
    ("admin@example.local", "Demo Admin", Role.ADMIN, "admin-demo-pass"),
    ("engineer@example.local", "Demo Engineer", Role.ENGINEER, "engineer-demo-pass"),
    ("reviewer@example.local", "Demo Reviewer", Role.REVIEWER, "reviewer-demo-pass"),
]


def seed() -> None:
    with SessionLocal() as db:
        for email, name, role, pw in DEMO_USERS:
            if db.scalar(select(User).where(User.email == email)) is None:
                db.add(User(email=email, full_name=name, role=role, password_hash=hash_password(pw)))
        db.commit()


if __name__ == "__main__":
    seed()
    print("Seeded demo users.")
