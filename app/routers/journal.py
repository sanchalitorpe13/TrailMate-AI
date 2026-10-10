"""Nature journal endpoints."""

import sqlite3
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from app.database import get_db
from app.schemas import JournalCreate, JournalOut
from app.services import journal_service
from app.services.mission_service import MissionNotFound

router = APIRouter(prefix="/api/journal", tags=["journal"])

EntryId = Annotated[int, Path(ge=1, description="Journal entry id")]


@router.post("", response_model=JournalOut, status_code=status.HTTP_201_CREATED)
def create_entry(data: JournalCreate, conn: sqlite3.Connection = Depends(get_db)):
    try:
        return journal_service.create_entry(conn, data)
    except MissionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("", response_model=list[JournalOut])
def list_entries(
    limit: int = Query(100, ge=1, le=500),
    mission_id: Optional[int] = Query(None, ge=1),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Newest entries first. Optionally filter to one mission."""
    return journal_service.list_entries(conn, limit, mission_id)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: EntryId, conn: sqlite3.Connection = Depends(get_db)):
    try:
        journal_service.delete_entry(conn, entry_id)
    except journal_service.JournalEntryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)