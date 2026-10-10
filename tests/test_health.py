"""Health endpoint, startup behaviour, static files and Ollama status detection."""

import httpx

from app.config import get_settings
from app.services import ai_service
from app.services.ai_service import check_status as real_check_status


def test_health_when_ollama_is_missing(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["ollama_available"] is False
    assert body["model_ready"] is False
    assert body["model"] == get_settings().ollama_model


def test_health_when_model_is_ready(client, monkeypatch):
    monkeypatch.setattr(ai_service, "check_status", lambda: (True, True))
    body = client.get("/api/health").json()
    assert body["ollama_available"] is True
    assert body["model_ready"] is True


def test_health_when_ollama_runs_but_model_is_missing(client, monkeypatch):
    monkeypatch.setattr(ai_service, "check_status", lambda: (True, False))
    body = client.get("/api/health").json()
    assert body["ollama_available"] is True
    assert body["model_ready"] is False


def test_database_is_created_on_startup(client, tmp_path):
    assert (tmp_path / "test.db").is_file()


def test_frontend_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "TrailMate" in response.text


def test_static_assets_are_served(client):
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_privacy_headers_block_external_resources(client):
    headers = client.get("/").headers
    assert headers["content-security-policy"].startswith("default-src 'self'")
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"


def test_unknown_api_route_returns_404(client):
    assert client.get("/api/does-not-exist").status_code == 404


# ---- check_status() with a faked HTTP layer (no real Ollama needed) ----

def test_check_status_when_connection_fails(monkeypatch):
    def boom(url, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", boom)
    assert real_check_status() == (False, False)


def test_check_status_model_installed(monkeypatch, fake_response):
    name = get_settings().ollama_model
    monkeypatch.setattr(
        httpx, "get", lambda url, **kw: fake_response(payload={"models": [{"name": name}]})
    )
    assert real_check_status() == (True, True)


def test_check_status_model_not_installed(monkeypatch, fake_response):
    monkeypatch.setattr(
        httpx, "get", lambda url, **kw: fake_response(payload={"models": [{"name": "other:1b"}]})
    )
    assert real_check_status() == (True, False)


def test_check_status_untagged_model_matches_latest(monkeypatch, fake_response):
    monkeypatch.setenv("TRAILMATE_OLLAMA_MODEL", "gemma3")
    monkeypatch.setattr(
        httpx, "get", lambda url, **kw: fake_response(payload={"models": [{"name": "gemma3:latest"}]})
    )
    assert real_check_status() == (True, True)


def test_check_status_unreadable_json(monkeypatch, fake_response):
    monkeypatch.setattr(httpx, "get", lambda url, **kw: fake_response(bad_json=True))
    assert real_check_status() == (False, False)