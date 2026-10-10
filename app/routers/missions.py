"""Mission endpoints: generate, list, fetch, start, complete."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.database import get_db
from app.schemas import MissionCompleteRequest, MissionOut, MissionRequest
from app.services import mission_service

router = APIRouter(prefix="/api/missions", tags=["missions"])

MissionId = Annotated[int, Path(ge=1, description="Mission id")]


@router.post("", response_model=MissionOut, status_code=status.HTTP_201_CREATED)
def create_mission(request: MissionRequest, conn: sqlite3.Connection = Depends(get_db)):
    """Generate a mission with local Gemma (or the labelled fallback) and save it."""
    return mission_service.create_mission(conn, request)


@router.get("", response_model=list[MissionOut])
def list_missions(
    limit: int = Query(20, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Most recent missions first."""
    return mission_service.list_missions(conn, limit)


@router.get("/{mission_id}", response_model=MissionOut)
def get_mission(mission_id: MissionId, conn: sqlite3.Connection = Depends(get_db)):
    try:
        return mission_service.get_mission(conn, mission_id)
    except mission_service.MissionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{mission_id}/start", response_model=MissionOut)
def start_mission(mission_id: MissionId, conn: sqlite3.Connection = Depends(get_db)):
    """Mark a mission as started (the user pressed Start)."""
    try:
        return mission_service.start_mission(conn, mission_id)
    except mission_service.MissionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{mission_id}/complete", response_model=MissionOut)
def complete_mission(
    mission_id: MissionId,
    body: MissionCompleteRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Record that the user says they finished. A timer alone never calls this."""
    try:
        return mission_service.complete_mission(conn, mission_id, body.completed_task_count)
    except mission_service.MissionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except mission_service.InvalidCompletion as exc:
        raise HTTPException(status_code=422, detail=str(exc))