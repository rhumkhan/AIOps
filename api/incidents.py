"""Read-only incident API for operator review and defense demos."""

from __future__ import annotations

import os

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from psycopg2.extras import RealDictCursor

router = APIRouter()


@router.get("/incidents")
def list_incidents(
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
) -> list[dict]:
    """List recent incidents with their cause hypothesis, impact, and evidence."""
    if status is not None and status not in {"open", "acknowledged", "resolved"}:
        raise HTTPException(status_code=422, detail="Invalid incident status")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise HTTPException(status_code=503, detail="Database is not configured")

    status_filter = ""
    parameters: list[object] = []
    if status is not None:
        status_filter = "WHERE i.status = %s"
        parameters.append(status)
    parameters.append(limit)

    try:
        with psycopg2.connect(database_url) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    f"""SELECT i.id, s.name AS service, i.title, i.description,
                              i.probable_root_cause, i.impact_assessment,
                              i.recommended_action, i.evidence, i.severity,
                              i.status, i.source, i.detected_at
                       FROM incidents AS i
                       JOIN services AS s ON s.id = i.service_id
                       {status_filter}
                       ORDER BY i.detected_at DESC, i.id DESC
                       LIMIT %s""",
                    parameters,
                )
                return [dict(row) for row in cursor.fetchall()]
    except psycopg2.Error as exc:
        raise HTTPException(status_code=503, detail="Could not read incidents") from exc
