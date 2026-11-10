from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Asset
from ..schemas import AssetCreate, AssetResponse

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post(
    "",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_asset(asset_data: AssetCreate, db: Session = Depends(get_db)) -> Asset:
    """Create an asset, returning a conflict if its identifier is already used."""
    if db.get(Asset, asset_data.asset_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An asset with this asset_id already exists.",
        )

    asset = Asset(**asset_data.model_dump())
    db.add(asset)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.get(Asset, asset_data.asset_id) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An asset with this asset_id already exists.",
            ) from None
        raise

    db.refresh(asset)
    return asset


@router.get("", response_model=list[AssetResponse])
def list_assets(db: Session = Depends(get_db)) -> list[Asset]:
    """Return all assets in identifier order."""
    return list(db.scalars(select(Asset).order_by(Asset.asset_id)).all())


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(asset_id: str, db: Session = Depends(get_db)) -> Asset:
    """Return one asset, or a not-found response if it does not exist."""
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found.",
        )
    return asset
