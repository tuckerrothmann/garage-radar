"""
Alerts router

GET  /alerts               — paginated list, filterable by status/severity/type
GET  /alerts/{id}          — single alert
PATCH /alerts/{id}/status  — set status to "read" or "dismissed"
POST  /alerts/dismiss-all  — bulk dismiss all open/read alerts (convenience)
"""
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select, update

from garage_radar.api.deps import DBSession
from garage_radar.api.schemas import AlertOut, AlertPage, AlertStatusPatch
from garage_radar.db.models import (
    Alert,
    AlertSeverityEnum,
    AlertStatusEnum,
    AlertTypeEnum,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])

_MAX_LIMIT = 200
_ALLOWED_STATUS_TRANSITIONS = {
    AlertStatusEnum.open: {AlertStatusEnum.read, AlertStatusEnum.dismissed},
    AlertStatusEnum.read: {AlertStatusEnum.dismissed},
    AlertStatusEnum.dismissed: set(),
}


@router.get("", response_model=AlertPage)
async def list_alerts(
    session: DBSession,
    status: Optional[str] = Query("open", description="open | read | dismissed"),
    severity: Optional[str] = Query(None, description="info | watch | act"),
    alert_type: Optional[str] = Query(None),
    listing_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> AlertPage:
    """Return alerts, most recent first. Default: open only."""
    stmt = select(Alert)

    if status:
        try:
            stmt = stmt.where(Alert.status == AlertStatusEnum(status))
        except ValueError:
            raise HTTPException(400, f"Invalid status '{status}'")
    if severity:
        try:
            stmt = stmt.where(Alert.severity == AlertSeverityEnum(severity))
        except ValueError:
            raise HTTPException(400, f"Invalid severity '{severity}'")
    if alert_type:
        try:
            stmt = stmt.where(Alert.alert_type == AlertTypeEnum(alert_type))
        except ValueError:
            raise HTTPException(400, f"Invalid alert_type '{alert_type}'")
    if listing_id is not None:
        stmt = stmt.where(Alert.listing_id == listing_id)

    total = (await session.scalar(select(func.count()).select_from(stmt.subquery()))) or 0
    stmt = stmt.order_by(Alert.triggered_at.desc()).offset(offset).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()

    return AlertPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[AlertOut.model_validate(r) for r in rows],
    )


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(alert_id: uuid.UUID, session: DBSession) -> AlertOut:
    """Return a single alert by ID."""
    row = await session.get(Alert, alert_id)
    if row is None:
        raise HTTPException(404, "Alert not found")
    return AlertOut.model_validate(row)


@router.patch("/{alert_id}/status", response_model=AlertOut)
async def patch_alert_status(
    alert_id: uuid.UUID,
    body: AlertStatusPatch,
    session: DBSession,
) -> AlertOut:
    """
    Transition an alert's status.

    Allowed transitions:
      open → read | dismissed
      read → dismissed
      dismissed → (no further transitions)
    """
    row = await session.get(Alert, alert_id)
    if row is None:
        raise HTTPException(404, "Alert not found")

    try:
        new_status = AlertStatusEnum(body.status)
    except ValueError:
        raise HTTPException(400, f"Invalid status '{body.status}'")

    allowed = _ALLOWED_STATUS_TRANSITIONS.get(row.status, set())
    if new_status not in allowed:
        raise HTTPException(
            422,
            f"Cannot transition alert from '{row.status.value}' to '{new_status.value}'",
        )

    row.status = new_status
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return AlertOut.model_validate(row)


@router.post("/dismiss-all", response_model=dict)
async def dismiss_all_alerts(session: DBSession) -> dict:
    """
    Bulk-dismiss all open and read alerts.
    Returns the count of alerts dismissed.
    """
    result = await session.execute(
        update(Alert)
        .where(Alert.status.in_([AlertStatusEnum.open, AlertStatusEnum.read]))
        .values(status=AlertStatusEnum.dismissed)
        .returning(Alert.id)
    )
    dismissed = len(result.fetchall())
    await session.commit()
    return {"dismissed": dismissed}
