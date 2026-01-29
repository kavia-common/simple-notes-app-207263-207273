"""Notes CRUD router.

Provides REST endpoints for creating, listing, retrieving, updating and deleting notes.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from src.api.db import get_connection

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteBase(BaseModel):
    """Shared fields for notes."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Short title for the note.",
        examples=["Groceries"],
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="Full note content (plain text).",
        examples=["Milk, eggs, bread"],
    )


class NoteCreate(NoteBase):
    """Request payload for creating a note."""


class NoteUpdate(BaseModel):
    """Request payload for updating a note.

    Fields are optional; at least one must be provided.
    """

    title: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="Updated title (optional).",
    )
    content: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50_000,
        description="Updated content (optional).",
    )


class NoteOut(NoteBase):
    """Note representation returned by the API."""

    id: int = Field(..., description="Note ID.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")

    class Config:
        from_attributes = True


def _parse_note_row(row: dict) -> NoteOut:
    """Convert a DB row dict to NoteOut."""
    # SQLite returns timestamps as strings by default; FastAPI/Pydantic can parse.
    return NoteOut.model_validate(row)


@router.post(
    "",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create note",
    description="Create a new note with a title and content.",
    operation_id="create_note",
)
def create_note(payload: NoteCreate) -> NoteOut:
    """Create a new note.

    Args:
        payload: NoteCreate payload containing title and content.

    Returns:
        The created note.

    Raises:
        HTTPException: 500 on DB errors.
    """
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO notes (title, content)
            VALUES (?, ?)
            """,
            (payload.title, payload.content),
        )
        note_id = int(cur.lastrowid)
        conn.commit()

        cur.execute(
            """
            SELECT id, title, content, created_at, updated_at
            FROM notes
            WHERE id = ?
            """,
            (note_id,),
        )
        row = cur.fetchone()
        return _parse_note_row(row)
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error while creating note: {e}",
        ) from e
    finally:
        if conn is not None:
            conn.close()


@router.get(
    "",
    response_model=List[NoteOut],
    summary="List notes",
    description="List notes ordered by most recently updated first.",
    operation_id="list_notes",
)
def list_notes(limit: int = 200, offset: int = 0) -> List[NoteOut]:
    """List notes.

    Args:
        limit: Maximum number of notes to return (1..500).
        offset: Offset for pagination (>=0).

    Returns:
        List of notes.
    """
    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be between 1 and 500",
        )
    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="offset must be >= 0",
        )

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, content, created_at, updated_at
            FROM notes
            ORDER BY datetime(updated_at) DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cur.fetchall() or []
        return [_parse_note_row(r) for r in rows]
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error while listing notes: {e}",
        ) from e
    finally:
        if conn is not None:
            conn.close()


@router.get(
    "/{note_id}",
    response_model=NoteOut,
    summary="Get note",
    description="Fetch a single note by ID.",
    operation_id="get_note",
)
def get_note(note_id: int) -> NoteOut:
    """Get a note by ID.

    Args:
        note_id: Note ID.

    Returns:
        The note.

    Raises:
        HTTPException: 404 if not found.
    """
    if note_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="note_id must be a positive integer",
        )

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, content, created_at, updated_at
            FROM notes
            WHERE id = ?
            """,
            (note_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return _parse_note_row(row)
    except HTTPException:
        raise
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error while fetching note: {e}",
        ) from e
    finally:
        if conn is not None:
            conn.close()


@router.put(
    "/{note_id}",
    response_model=NoteOut,
    summary="Update note",
    description="Update a note's title and/or content.",
    operation_id="update_note",
)
def update_note(note_id: int, payload: NoteUpdate) -> NoteOut:
    """Update a note.

    Args:
        note_id: Note ID.
        payload: Fields to update (title/content). At least one must be provided.

    Returns:
        Updated note.

    Raises:
        HTTPException: 404 if note not found.
    """
    if note_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="note_id must be a positive integer",
        )
    if payload.title is None and payload.content is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of title/content must be provided",
        )

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Ensure note exists first for correct 404 semantics.
        cur.execute("SELECT id FROM notes WHERE id = ?", (note_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

        if payload.title is not None and payload.content is not None:
            cur.execute(
                "UPDATE notes SET title = ?, content = ? WHERE id = ?",
                (payload.title, payload.content, note_id),
            )
        elif payload.title is not None:
            cur.execute(
                "UPDATE notes SET title = ? WHERE id = ?",
                (payload.title, note_id),
            )
        else:
            cur.execute(
                "UPDATE notes SET content = ? WHERE id = ?",
                (payload.content, note_id),
            )

        conn.commit()

        cur.execute(
            """
            SELECT id, title, content, created_at, updated_at
            FROM notes
            WHERE id = ?
            """,
            (note_id,),
        )
        row = cur.fetchone()
        return _parse_note_row(row)
    except HTTPException:
        raise
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error while updating note: {e}",
        ) from e
    finally:
        if conn is not None:
            conn.close()


@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete note",
    description="Delete a note by ID.",
    operation_id="delete_note",
)
def delete_note(note_id: int) -> Response:
    """Delete a note.

    Args:
        note_id: Note ID.

    Returns:
        204 No Content on success.

    Raises:
        HTTPException: 404 if note not found.
    """
    if note_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="note_id must be a positive integer",
        )

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error while deleting note: {e}",
        ) from e
    finally:
        if conn is not None:
            conn.close()
