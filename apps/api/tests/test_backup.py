import json
from pathlib import Path

from app.core.config import get_settings
from app.services import backup as backup_service


def test_backup_requires_auth(client):
    r = client.post("/admin/backup")
    assert r.status_code == 401


def test_backup_requires_admin(client, auth):
    r = client.post("/admin/backup", headers=auth("engineer"))
    assert r.status_code == 403
    r = client.post("/admin/backup", headers=auth("bim_coordinator"))
    assert r.status_code == 403


def test_backup_writes_a_file_and_reports_counts(client, auth, project, monkeypatch, tmp_path):
    # Point the storage dir at a temp folder so tests don't litter
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))

    # Create one document so projects and documents tables are non-empty
    r = client.post(f"/projects/{project['id']}/documents", headers=auth("engineer"),
                    json={"document_number": "A-101", "name": "Test", "discipline": "architecture"})
    assert r.status_code == 201

    r = client.post("/admin/backup", headers=auth("admin"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert Path(body["path"]).exists()
    assert body["size_bytes"] > 0
    assert body["tables"]["projects"] >= 1
    assert body["tables"]["documents"] >= 1
    assert body["tables"]["users"] >= 1


def test_backup_file_is_valid_json_with_expected_schema(client, auth, monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))

    r = client.post("/admin/backup", headers=auth("admin"))
    assert r.status_code == 200
    body = r.json()
    path = Path(body["path"])
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema"] == "bimguard.backup/1"
    assert "created_at" in payload
    assert "tables" in payload
    assert "counts" in payload
    assert "projects" in payload["tables"]
    assert "users" in payload["tables"]
    assert payload["counts"]["users"] >= 1


def test_dump_tables_roundtrip(session_factory):
    """Direct service test: dump_tables returns dicts and consistent counts."""
    with session_factory() as db:
        tables, counts = backup_service.dump_tables(db)
    assert "users" in tables and "projects" in tables
    for name, rows in tables.items():
        assert counts[name] == len(rows)
        if rows:
            assert isinstance(rows[0], dict)