import pytest
from fastapi.testclient import TestClient
from aivion_mask_claude.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


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


def test_delete_session(client):
    r = client.delete("/v1/session/test-session")
    assert r.status_code == 200


def test_messages_no_auth(client):
    r = client.post("/v1/messages", json={"model": "claude-sonnet-4-6", "max_tokens": 1, "messages": []})
    assert r.status_code == 401
    assert "auth" in r.json()["detail"].lower()
