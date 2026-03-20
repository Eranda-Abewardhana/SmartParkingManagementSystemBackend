from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from core.database import get_db
from models.occupancy import OccupancySnapshot
from models.zones import Zone
from models.users import User
from routers.auth import require_admin
from schemas.occupancy import (
    ApiResponse,
    OccupancyManualAdjustRequest,
    OccupancySource,
    OccupancyUpdateRequest,
    ZoneOccupancyListResponse,
    ZoneOccupancySummary,
)

router = APIRouter(prefix="/occupancy", tags=["occupancy"])


def _build_zone_summary(zone: Zone, db: Session) -> ZoneOccupancySummary:
    """
    Build zone occupancy summary from zone metadata and latest occupancy snapshot.
    """
    snapshot = db.query(OccupancySnapshot).filter(
        OccupancySnapshot.zone_id == zone.id
    ).order_by(OccupancySnapshot.updated_at.desc()).first()

    occupied_count = snapshot.occupied_count if snapshot else 0
    updated_at = snapshot.updated_at if snapshot else datetime.utcnow()
    source = snapshot.source if snapshot else OccupancySource.SYSTEM.value

    available_count = max(zone.capacity - occupied_count, 0)

    return ZoneOccupancySummary(
        zone_id=zone.id,
        zone_name=zone.name,
        zone_code=zone.code,
        occupied_count=occupied_count,
        available_count=available_count,
        total_capacity=zone.capacity,
        updated_at=updated_at,
        source=source,
        active=zone.active,
        blocked=zone.blocked,
    )


def _validate_occupied_count(zone: Zone, occupied_count: int) -> None:
    if occupied_count < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="occupied_count cannot be negative.",
        )

    if occupied_count > zone.capacity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="occupied_count cannot exceed total capacity.",
        )


@router.post(
    "/update",
    response_model=ApiResponse[ZoneOccupancySummary],
    status_code=status.HTTP_200_OK,
)
def update_occupancy(
    payload: OccupancyUpdateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Update occupancy counts for a zone.
    """
    zone = db.query(Zone).filter(Zone.id == payload.zone_id).first()
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found.",
        )

    _validate_occupied_count(zone, payload.occupied_count)

    new_snapshot = OccupancySnapshot(
        zone_id=payload.zone_id,
        occupied_count=payload.occupied_count,
        updated_at=payload.updated_at or datetime.utcnow(),
        source=payload.source.value,
    )
    db.add(new_snapshot)
    db.commit()
    db.refresh(new_snapshot)

    return ApiResponse(
        message="Zone occupancy updated successfully.",
        data=_build_zone_summary(zone, db),
    )


@router.get(
    "/zones",
    response_model=ApiResponse[ZoneOccupancyListResponse],
    status_code=status.HTTP_200_OK,
)
def get_all_zone_occupancy(db: Session = Depends(get_db)):
    """
    Return occupancy summary for all zones.
    """
    zones = db.query(Zone).all()
    items = [_build_zone_summary(zone, db) for zone in zones]

    return ApiResponse(
        message="Zone occupancy summaries retrieved successfully.",
        data=ZoneOccupancyListResponse(items=items, total=len(items)),
    )


@router.get(
    "/zones/{zone_id}",
    response_model=ApiResponse[ZoneOccupancySummary],
    status_code=status.HTTP_200_OK,
)
def get_zone_occupancy(zone_id: int, db: Session = Depends(get_db)):
    """
    Return occupancy summary for one zone.
    """
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found.",
        )

    return ApiResponse(
        message="Zone occupancy summary retrieved successfully.",
        data=_build_zone_summary(zone, db),
    )


@router.patch(
    "/zones/{zone_id}/manual-adjust",
    response_model=ApiResponse[ZoneOccupancySummary],
    status_code=status.HTTP_200_OK,
)
def manual_adjust_zone_occupancy(
    zone_id: int,
    payload: OccupancyManualAdjustRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Manually adjust occupied count for a zone.
    """
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found.",
        )

    _validate_occupied_count(zone, payload.occupied_count)

    new_snapshot = OccupancySnapshot(
        zone_id=zone_id,
        occupied_count=payload.occupied_count,
        updated_at=payload.updated_at or datetime.utcnow(),
        source=payload.source.value,
    )
    db.add(new_snapshot)
    db.commit()
    db.refresh(new_snapshot)

    return ApiResponse(
        message="Zone occupancy adjusted successfully.",
        data=_build_zone_summary(zone, db),
    )
