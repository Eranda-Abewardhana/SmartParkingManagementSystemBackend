from typing import List, Optional
from datetime import date, time, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.database import get_db
from models.zones import Zone
from models.users import User
from models.occupancy import OccupancySnapshot
from models.reservations import Reservation
from routers.auth import require_admin
from routers.reservations import _expire_past_reservations
from schemas.zones import (
    ApiResponse,
    ZoneAvailability,
    ZoneCreateRequest,
    ZoneDetail,
    ZoneListResponse,
    ZoneStatusUpdateRequest,
    ZoneSummary,
    ZoneType,
    ZoneUpdateRequest, SlotAvailability,
)

router = APIRouter(prefix="/zones", tags=["zones"])

ACTIVE_STATUSES = {"pending", "confirmed", "active"}


def _to_zone_summary(zone: Zone) -> ZoneSummary:
    return ZoneSummary.model_validate(zone)


def _to_zone_detail(zone: Zone) -> ZoneDetail:
    return ZoneDetail.model_validate(zone)


def _times_overlap(
        start_1: time,
        end_1: time,
        start_2: time,
        end_2: time,
) -> bool:
    return start_1 < end_2 and start_2 < end_1


import math
import string


def generate_slots_by_capacity(capacity: int, cols_per_row: int = 4) -> list[str]:
    slots = []
    letters = string.ascii_uppercase

    if capacity <= 0:
        return slots

    row_count = math.ceil(capacity / cols_per_row)

    for r in range(row_count):
        for c in range(1, cols_per_row + 1):
            if len(slots) >= capacity:
                break
            slots.append(f"{letters[r]}{c}")

    return slots


def _build_zone_availability_for_slot(
        zone: Zone,
        db: Session,
        reservation_date: date,
        start_time: time,
        end_time: time,
) -> ZoneAvailability:
    reservations = (
        db.query(Reservation)
        .filter(
            Reservation.zone_id == zone.id,
            Reservation.reservation_date == reservation_date,
            Reservation.status == 'confirmed',
        )
        .all()
    )

    reserved_slot_map: dict[str, Reservation] = {}

    for reservation in reservations:
        if not reservation.slot_number:
            continue

        if not reservation.start_time or not reservation.end_time:
            continue

        overlap = _times_overlap(
            reservation.start_time,
            reservation.end_time,
            start_time,
            end_time,
        )

        if not overlap:
            continue

        normalized_slot = reservation.slot_number.strip().upper()
        reserved_slot_map[normalized_slot] = reservation

    generated_slots = generate_slots_by_capacity(
        capacity=zone.capacity,
        cols_per_row=4,
    )

    slot_items = []
    for index, slot_number in enumerate(generated_slots, start=1):
        normalized_slot = slot_number.strip().upper()
        reservation = reserved_slot_map.get(normalized_slot)

        if reservation is not None:
            reservation_id = reservation.id
            slot_status = reservation.status
            is_available = False
        else:
            reservation_id = None
            slot_status = "available"
            is_available = True

        slot_items.append(
            SlotAvailability(
                slot_id=index,
                slot_number=normalized_slot,
                status=slot_status,
                is_available=is_available,
                reservation_id=reservation_id,
            )
        )

    total_slots = len(slot_items)
    available_slots = sum(1 for slot in slot_items if slot.is_available)
    occupied_slots = total_slots - available_slots

    return ZoneAvailability(
        zone_id=zone.id,
        zone_name=zone.name,
        zone_code=zone.code,
        zone_type=zone.zone_type,
        capacity=zone.capacity,
        active=zone.active,
        blocked=zone.blocked,
        reservation_date=reservation_date,
        start_time=start_time,
        end_time=end_time,
        total_slots=total_slots,
        available_slots=available_slots,
        occupied_slots=occupied_slots,
        slots=slot_items,
    )


