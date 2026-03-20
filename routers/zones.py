from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.database import get_db
from models.zones import Zone
from models.users import User
from models.occupancy import OccupancySnapshot
from models.reservations import Reservation
from routers.auth import require_admin
from schemas.zones import (
    ApiResponse,
    ZoneAvailability,
    ZoneCreateRequest,
    ZoneDetail,
    ZoneListResponse,
    ZoneStatusUpdateRequest,
    ZoneSummary,
    ZoneType,
    ZoneUpdateRequest,
)

router = APIRouter(prefix="/zones", tags=["zones"])


def _to_zone_summary(zone: Zone) -> ZoneSummary:
    return ZoneSummary.model_validate(zone)


def _to_zone_detail(zone: Zone) -> ZoneDetail:
    return ZoneDetail.model_validate(zone)


def _build_zone_availability(zone: Zone, db: Session) -> ZoneAvailability:
    """
    Build availability payload for a zone by calculating real-time occupancy
    and current active reservations.
    """
    # 1. Get latest occupancy snapshot
    latest_snapshot = db.query(OccupancySnapshot).filter(
        OccupancySnapshot.zone_id == zone.id
    ).order_by(OccupancySnapshot.updated_at.desc()).first()
    
    occupied_count = latest_snapshot.occupied_count if latest_snapshot else 0

    # 2. Get count of confirmed/active reservations for the current time
    now = datetime.utcnow()
    reserved_count = db.query(Reservation).filter(
        Reservation.zone_id == zone.id,
        Reservation.status.in_(["confirmed", "active"]),
        Reservation.reservation_date == now.date(),
        Reservation.start_time <= now.time(),
        Reservation.end_time >= now.time()
    ).count()

    # 3. Calculate remaining capacity
    available_count = max(zone.capacity - occupied_count - reserved_count, 0)

    return ZoneAvailability(
        zone_id=zone.id,
        zone_name=zone.name,
        code=zone.code,
        capacity=zone.capacity,
        occupied_count=occupied_count,
        reserved_count=reserved_count,
        available_count=available_count,
        active=zone.active,
        blocked=zone.blocked,
    )


@router.post(
    "/",
    response_model=ApiResponse[ZoneDetail],
    status_code=status.HTTP_201_CREATED,
)
def create_zone(
    payload: ZoneCreateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Create a new parking zone. Admin only.
    """
    existing = db.query(Zone).filter(
        Zone.code == payload.code.strip().upper()
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A zone with this code already exists.",
        )

    new_zone = Zone(
        name=payload.name,
        code=payload.code.strip().upper(),
        zone_type=payload.zone_type.value,
        capacity=payload.capacity,
        active=payload.active,
        blocked=payload.blocked,
        description=payload.description,
    )

    db.add(new_zone)
    db.commit()
    db.refresh(new_zone)

    return ApiResponse(
        message="Zone created successfully.",
        data=_to_zone_detail(new_zone),
    )


@router.get(
    "/",
    response_model=ApiResponse[ZoneListResponse],
    status_code=status.HTTP_200_OK,
)
def list_zones(
    active: Optional[bool] = Query(default=None),
    blocked: Optional[bool] = Query(default=None),
    zone_type: Optional[ZoneType] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    List all parking zones with optional filters.
    """
    query = db.query(Zone)

    if active is not None:
        query = query.filter(Zone.active == active)

    if blocked is not None:
        query = query.filter(Zone.blocked == blocked)

    if zone_type is not None:
        query = query.filter(Zone.zone_type == zone_type.value)

    zones = query.all()

    data = ZoneListResponse(
        items=[_to_zone_summary(zone) for zone in zones],
        total=len(zones),
    )

    return ApiResponse(
        message="Zones retrieved successfully.",
        data=data,
    )


@router.get(
    "/{zone_id}",
    response_model=ApiResponse[ZoneDetail],
    status_code=status.HTTP_200_OK,
)
def get_zone(zone_id: int, db: Session = Depends(get_db)):
    """
    Return zone details by ID.
    """
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found.",
        )

    return ApiResponse(
        message="Zone retrieved successfully.",
        data=_to_zone_detail(zone),
    )


@router.put(
    "/{zone_id}",
    response_model=ApiResponse[ZoneDetail],
    status_code=status.HTTP_200_OK,
)
def update_zone(
    zone_id: int,
    payload: ZoneUpdateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Update a parking zone. Admin only.
    """
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update.",
        )

    if "code" in update_data:
        new_code = update_data["code"].strip().upper()
        duplicate = db.query(Zone).filter(
            Zone.code == new_code,
            Zone.id != zone_id
        ).first()
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A zone with this code already exists.",
            )
        zone.code = new_code

    if "zone_type" in update_data:
        zone.zone_type = update_data["zone_type"].value

    for field in ["name", "capacity", "active", "blocked", "description"]:
        if field in update_data:
            setattr(zone, field, update_data[field])

    db.commit()
    db.refresh(zone)

    return ApiResponse(
        message="Zone updated successfully.",
        data=_to_zone_detail(zone),
    )


@router.patch(
    "/{zone_id}/status",
    response_model=ApiResponse[ZoneDetail],
    status_code=status.HTTP_200_OK,
)
def update_zone_status(
    zone_id: int,
    payload: ZoneStatusUpdateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Update zone active/blocked state. Admin only.
    """
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No status fields provided for update.",
        )

    if "active" in update_data:
        zone.active = update_data["active"]

    if "blocked" in update_data:
        zone.blocked = update_data["blocked"]

    db.commit()
    db.refresh(zone)

    return ApiResponse(
        message="Zone status updated successfully.",
        data=_to_zone_detail(zone),
    )


@router.get(
    "/{zone_id}/availability",
    response_model=ApiResponse[ZoneAvailability],
    status_code=status.HTTP_200_OK,
)
def get_zone_availability(zone_id: int, db: Session = Depends(get_db)):
    """
    Return zone availability summary.
    """
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found.",
        )

    availability = _build_zone_availability(zone, db)

    return ApiResponse(
        message="Zone availability retrieved successfully.",
        data=availability,
    )
