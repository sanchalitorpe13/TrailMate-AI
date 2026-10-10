"""Progress statistics endpoint."""

import sqlite3

from fastapi import APIRouter, Depends

from app.database import get_db
from app.schemas import StatsOut
from app.services import mission_service

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
def get_stats(conn: sqlite3.Connection = Depends(get_db)):
    """Self-reported progress. Nothing here is verified by GPS or sensors."""
    return mission_service.get_stats(conn)