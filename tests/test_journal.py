"""Nature journal: create, list, filter, delete, validation, missing records."""

import pytest


def test_create_unlinked_entry_with_defaults(client):
    response = client.post("/api/journal", json={"content": "  Heard a woodpecker.  "})
    assert response.status_code == 201
    data = response.json()
    assert data["content"] == "Heard a woodpecker."
    assert data["mood"] == "neutral"
    assert data["mission_id"] is None
    assert data["mission_title"] is None
    assert data["created_at"].endswith("Z")


def test_create_entry_linked_to_a_mission(client, create_mission):
    mission = create_mission()
    response = client.post(
        "/api/journal", json={"content": "Smelled rain.", "mood": "calm", "mission_id": mission["id"]}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["mission_id"] == mission["id"]
    assert data["mission_title"] == mission["title"]
    assert data["mood"] == "calm"


def test_entries_are_listed_newest_first(client):
    for text in ("first", "second", "third"):
        client.post("/api/journal", json={"content": text})
    contents = [e["content"] for e in client.get("/api/journal").json()]
    assert contents == ["third", "second", "first"]


def test_list_can_be_limited_and_filtered_by_mission(client, create_mission):
    mission = create_mission()
    client.post("/api/journal", json={"content": "linked", "mission_id": mission["id"]})
    client.post("/api/journal", json={"content": "free note"})
    assert len(client.get("/api/journal?limit=1").json()) == 1
    filtered = client.get(f"/api/journal?mission_id={mission['id']}").json()
    assert [e["content"] for e in filtered] == ["linked"]


def test_entry_is_stored_verbatim_so_the_ui_must_escape_it(client):
    text = "<script>alert('x')</script> & more"
    created = client.post("/api/journal", json={"content": text}).json()
    assert created["content"] == text
    assert client.get("/api/journal").json()[0]["content"] == text


def test_delete_entry(client):
    entry = client.post("/api/journal", json={"content": "to delete"}).json()
    assert client.delete(f"/api/journal/{entry['id']}").status_code == 204
    assert client.get("/api/journal").json() == []
    assert client.delete(f"/api/journal/{entry['id']}").status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"content": ""},
        {"content": "     "},
        {"content": "x" * 2001},
        {"content": "ok", "mood": "furious"},
        {"content": "ok", "mission_id": 0},
        {},
    ],
)
def test_invalid_entries_are_rejected_and_not_saved(client, payload):
    assert client.post("/api/journal", json=payload).status_code == 422
    assert client.get("/api/journal").json() == []


def test_entry_for_unknown_mission_returns_404(client):
    response = client.post("/api/journal", json={"content": "hello", "mission_id": 9999})
    assert response.status_code == 404
    assert client.get("/api/journal").json() == []


def test_delete_unknown_or_invalid_entry(client):
    assert client.delete("/api/journal/9999").status_code == 404
    assert client.delete("/api/journal/0").status_code == 422