def _build_zone_availability_now(
        zone: Zone,
        db: Session,
) -> ZoneAvailability:
    now = datetime.now()
    current_date = now.date()
    current_time = now.time().replace(microsecond=0)
    next_time = (now + timedelta(hours=1)).time().replace(microsecond=0)

    return _build_zone_availability_for_slot(
        zone=zone,
        db=db,
        reservation_date=current_date,
        start_time=current_time,
        end_time=next_time,
    )


@router.get(
    "/",
    response_model=ApiResponse[ZoneListResponse],
    status_code=status.HTTP_200_OK,
)
def list_zones(
        db: Session = Depends(get_db),
        active_only: bool = Query(default=False),
        zone_type: Optional[ZoneType] = Query(default=None),
):
    """
    List all parking zones.
    """
    query = db.query(Zone)
    if active_only:
        query = query.filter(Zone.active.is_(True))
    if zone_type:
        query = query.filter(Zone.zone_type == zone_type.value)

    zones = query.all()
    data = ZoneListResponse(
        items=[_to_zone_detail(z) for z in zones],
        total=len(zones)
    )
    return ApiResponse(
        message="Zones retrieved successfully.",
        data=data
    )


@router.get(
    "/availability/list",
    response_model=ApiResponse[List[ZoneAvailability]],
    status_code=status.HTTP_200_OK,
)
def list_zone_availabilities(
        reservation_date: date = Query(..., alias="date"),
        start_time: time = Query(...),
        end_time: time = Query(...),
        zone_type: Optional[ZoneType] = Query(default=None),
        active_only: bool = Query(default=True),
        exclude_blocked: bool = Query(default=True),
        db: Session = Depends(get_db),
):
    """
    Return availability for all zones for a selected date/time slot.
    """
    _expire_past_reservations(db)
    if start_time >= end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_time must be after start_time.",
        )

    query = db.query(Zone)

    if active_only:
        query = query.filter(Zone.active.is_(True))

    if exclude_blocked:
        query = query.filter(Zone.blocked.is_(False))

    if zone_type is not None:
        query = query.filter(Zone.zone_type == zone_type.value)

    zones = query.order_by(Zone.id.asc()).all()

    items = [
        _build_zone_availability_for_slot(
            zone=zone,
            db=db,
            reservation_date=reservation_date,
            start_time=start_time,
            end_time=end_time,
        )
        for zone in zones
    ]

    return ApiResponse(
        message="Zone availabilities retrieved successfully.",
        data=items,
    )


@router.get(
    "/{zone_id}/availability",
    response_model=ApiResponse[ZoneAvailability],
    status_code=status.HTTP_200_OK,
)
def get_zone_availability(
        zone_id: int,
        date_value: Optional[date] = Query(default=None, alias="date"),
        start_time: Optional[time] = Query(default=None),
        end_time: Optional[time] = Query(default=None),
        db: Session = Depends(get_db),
):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found.",
        )

    if not zone.active or zone.blocked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zone is not available for reservations.",
        )

    if date_value and start_time and end_time:
        if start_time >= end_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_time must be after start_time.",
            )

        availability = _build_zone_availability_for_slot(
            zone=zone,
            db=db,
            reservation_date=date_value,
            start_time=start_time,
            end_time=end_time,
        )
    else:
        availability = _build_zone_availability_now(
            zone=zone,
            db=db,
        )

    return ApiResponse(
        message="Zone availability retrieved successfully.",
        data=availability,
    )


@router.put("/{zone_id}")
def update_zone(zone_id: int, payload: ZoneUpdateRequest, db: Session = Depends(get_db)):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    zone.name = payload.name
    zone.code = payload.code
    zone.capacity = payload.capacity
    zone.active = payload.active
    zone.blocked = payload.blocked
    zone.latitude = payload.latitude
    zone.longitude = payload.longitude
    zone.description = payload.description
    zone.zone_type = payload.zone_type

    db.commit()
    db.refresh(zone)
    return ApiResponse(message="Zone updated", data=_to_zone_detail(zone))
