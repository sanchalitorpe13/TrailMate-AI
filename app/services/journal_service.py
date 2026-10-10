
"""Service functions for TrailMate AI journal entries."""

import sqlite3

from app.models import utc_now_iso
from app.schemas import JournalCreate
from app.services.mission_service import MissionNotFound


class JournalEntryNotFound(Exception):
    """Raised when a journal entry does not exist."""


def create_entry(conn: sqlite3.Connection, data: JournalCreate) -> dict:
    """Create a journal entry and optionally link it to a mission."""
    if data.mission_id is not None:
        mission = conn.execute(
            "SELECT id FROM missions WHERE id = ?",
            (data.mission_id,),
        ).fetchone()
        if mission is None:
            raise MissionNotFound(f"Mission {data.mission_id} not found.")

    cursor = conn.execute(
        """
        INSERT INTO journal_entries
            (mission_id, content, mood, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (data.mission_id, data.content, data.mood, utc_now_iso()),
    )
    conn.commit()

    row = conn.execute(
        """
        SELECT j.*, m.title AS mission_title
        FROM journal_entries j
        LEFT JOIN missions m ON m.id = j.mission_id
        WHERE j.id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    return dict(row)


def list_entries(
    conn: sqlite3.Connection,
    limit: int = 100,
    mission_id: int | None = None,
) -> list[dict]:
    """List newest entries first, optionally filtered by mission."""
    query = """
        SELECT j.*, m.title AS mission_title
        FROM journal_entries j
        LEFT JOIN missions m ON m.id = j.mission_id
    """
    params = []

    if mission_id is not None:
        query += " WHERE j.mission_id = ?"
        params.append(mission_id)

    query += " ORDER BY j.created_at DESC, j.id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def delete_entry(conn: sqlite3.Connection, entry_id: int) -> None:
    """Delete an entry or raise if it does not exist."""
    cursor = conn.execute(
        "DELETE FROM journal_entries WHERE id = ?",
        (entry_id,),
    )
    if cursor.rowcount == 0:
        raise JournalEntryNotFound(
            f"Journal entry {entry_id} not found."
        )
    conn.commit()
