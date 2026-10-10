"""Progress statistics."""


def test_stats_for_an_empty_database(client):
    data = client.get("/api/stats").json()
    assert data["missions_created"] == 0
    assert data["missions_completed"] == 0
    assert data["self_reported_outdoor_minutes"] == 0
    assert data["journal_entries"] == 0
    assert data["recent_activity"] == []


def test_stats_never_claim_verified_activity(client):
    data = client.get("/api/stats").json()
    assert data["verified_outdoor_minutes"] == 0
    assert "self-reported" in data["verification_note"]
    assert "GPS" in data["verification_note"]


def test_stats_count_only_completed_missions_for_minutes(client, create_mission):
    first = create_mission(duration_minutes=20)
    second = create_mission(duration_minutes=45)
    create_mission(duration_minutes=60)  # never completed
    client.patch(f"/api/missions/{first['id']}/complete", json={"completed_task_count": 3})
    data = client.get("/api/stats").json()
    assert data["missions_created"] == 3
    assert data["missions_completed"] == 1
    assert data["self_reported_outdoor_minutes"] == 20

    client.patch(f"/api/missions/{second['id']}/complete", json={"completed_task_count": 5})
    data = client.get("/api/stats").json()
    assert data["missions_completed"] == 2
    assert data["self_reported_outdoor_minutes"] == 65


def test_a_started_but_unfinished_mission_adds_no_minutes(client, create_mission):
    mission = create_mission(duration_minutes=30)
    client.patch(f"/api/missions/{mission['id']}/start")
    data = client.get("/api/stats").json()
    assert data["missions_completed"] == 0
    assert data["self_reported_outdoor_minutes"] == 0


def test_completing_twice_does_not_double_count(client, create_mission):
    mission = create_mission(duration_minutes=20)
    for _ in range(2):
        client.patch(f"/api/missions/{mission['id']}/complete", json={"completed_task_count": 2})
    data = client.get("/api/stats").json()
    assert data["missions_completed"] == 1
    assert data["self_reported_outdoor_minutes"] == 20


def test_stats_count_journal_entries_and_follow_deletions(client):
    ids = [client.post("/api/journal", json={"content": f"note {n}"}).json()["id"] for n in range(3)]
    assert client.get("/api/stats").json()["journal_entries"] == 3
    client.delete(f"/api/journal/{ids[0]}")
    assert client.get("/api/stats").json()["journal_entries"] == 2


def test_recent_activity_shows_the_five_newest_missions(client, create_mission):
    ids = [create_mission()["id"] for _ in range(6)]
    recent = client.get("/api/stats").json()["recent_activity"]
    assert [m["id"] for m in recent] == list(reversed(ids))[:5]