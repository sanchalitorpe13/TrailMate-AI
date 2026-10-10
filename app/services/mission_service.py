"""Mission business logic: AI-or-fallback generation, persistence, completion, stats."""

import json
import logging
import random
import sqlite3
from typing import Optional

from app.config import get_settings
from app.models import utc_now_iso
from app.schemas import GeneratedMission, MissionRequest
from app.services import ai_service

logger = logging.getLogger("trailmate.missions")


class MissionNotFound(Exception):
    pass


class InvalidCompletion(ValueError):
    pass


# ---------------------------------------------------------------- fallback generator
# Hand-written templates. These are NOT AI output and are always labelled "fallback".

_CONTENT = {
    "nature discovery": {
        "title": "Nature Detective",
        "tasks": [
            "Find three different natural textures, such as bark, stone, leaf or soil, and study each for a full minute.",
            "Look for a sign that an animal or insect has been nearby, like a feather, a web or a tiny track. Observe it without disturbing it.",
            "Find the smallest living thing you can see and watch what it does for one minute.",
            "Notice one thing that shows the season, like leaf colour, light or the sound of the air, and think about why it looks that way.",
            "Pick a spot, look at the same patch of ground for two minutes, and count how many different things you can spot in it.",
        ],
    },
    "bird watching": {
        "title": "Bird Listener",
        "tasks": [
            "Stand still for two minutes and count how many different bird sounds you can hear.",
            "Spot a bird and watch it from a respectful distance for one full minute. Notice its colours, size and movement.",
            "Scan the treetops, rooftops and sky for anything that flies.",
            "Describe one bird call in your own words, as a rhythm or a little sentence it might be saying.",
            "Find where birds seem to gather, such as a tree, a hedge or a wire, and notice what makes that spot attractive to them.",
        ],
    },
    "plants": {
        "title": "Plant Spotter",
        "tasks": [
            "Find three different leaf shapes and compare their edges, veins and sizes by eye.",
            "Look for a plant growing somewhere surprising, like a crack in the pavement or a wall.",
            "Find the tallest and the smallest plant you can see and notice how they differ.",
            "Look closely at one flower, seed or bud without picking it. Notice its colours and patterns.",
            "Find two plants of the same kind in different spots and notice whether they look alike.",
        ],
    },
    "mindfulness": {
        "title": "Mindful Moments",
        "tasks": [
            "Find a comfortable, safe spot to sit or stand and take ten slow breaths.",
            "Name five things you can see, four you can feel, three you can hear and two you can smell.",
            "If your spot is safe, close your eyes for one minute and listen for the farthest sound you can hear.",
            "Feel the ground under your feet and notice the temperature of the air on your skin.",
            "Watch a cloud, a leaf or moving water for two minutes without trying to name or judge anything.",
        ],
    },
    "photography": {
        "title": "Photo Walk",
        "tasks": [
            "Take up to three photos of things that catch your eye, then put your phone away again.",
            "Look for interesting light and shadow, and frame one scene carefully before you take a single shot.",
            "Find a pattern in nature, such as repeated leaves or ripples, and photograph or sketch it.",
            "Take one photo from a low angle, close to the ground.",
            "Choose one thing you did not photograph and look at it with your eyes for a full minute instead.",
        ],
    },
    "walking": {
        "title": "Wander Walk",
        "tasks": [
            "Walk at an easy pace and notice something on your route that you have never noticed before.",
            "Take ten slow steps and pay attention to how your feet meet the ground.",
            "Choose a landmark in view, walk toward it on a safe public path, and notice everything on the way.",
            "Turn around halfway and see how the place looks from the opposite direction.",
            "Walk for two minutes without looking at anything on a screen, and notice how your breathing changes.",
        ],
    },
}

_DIFFICULTY_NOTE = {
    "easy": "Take it slow and easy, with no need to rush or go far.",
    "medium": "A balanced mix of looking closely and moving around.",
    "adventurous": "A bolder challenge, while always staying on open, public, safe paths.",
}

_ADVENTUROUS_CHALLENGE = (
    "Challenge: visit a corner, path or viewpoint of this place you have never explored before, "
    "stay on open public paths, and notice what is different there."
)

_PHONE_REMINDERS = [
    "Read the mission, lock your phone, go be here.",
    "Read this once, then lock your phone and slip it away. The best part of this mission happens out there, not on this screen.",
    "Quick promise: phone on silent, in your pocket, screen dark. Your mission starts the moment you look up.",
    "Lock your phone now. The sky, the trees and the birds are far better company than a screen.",
]


