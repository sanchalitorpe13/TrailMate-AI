"""Shared test fixtures. No test needs Ollama, Gemma or internet access."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import ai_service


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Every test gets its own empty SQLite file, never the real data/trailmate.db."""
    monkeypatch.setenv("TRAILMATE_DB_PATH", str(tmp_path / "test.db"))


@pytest.fixture(autouse=True)
def ollama_unavailable(monkeypatch):
    """By default the model is 'down', so missions use the labelled fallback."""

    def _no_model(request):
        raise ai_service.AIGenerationError("Ollama is unavailable in tests.")

    monkeypatch.setattr(ai_service, "generate_mission", _no_model)
    monkeypatch.setattr(ai_service, "check_status", lambda: (False, False))


@pytest.fixture()
def client():
    """TestClient used as a context manager so the startup hook creates the database."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def mission_payload():
    return {
        "duration_minutes": 20,
        "interests": ["plants", "walking"],
        "environment": "nearby park",
        "difficulty": "easy",
    }


@pytest.fixture()
def create_mission(client, mission_payload):
    """Factory: create_mission(duration_minutes=45) -> mission JSON."""

    def _create(**overrides):
        response = client.post("/api/missions", json={**mission_payload, **overrides})
        assert response.status_code == 201, response.text
        return response.json()

    return _create


class _FakeResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, status_code=200, payload=None, bad_json=False):
        self.status_code = status_code
        self._payload = payload
        self._bad_json = bad_json

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://ollama.test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


@pytest.fixture()
def fake_response():
    return _FakeResponse