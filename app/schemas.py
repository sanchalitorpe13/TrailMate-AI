"""Pydantic schemas: the API contract between backend and frontend."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Duration = Literal[10, 20, 30, 45, 60]
Interest = Literal[
    "nature discovery", "bird watching", "plants", "mindfulness", "photography", "walking"
]
Difficulty = Literal["easy", "medium", "adventurous"]
Mood = Literal["calm", "happy", "energized", "curious", "grateful", "tired", "neutral"]


class MissionRequest(BaseModel):
    duration_minutes: Duration
    interests: list[Interest] = Field(min_length=1, max_length=6)
    environment: str = Field(min_length=1, max_length=120)
    difficulty: Difficulty

    @field_validator("environment")
    @classmethod
    def clean_environment(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("environment must not be blank")
        return value

    @field_validator("interests")
    @classmethod
    def unique_interests(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class GeneratedMission(BaseModel):
    """Shape the AI (or fallback) must produce. Used to validate model output."""

    title: str = Field(min_length=3, max_length=100)
    description: str = Field(min_length=10, max_length=400)
    tasks: list[str] = Field(min_length=3, max_length=5)
    phone_reminder: str = Field(min_length=5, max_length=200)

    @field_validator("title", "description", "phone_reminder")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("tasks")
    @classmethod
    def clean_tasks(cls, value: list[str]) -> list[str]:
        cleaned = [t.strip() for t in value if isinstance(t, str) and t.strip()]
        if not 3 <= len(cleaned) <= 5 or any(len(t) > 220 for t in cleaned):
            raise ValueError("need 3-5 tasks of at most 220 characters")
        return cleaned


class MissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    duration_minutes: int
    difficulty: str
    interests: list[str]
    environment: str
    tasks: list[str]
    phone_reminder: str
    source: Literal["ai", "fallback"]
    model_name: Optional[str] = None
    status: Literal["created", "started", "completed"]
    completed_task_count: int
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class MissionCompleteRequest(BaseModel):
    """User-reported completion. A timer alone never completes a mission."""

    completed_task_count: int = Field(ge=0, le=5)


class JournalCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    mood: Mood = "neutral"
    mission_id: Optional[int] = Field(default=None, ge=1)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class JournalOut(BaseModel):
    id: int
    mission_id: Optional[int] = None
    mission_title: Optional[str] = None
    content: str
    mood: str
    created_at: str


class StatsOut(BaseModel):
    missions_created: int
    missions_completed: int
    self_reported_outdoor_minutes: int
    journal_entries: int
    recent_activity: list[MissionOut]
    verified_outdoor_minutes: int = 0
    verification_note: str = (
        "All activity is self-reported. TrailMate AI does not use GPS or sensors, "
        "so no outdoor visit is independently verified."
    )


class HealthOut(BaseModel):
    status: Literal["ok"]
    ollama_available: bool
    model_ready: bool
    model: str