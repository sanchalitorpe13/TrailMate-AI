"""Missions: creation, persistence, fallback, AI integration (mocked), completion, validation."""

import json
import random

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.schemas import GeneratedMission, MissionRequest
from app.services import ai_service
from app.services.ai_service import AIGenerationError, contains_unsafe_text
from app.services.ai_service import generate_mission as real_generate_mission
from app.services.mission_service import fallback_mission


def make_ai_mission() -> GeneratedMission:
    return GeneratedMission(
        title="Leaf Hunt",
        description="Find five leaves with different shapes and notice how they differ.",
        tasks=[
            "Find a leaf with smooth edges and look at its veins.",
            "Find a leaf with jagged edges and compare it to the first.",
            "Sit for one minute and listen to the leaves moving.",
        ],
        phone_reminder="Lock your phone and look up.",
    )


# ------------------------------------------------------------------ creation and persistence

def test_create_mission_uses_labelled_fallback_when_ollama_is_down(client, mission_payload):
    response = client.post("/api/missions", json=mission_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 1
    assert data["source"] == "fallback"
    assert data["model_name"] is None
    assert data["status"] == "created"
    assert data["completed_task_count"] == 0
    assert data["interests"] == ["plants", "walking"]
    assert data["environment"] == "nearby park"
    assert data["duration_minutes"] == 20
    assert len(data["tasks"]) == 3
    assert data["phone_reminder"]
    assert data["created_at"].endswith("Z")


def test_mission_is_persisted_and_listed(client, create_mission):
    created = create_mission()
    fetched = client.get(f"/api/missions/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created
    listed = client.get("/api/missions").json()
    assert [m["id"] for m in listed] == [created["id"]]


def test_missions_survive_an_app_restart(monkeypatch, tmp_path, mission_payload):
    monkeypatch.setenv("TRAILMATE_DB_PATH", str(tmp_path / "restart.db"))
    with TestClient(app) as first:
        created = first.post("/api/missions", json=mission_payload).json()
    with TestClient(app) as second:
        again = second.get(f"/api/missions/{created['id']}")
    assert again.status_code == 200
    assert again.json()["title"] == created["title"]


def test_ai_generated_mission_is_labelled_and_saved(client, monkeypatch, mission_payload):
    monkeypatch.setattr(ai_service, "generate_mission", lambda request: make_ai_mission())
    data = client.post("/api/missions", json=mission_payload).json()
    assert data["source"] == "ai"
    assert data["model_name"] == get_settings().ollama_model
    assert data["title"] == "Leaf Hunt"
    assert len(data["tasks"]) == 3


def test_list_is_newest_first_and_respects_limit(client, create_mission):
    ids = [create_mission()["id"] for _ in range(3)]
    listed = client.get("/api/missions").json()
    assert [m["id"] for m in listed] == list(reversed(ids))
    assert len(client.get("/api/missions?limit=2").json()) == 2
    assert client.get("/api/missions?limit=0").status_code == 422


def test_environment_is_normalised_and_interests_deduplicated(client, mission_payload):
    payload = {**mission_payload, "environment": "  nearby   park ", "interests": ["plants", "plants"]}
    data = client.post("/api/missions", json=payload).json()
    assert data["environment"] == "nearby park"
    assert data["interests"] == ["plants"]


# ------------------------------------------------------------------ invalid input

@pytest.mark.parametrize(
    "override",
    [
        {"duration_minutes": 25},
        {"duration_minutes": "soon"},
        {"interests": []},
        {"interests": ["skydiving"]},
        {"environment": ""},
        {"environment": "     "},
        {"environment": "x" * 121},
        {"difficulty": "impossible"},
    ],
)
def test_invalid_mission_request_is_rejected_and_not_saved(client, mission_payload, override):
    response = client.post("/api/missions", json={**mission_payload, **override})
    assert response.status_code == 422
    assert client.get("/api/missions").json() == []


def test_missing_fields_are_rejected(client):
    assert client.post("/api/missions", json={}).status_code == 422


def test_malformed_json_body_is_rejected(client):
    response = client.post(
        "/api/missions", content="{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422


# ------------------------------------------------------------------ missing missions

def test_unknown_mission_returns_404(client):
    assert client.get("/api/missions/999").status_code == 404
    assert client.patch("/api/missions/999/start").status_code == 404
    response = client.patch("/api/missions/999/complete", json={"completed_task_count": 1})
    assert response.status_code == 404


@pytest.mark.parametrize("bad_id", ["0", "-1", "abc"])
def test_invalid_mission_id_is_rejected(client, bad_id):
    assert client.get(f"/api/missions/{bad_id}").status_code == 422


# ------------------------------------------------------------------ start and completion

def test_start_marks_mission_started_and_is_idempotent(client, create_mission):
    mission = create_mission()
    first = client.patch(f"/api/missions/{mission['id']}/start").json()
    assert first["status"] == "started"
    assert first["started_at"] is not None
    second = client.patch(f"/api/missions/{mission['id']}/start").json()
    assert second["started_at"] == first["started_at"]


def test_complete_mission_records_self_reported_progress(client, create_mission):
    mission = create_mission()
    client.patch(f"/api/missions/{mission['id']}/start")
    response = client.patch(f"/api/missions/{mission['id']}/complete", json={"completed_task_count": 2})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["completed_task_count"] == 2
    assert data["completed_at"] is not None


def test_completing_twice_does_not_change_the_mission(client, create_mission):
    mission = create_mission()
    first = client.patch(f"/api/missions/{mission['id']}/complete", json={"completed_task_count": 2}).json()
    second = client.patch(f"/api/missions/{mission['id']}/complete", json={"completed_task_count": 3})
    assert second.status_code == 200
    assert second.json()["completed_task_count"] == 2
    assert second.json()["completed_at"] == first["completed_at"]


@pytest.mark.parametrize("count", [0, 4, 6, -1])
def test_invalid_completion_count_is_rejected(client, create_mission, count):
    mission = create_mission()  # 20 minutes -> 3 tasks
    response = client.patch(f"/api/missions/{mission['id']}/complete", json={"completed_task_count": count})
    assert response.status_code == 422
    assert client.get(f"/api/missions/{mission['id']}").json()["status"] == "created"


def test_completion_requires_a_body(client, create_mission):
    mission = create_mission()
    assert client.patch(f"/api/missions/{mission['id']}/complete").status_code == 422


# ------------------------------------------------------------------ built-in fallback generator

@pytest.mark.parametrize("duration,expected", [(10, 3), (20, 3), (30, 4), (45, 5), (60, 5)])
def test_fallback_task_count_matches_duration(duration, expected):
    request = MissionRequest(
        duration_minutes=duration, interests=["plants"], environment="a garden", difficulty="easy"
    )
    assert len(fallback_mission(request).tasks) == expected


def test_fallback_mixes_interests_without_duplicate_tasks():
    request = MissionRequest(
        duration_minutes=60,
        interests=["plants", "bird watching", "mindfulness"],
        environment="campus grounds",
        difficulty="medium",
    )
    mission = fallback_mission(request)
    assert len(mission.tasks) == 5
    assert len(set(mission.tasks)) == 5
    assert "campus grounds" in mission.description


def test_fallback_adventurous_adds_a_safe_public_challenge():
    request = MissionRequest(
        duration_minutes=30, interests=["walking"], environment="a nearby park", difficulty="adventurous"
    )
    last_task = fallback_mission(request).tasks[-1]
    assert "public" in last_task


def test_fallback_is_repeatable_with_a_seeded_random():
    request = MissionRequest(
        duration_minutes=30, interests=["plants", "walking"], environment="a garden", difficulty="easy"
    )
    first = fallback_mission(request, random.Random(7))
    second = fallback_mission(request, random.Random(7))
    assert first == second


@pytest.mark.parametrize("difficulty", ["easy", "medium", "adventurous"])
def test_fallback_content_passes_the_safety_check(difficulty):
    for interest in ("nature discovery", "bird watching", "plants", "mindfulness", "photography", "walking"):
        for duration in (10, 20, 30, 45, 60):
            request = MissionRequest(
                duration_minutes=duration, interests=[interest],
                environment="a nearby park", difficulty=difficulty,
            )
            mission = fallback_mission(request)
            text = " ".join([mission.title, mission.description, mission.phone_reminder, *mission.tasks])
            assert not contains_unsafe_text(text), text


# ------------------------------------------------------------------ AI service (HTTP mocked)

AI_REQUEST = MissionRequest(
    duration_minutes=20, interests=["plants"], environment="a garden", difficulty="easy"
)


def ollama_reply(**overrides):
    mission = {
        "title": "Leaf Hunt",
        "description": "Find five leaves with different shapes and notice how they differ.",
        "tasks": ["Find a smooth leaf.", "Find a jagged leaf.", "Listen to the leaves for a minute."],
        "phone_reminder": "Lock your phone and look up.",
    }
    mission.update(overrides)
    return {"message": {"content": json.dumps(mission)}}


def test_ai_service_parses_a_valid_response_and_sends_a_json_request(monkeypatch, fake_response):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"], captured["json"] = url, kwargs["json"]
        return fake_response(payload=ollama_reply())

    monkeypatch.setattr(httpx, "post", fake_post)
    mission = real_generate_mission(AI_REQUEST)
    assert mission.title == "Leaf Hunt"
    assert captured["url"].endswith("/api/chat")
    assert captured["json"]["stream"] is False
    assert captured["json"]["model"] == get_settings().ollama_model
    assert "format" in captured["json"]
    assert "a garden" in captured["json"]["messages"][1]["content"]


def test_ai_service_accepts_json_wrapped_in_a_code_fence(monkeypatch, fake_response):
    fenced = "```json\n" + ollama_reply()["message"]["content"] + "\n```"
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: fake_response(payload={"message": {"content": fenced}})
    )
    assert real_generate_mission(AI_REQUEST).title == "Leaf Hunt"


def test_ai_service_trims_a_slightly_too_long_task_list(monkeypatch, fake_response):
    tasks = [f"Task number {n} outdoors." for n in range(1, 7)]
    monkeypatch.setattr(httpx, "post", lambda url, **kw: fake_response(payload=ollama_reply(tasks=tasks)))
    assert len(real_generate_mission(AI_REQUEST).tasks) == 5


def test_ai_service_reports_ollama_not_running(monkeypatch):
    def boom(url, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(AIGenerationError, match="not running"):
        real_generate_mission(AI_REQUEST)


def test_ai_service_reports_a_timeout(monkeypatch):
    def slow(url, **kwargs):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(httpx, "post", slow)
    with pytest.raises(AIGenerationError, match="too long"):
        real_generate_mission(AI_REQUEST)


def test_ai_service_reports_a_missing_model(monkeypatch, fake_response):
    monkeypatch.setattr(httpx, "post", lambda url, **kw: fake_response(status_code=404))
    with pytest.raises(AIGenerationError, match="ollama pull"):
        real_generate_mission(AI_REQUEST)


def test_ai_service_reports_other_http_errors(monkeypatch, fake_response):
    monkeypatch.setattr(httpx, "post", lambda url, **kw: fake_response(status_code=500))
    with pytest.raises(AIGenerationError, match="HTTP 500"):
        real_generate_mission(AI_REQUEST)


@pytest.mark.parametrize("content", ["Sure! Here is your mission.", "{ broken json", "[1, 2, 3]", "   "])
def test_ai_service_rejects_unusable_model_output(monkeypatch, fake_response, content):
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: fake_response(payload={"message": {"content": content}})
    )
    with pytest.raises(AIGenerationError):
        real_generate_mission(AI_REQUEST)


def test_ai_service_rejects_a_response_with_too_few_tasks(monkeypatch, fake_response):
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: fake_response(payload=ollama_reply(tasks=["Only one task."]))
    )
    with pytest.raises(AIGenerationError, match="required format"):
        real_generate_mission(AI_REQUEST)


def test_ai_service_rejects_unsafe_suggestions(monkeypatch, fake_response):
    tasks = ["Climb the tallest tree you can find.", "Look at the sky.", "Listen to the wind."]
    monkeypatch.setattr(httpx, "post", lambda url, **kw: fake_response(payload=ollama_reply(tasks=tasks)))
    with pytest.raises(AIGenerationError, match="safety"):
        real_generate_mission(AI_REQUEST)


def test_unusable_model_output_leads_to_a_saved_fallback_mission(client, monkeypatch, fake_response, mission_payload):
    """End to end: real ai_service code, bad model output, labelled fallback saved."""
    monkeypatch.setattr(ai_service, "generate_mission", real_generate_mission)
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: fake_response(payload={"message": {"content": "not json"}})
    )
    data = client.post("/api/missions", json=mission_payload).json()
    assert data["source"] == "fallback"
    assert data["model_name"] is None


@pytest.mark.parametrize(
    "text,unsafe",
    [
        ("Climb the old oak.", True),
        ("Approach the deer slowly.", True),
        ("You may taste the berries.", True),
        ("Check the forecast first.", True),
        ("Notice the colours of three leaves.", False),
        ("Take ten slow breaths and watch the clouds.", False),
    ],
)
def test_safety_filter(text, unsafe):
    assert contains_unsafe_text(text) is unsafe