def _join_phrase(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def fallback_mission(request: MissionRequest, rng: Optional[random.Random] = None) -> GeneratedMission:
    """Build a mission from built-in templates. Pass a seeded Random for repeatable output."""
    rng = rng or random.Random()
    interests = list(request.interests)
    count = ai_service.TASK_COUNT_BY_DURATION[request.duration_minutes]

    pools = [rng.sample(_CONTENT[i]["tasks"], k=len(_CONTENT[i]["tasks"])) for i in interests]
    tasks: list[str] = []
    while len(tasks) < count:
        for pool in pools:
            if pool and len(tasks) < count:
                tasks.append(pool.pop())
    if request.difficulty == "adventurous":
        tasks[-1] = _ADVENTUROUS_CHALLENGE

    title = " + ".join(_CONTENT[i]["title"] for i in interests[:2])
    description = (
        f"A {request.duration_minutes}-minute {request.difficulty} outing in {request.environment}, "
        f"focused on {_join_phrase(interests)}. {_DIFFICULTY_NOTE[request.difficulty]}"
    )[:400]
    return GeneratedMission(
        title=title,
        description=description,
        tasks=tasks,
        phone_reminder=rng.choice(_PHONE_REMINDERS),
    )


# ---------------------------------------------------------------- persistence helpers

def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["interests"] = json.loads(data["interests"])
    data["tasks"] = json.loads(data["tasks"])
    return data


def _fetch_row(conn: sqlite3.Connection, mission_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
    if row is None:
        raise MissionNotFound(f"Mission {mission_id} not found.")
    return row


def get_mission(conn: sqlite3.Connection, mission_id: int) -> dict:
    return _row_to_dict(_fetch_row(conn, mission_id))


def list_missions(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM missions ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------- main operations

def create_mission(conn: sqlite3.Connection, request: MissionRequest) -> dict:
    """Generate with local Gemma if possible, otherwise use the labelled fallback, then save."""
    try:
        generated = ai_service.generate_mission(request)
        source, model_name = "ai", get_settings().ollama_model
    except ai_service.AIGenerationError as exc:
        logger.warning("Using fallback mission: %s", exc.reason)
        generated = fallback_mission(request)
        source, model_name = "fallback", None

    cursor = conn.execute(
        """
        INSERT INTO missions (
            title, description, duration_minutes, difficulty, interests, environment,
            tasks, phone_reminder, source, model_name, status, completed_task_count, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'created', 0, ?)
        """,
        (
            generated.title,
            generated.description,
            request.duration_minutes,
            request.difficulty,
            json.dumps(request.interests, ensure_ascii=False),
            request.environment,
            json.dumps(generated.tasks, ensure_ascii=False),
            generated.phone_reminder,
            source,
            model_name,
            utc_now_iso(),
        ),
    )
    conn.commit()
    return get_mission(conn, cursor.lastrowid)


def start_mission(conn: sqlite3.Connection, mission_id: int) -> dict:
    """Mark a freshly created mission as started. Already started/completed missions are unchanged."""
    row = _fetch_row(conn, mission_id)
    if row["status"] == "created":
        conn.execute(
            "UPDATE missions SET status = 'started', started_at = ? WHERE id = ?",
            (utc_now_iso(), mission_id),
        )
        conn.commit()
    return get_mission(conn, mission_id)


def complete_mission(conn: sqlite3.Connection, mission_id: int, completed_task_count: int) -> dict:
    """Record user-reported completion. Repeating the call on a completed mission changes nothing."""
    row = _fetch_row(conn, mission_id)
    if row["status"] == "completed":
        return _row_to_dict(row)
    task_total = len(json.loads(row["tasks"]))
    if not 1 <= completed_task_count <= task_total:
        raise InvalidCompletion(f"completed_task_count must be between 1 and {task_total}.")
    conn.execute(
        "UPDATE missions SET status = 'completed', completed_task_count = ?, completed_at = ? WHERE id = ?",
        (completed_task_count, utc_now_iso(), mission_id),
    )
    conn.commit()
    return get_mission(conn, mission_id)


def get_stats(conn: sqlite3.Connection) -> dict:
    """All numbers are self-reported; nothing is verified by GPS or sensors."""
    created = conn.execute("SELECT COUNT(*) FROM missions").fetchone()[0]
    completed = conn.execute("SELECT COUNT(*) FROM missions WHERE status = 'completed'").fetchone()[0]
    minutes = conn.execute(
        "SELECT COALESCE(SUM(duration_minutes), 0) FROM missions WHERE status = 'completed'"
    ).fetchone()[0]
    entries = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
    return {
        "missions_created": created,
        "missions_completed": completed,
        "self_reported_outdoor_minutes": minutes,
        "journal_entries": entries,
        "recent_activity": list_missions(conn, 5),
    }