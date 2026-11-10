from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Alert, Asset, Inspection
from ..schemas import InspectionCreate, InspectionResponse

router = APIRouter(tags=["inspections"])


def _matches_inspection(
    inspection: Inspection,
    inspection_data: InspectionCreate,
) -> bool:
    return (
        inspection.max_temp_C == inspection_data.max_temp_C
        and inspection.mean_temp_C == inspection_data.mean_temp_C
        and inspection.image_ref == inspection_data.image_ref
    )


def _find_existing_inspection(
    db: Session,
    inspection_data: InspectionCreate,
) -> Inspection | None:
    return db.scalar(
        select(Inspection).where(
            Inspection.asset_id == inspection_data.asset_id,
            Inspection.timestamp == inspection_data.timestamp,
        )
    )


def _return_existing_inspection(
    inspection: Inspection,
    inspection_data: InspectionCreate,
    response: Response,
) -> Inspection:
    if not _matches_inspection(inspection, inspection_data):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An inspection with this asset_id and timestamp has different data.",
        )
    response.status_code = status.HTTP_200_OK
    return inspection


@router.post(
    "/inspections",
    response_model=InspectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_inspection(
    inspection_data: InspectionCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> Inspection:
    """Save an inspection and create at most one alert in the same transaction."""
    try:
        with db.begin():
            asset = db.get(Asset, inspection_data.asset_id)
            if asset is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Asset not found.",
                )

            existing = _find_existing_inspection(db, inspection_data)
            if existing is not None:
                return _return_existing_inspection(existing, inspection_data, response)

            inspection = Inspection(**inspection_data.model_dump())
            db.add(inspection)
            db.flush()

            if inspection.max_temp_C >= asset.critical_limit_C:
                db.add(Alert(inspection_id=inspection.id, severity="critical"))
            elif inspection.max_temp_C >= asset.warning_limit_C:
                db.add(Alert(inspection_id=inspection.id, severity="warning"))

        db.refresh(inspection)
        return inspection
    except IntegrityError:
        db.rollback()
        existing = _find_existing_inspection(db, inspection_data)
        if existing is None:
            raise
        return _return_existing_inspection(existing, inspection_data, response)


@router.get(
    "/assets/{asset_id}/inspections",
    response_model=list[InspectionResponse],
)
def list_asset_inspections(
    asset_id: str,
    db: Session = Depends(get_db),
) -> Sequence[Inspection]:
    """Return one asset's inspections from newest to oldest."""
    if db.get(Asset, asset_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found.",
        )

    return db.scalars(
        select(Inspection)
        .where(Inspection.asset_id == asset_id)
        .order_by(Inspection.timestamp.desc(), Inspection.id.desc())
    ).all()
