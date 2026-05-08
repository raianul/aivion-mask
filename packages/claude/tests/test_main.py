import uuid
import pytest
from fastapi.testclient import TestClient
from aivion_mask_claude import main as claude_main
from aivion_mask_claude.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers():
    return {"X-Aivion-Auth": claude_main._auth_token}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_mcp_returns_manifest(client):
    r = client.get("/mcp")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "aivion-mask"
    assert "proxy" in data


def test_delete_session_requires_auth(client):
    r = client.delete(f"/v1/session/{uuid.uuid4()}")
    assert r.status_code == 401


def test_delete_session_rejects_non_uuid(client, auth_headers):
    r = client.delete("/v1/session/test-session", headers=auth_headers)
    assert r.status_code == 400


def test_delete_session(client, auth_headers):
    r = client.delete(f"/v1/session/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 200


def test_dashboard_requires_auth(client):
    r = client.get("/")
    assert r.status_code == 401


def test_dashboard_with_token_query(client):
    r = client.get(f"/?token={claude_main._auth_token}")
    assert r.status_code == 200
    assert "aivion" in r.text.lower()


def test_dashboard_html_packaged():
    from pathlib import Path
    p = Path(claude_main.__file__).parent / "dashboard.html"
    assert p.exists(), "dashboard.html missing — won't be in the wheel"


def test_health_uses_package_version(client):
    from aivion_mask_claude import __version__
    r = client.get("/health")
    assert r.json()["version"] == __version__


def test_sessions_requires_auth(client):
    r = client.get("/v1/sessions")
    assert r.status_code == 401


def test_sessions_with_auth(client, auth_headers):
    r = client.get("/v1/sessions", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "total" in body and "sessions" in body


def test_cleanup_requires_auth(client):
    r = client.post("/v1/sessions/cleanup")
    assert r.status_code == 401


def test_messages_no_auth(client):
    r = client.post("/v1/messages", json={"model": "claude-sonnet-4-6", "max_tokens": 1, "messages": []})
    assert r.status_code == 401
    assert "auth" in r.json()["detail"].lower()


def test_messages_session_header_requires_auth(client):
    r = client.post(
        "/v1/messages",
        headers={"X-Aivion-Session": str(uuid.uuid4()), "x-api-key": "sk-test"},
        json={"model": "claude-sonnet-4-6", "max_tokens": 1, "messages": []},
    )
    assert r.status_code == 401
    assert "X-Aivion-Auth" in r.json()["detail"]


def test_messages_session_header_must_be_uuid(client, auth_headers):
    headers = {**auth_headers, "X-Aivion-Session": "not-a-uuid", "x-api-key": "sk-test"}
    r = client.post(
        "/v1/messages",
        headers=headers,
        json={"model": "claude-sonnet-4-6", "max_tokens": 1, "messages": []},
    )
    assert r.status_code == 400
