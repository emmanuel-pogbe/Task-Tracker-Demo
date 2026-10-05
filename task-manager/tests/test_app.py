import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from app import app
from db import init_db
from scheduler import check_overdue


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    init_db()
    return app.test_client()


def iso(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def titles(client):
    return [t["title"] for t in client.get("/api/tasks").get_json()]


def test_create_and_order(client):
    assert client.post("/api/tasks", json={"title": "A", "due_at": iso(5)}).status_code == 201
    assert client.post("/api/tasks", json={"title": "B", "due_at": iso(1)}).status_code == 201
    # B is newer (or same second but due sooner), so B comes first.
    assert titles(client) == ["B", "A"]


def test_validation(client):
    assert client.post("/api/tasks", json={"title": "  ", "due_at": iso(1)}).status_code == 400
    assert client.post("/api/tasks", json={"title": "X", "due_at": "nope"}).status_code == 400


def test_mark_done(client):
    task = client.post("/api/tasks", json={"title": "A", "due_at": iso(1)}).get_json()
    res = client.post(f"/api/tasks/{task['id']}/done")
    assert res.status_code == 200 and res.get_json()["status"] == "done"
    assert client.post("/api/tasks/9999/done").status_code == 404


def test_overdue_scheduler(client, capsys):
    client.post("/api/tasks", json={"title": "Late", "due_at": iso(-1)})
    client.post("/api/tasks", json={"title": "Later", "due_at": iso(3)})
    check_overdue()
    flags = {t["title"]: t["is_overdue"] for t in client.get("/api/tasks").get_json()}
    assert flags == {"Late": True, "Later": None}
    assert "[OVERDUE]" in capsys.readouterr().out
    check_overdue()  # second run must not print again
    assert capsys.readouterr().out == ""


def test_export_csv(client):
    client.post("/api/tasks", json={"title": "=bad", "due_at": iso(1)})
    res = client.get("/api/tasks/export?start=2000-01-01&end=2100-01-01")
    assert res.status_code == 200 and res.mimetype == "text/csv"
    lines = res.data.decode().splitlines()
    assert lines[0] == "id,title,status,is_overdue,created_at,updated_at,due_at"
    assert "'=bad" in lines[1]
    assert client.get("/api/tasks/export?start=bad&end=2100-01-01").status_code == 400