from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Alert, AlertAcknowledgementHistory, Asset, Inspection
from ..schemas import (
    AcknowledgementCreate,
    AcknowledgementResponse,
    OpenAlertResponse,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/open", response_model=list[OpenAlertResponse])
def list_open_alerts(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    """Return open alerts with related asset and temperature details."""
    rows = db.execute(
        select(Alert, Asset.asset_id, Inspection.max_temp_C, Inspection.mean_temp_C)
        .join(Inspection, Alert.inspection_id == Inspection.id)
        .join(Asset, Inspection.asset_id == Asset.asset_id)
        .where(Alert.status == "open")
        .order_by(Alert.created_at.desc(), Alert.id.desc())
    ).all()

    return [
        {
            "id": alert.id,
            "inspection_id": alert.inspection_id,
            "severity": alert.severity,
            "status": alert.status,
            "created_at": alert.created_at,
            "asset_id": asset_id,
            "max_temp_C": max_temp,
            "mean_temp_C": mean_temp,
        }
        for alert, asset_id, max_temp, mean_temp in rows
    ]


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AcknowledgementResponse,
)
def acknowledge_alert(
    alert_id: int,
    acknowledgement: AcknowledgementCreate,
    db: Session = Depends(get_db),
) -> AcknowledgementResponse:
    """Acknowledge an open alert and save its audit record atomically."""
    acknowledged_at = datetime.now(timezone.utc)

    with db.begin():
        result = db.execute(
            update(Alert)
            .where(Alert.id == alert_id, Alert.status == "open")
            .values(status="acknowledged")
        )

        if result.rowcount != 1:
            alert = db.get(Alert, alert_id)
            if alert is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Alert not found.",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Alert has already been acknowledged.",
            )

        history = AlertAcknowledgementHistory(
            alert_id=alert_id,
            acknowledged_by=acknowledgement.acknowledged_by,
            acknowledged_at=acknowledged_at,
            previous_status="open",
            new_status="acknowledged",
        )
        db.add(history)
        db.flush()

        response = AcknowledgementResponse(
            alert_id=history.alert_id,
            acknowledged_by=history.acknowledged_by,
            acknowledged_at=acknowledged_at,
            previous_status=history.previous_status,
            new_status=history.new_status,
        )

    return response
