from datetime import date, time, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from core.database import get_db
from models.reservations import Reservation
from models.vehicles import Vehicle
from models.zones import Zone
from models.users import User
from routers.auth import get_current_user, require_admin
from schemas.reservations import (
    ApiResponse,
    ReservationCancelRequest,
    ReservationDetail,
    ReservationListResponse,
    ReservationRescheduleRequest,
    ReservationStatus,
    ReservationStatusUpdateRequest,
    ReservationSummary, ReservationCreateRequest,
)

router = APIRouter(prefix="/reservations", tags=["reservations"])

ACTIVE_STATUSES = {
    ReservationStatus.PENDING.value,
    ReservationStatus.CONFIRMED.value,
    ReservationStatus.RESERVED.value,
    ReservationStatus.OCCUPIED.value,
}


def _to_reservation_summary(reservation: Reservation) -> ReservationSummary:
    return ReservationSummary.model_validate(reservation)


def _to_reservation_detail(
        reservation: Reservation,
        vehicalNo: Optional[str] = None,
        username: Optional[str] = None,
        zone_name: Optional[str] = None,
) -> ReservationDetail:
    return ReservationDetail(
        id=reservation.id,
        start_time=reservation.start_time.strftime("%H:%M:%S") if reservation.start_time else None,
        end_time=reservation.end_time.strftime("%H:%M:%S") if reservation.end_time else None,
        user_id=reservation.user_id,
        status=reservation.status,
        notes=reservation.notes,
        vehicle_id=reservation.vehicle_id,
        zone_id=reservation.zone_id,
        vehicalNo=vehicalNo,
        username=username,
        zone_name=zone_name,
        slot_number=reservation.slot_number,
        reservation_date=reservation.reservation_date.strftime("%Y-%m-%d") if reservation.reservation_date else None,
    )


def _ensure_owner_or_admin(reservation: Reservation, current_user: User) -> None:
    if (
            reservation.user_id != current_user.id
            and current_user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this reservation.",
        )


def _times_overlap(start_1: time, end_1: time, start_2: time, end_2: time) -> bool:
    return start_1 < end_2 and start_2 < end_1


def _validate_vehicle_belongs_to_user(db: Session, vehicle_id: int, user_id: int) -> Vehicle:
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.is_active == True).first()
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with ID {vehicle_id} not found or inactive.",
        )
    if vehicle.owner_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Vehicle {vehicle.plate_number} (Owner: {vehicle.owner_user_id}) does not belong to target user (ID: {user_id}).",
        )
    return vehicle


def _validate_zone_for_booking(db: Session, zone_id: int) -> Zone:
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone with ID {zone_id} not found.",
        )
    if not zone.active or zone.blocked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Zone '{zone.name}' is currently not available for booking.",
        )
    return zone


def _check_overlapping_reservation_for_user_or_vehicle(
        db: Session,
        *,
        user_id: int,
        vehicle_id: int,
        reservation_date: date,
        start_time: time,
        end_time: time,
        exclude_reservation_id: Optional[int] = None,
) -> None:
    query = db.query(Reservation).filter(
        Reservation.status.in_(ACTIVE_STATUSES),
        Reservation.reservation_date == reservation_date
    )

    if exclude_reservation_id:
        query = query.filter(Reservation.id != exclude_reservation_id)

    overlaps = query.filter(
        or_(Reservation.user_id == user_id, Reservation.vehicle_id == vehicle_id)
    ).all()

    for r in overlaps:
        if _times_overlap(start_time, end_time, r.start_time, r.end_time):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Overlapping reservation exists ({r.start_time.strftime('%H:%M')} - {r.end_time.strftime('%H:%M')}).",
            )


def _check_zone_capacity_rules(
        db: Session,
        *,
        zone_id: int,
        reservation_date: date,
        start_time: time,
        end_time: time,
        exclude_reservation_id: Optional[int] = None,
) -> None:
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    query = db.query(Reservation).filter(
        Reservation.zone_id == zone_id,
        Reservation.status.in_(ACTIVE_STATUSES),
        Reservation.reservation_date == reservation_date
    )

    if exclude_reservation_id:
        query = query.filter(Reservation.id != exclude_reservation_id)

    reservations = query.all()

    overlapping_count = 0
    for r in reservations:
        if _times_overlap(start_time, end_time, r.start_time, r.end_time):
            overlapping_count += 1

    if overlapping_count >= zone.capacity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Zone capacity reached ({overlapping_count}/{zone.capacity}) for this time range.",
        )


@router.get(
    "/",
    response_model=ApiResponse[ReservationListResponse],
    status_code=status.HTTP_200_OK,
)
def list_all_reservations(
        status_filter: Optional[ReservationStatus] = Query(default=None, alias="status"),
        zone_id: Optional[int] = Query(default=None, ge=1),
        user_id: Optional[int] = Query(default=None, ge=1),
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    query = db.query(Reservation).join(Vehicle, Reservation.vehicle_id == Vehicle.id).join(User,
                                                                                           Reservation.user_id == User.id).join(
        Zone, Reservation.zone_id == Zone.id)

    if current_user.role != 'admin':
        query = query.filter(Reservation.user_id == current_user.id)
    else:
        if status_filter is not None:
            query = query.filter(Reservation.status == status_filter.value)
        if zone_id is not None:
            query = query.filter(Reservation.zone_id == zone_id)
        if user_id is not None:
            query = query.filter(Reservation.user_id == user_id)
        if date_from is not None:
            query = query.filter(Reservation.reservation_date >= date_from)
        if date_to is not None:
            query = query.filter(Reservation.reservation_date <= date_to)

    results = query.add_columns(
        Vehicle.plate_number,
        User.username,
        Zone.name.label("zone_name")
    ).all()

    reservation_items = [
        _to_reservation_detail(r, plate_number, username, zone_name)
        for r, plate_number, username, zone_name in results
    ]

    return ApiResponse(
        message="Reservations retrieved successfully.",
        data=ReservationListResponse(
            items=reservation_items,
            total=len(reservation_items)
        )
    )


@router.post(
    "/",
    response_model=ApiResponse[ReservationDetail],
    status_code=status.HTTP_201_CREATED,
)
def create_reservation(
        payload: ReservationCreateRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """
    Create a reservation. Admins can specify user_id to book for others.
    """
    # 1. Access Control & Target User
    target_user_id = current_user.id
    payload_user_id = getattr(payload, 'user_id', None)

    if payload_user_id and payload_user_id != current_user.id:
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Non-admin users cannot book for others.",
            )
        target_user_id = payload_user_id

    # 2. Validations
    _validate_vehicle_belongs_to_user(db, payload.vehicle_id, target_user_id)
    _validate_zone_for_booking(db, payload.zone_id)

    _check_overlapping_reservation_for_user_or_vehicle(
        db,
        user_id=target_user_id,
        vehicle_id=payload.vehicle_id,
        reservation_date=payload.reservation_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )

    _check_zone_capacity_rules(
        db,
        zone_id=payload.zone_id,
        reservation_date=payload.reservation_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )

    # 3. Persistence
    new_reservation = Reservation(
        user_id=target_user_id,
        vehicle_id=payload.vehicle_id,
        zone_id=payload.zone_id,
        reservation_date=payload.reservation_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status=ReservationStatus.RESERVED.value if current_user.role == "admin" else ReservationStatus.PENDING.value,
        notes=payload.notes,
        slot_number=payload.slot_number
    )

    db.add(new_reservation)
    db.commit()
    db.refresh(new_reservation)

    return ApiResponse(
        message="Reservation successfully created.",
        data=_to_reservation_detail(new_reservation),
    )

@router.post("/cleanup-expired", response_model=ApiResponse)
def cleanup_expired_reservations(
        days: int = Query(default=30, ge=1, le=365),
        _: User = Depends(require_admin),
        db: Session = Depends(get_db)
):
    """
    Admin only. Cleanup past unused reservations.
    """
    now = datetime.utcnow()
    today = now.date()
    current_time = now.time()

    expired_count = db.query(Reservation).filter(
        Reservation.status.in_([ReservationStatus.PENDING.value, ReservationStatus.CONFIRMED.value]),
        or_(
            Reservation.reservation_date < today,
            and_(
                Reservation.reservation_date == today,
                Reservation.end_time < current_time
            )
        ),
        Reservation.reservation_date >= today - timedelta(days=days)
    ).update(
        {"status": ReservationStatus.EXPIRED.value},
        synchronize_session=False
    )

    db.commit()

    return ApiResponse(
        message=f"Cleanup completed. {expired_count} unused reservations marked as expired.",
        data={"count": expired_count}
    )


@router.get(
    "/me",
    response_model=ApiResponse[ReservationListResponse],
    status_code=status.HTTP_200_OK,
)
def get_my_reservations(
        status_filter: Optional[ReservationStatus] = Query(default=None, alias="status"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    query = (
        db.query(Reservation)
        .join(Vehicle, Reservation.vehicle_id == Vehicle.id)
        .join(Zone, Reservation.zone_id == Zone.id)
        .filter(Reservation.user_id == current_user.id)
    )

    if status_filter is not None:
        query = query.filter(Reservation.status == status_filter.value)

    results = query.add_columns(
        Vehicle.plate_number,
        Zone.name,
    ).all()

    reservation_items = [
        _to_reservation_detail(
            reservation,
            vehicalNo=vehicle_plate,
            zone_name=zone_name,
        )
        for reservation, vehicle_plate, zone_name in results
    ]

    return ApiResponse(
        message="Your reservations retrieved successfully.",
        data=ReservationListResponse(
            items=reservation_items,
            total=len(reservation_items),
        ),
    )


@router.get(
    "/{reservation_id}",
    response_model=ApiResponse[ReservationDetail],
    status_code=status.HTTP_200_OK,
)
def get_reservation(
        reservation_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found.")

    _ensure_owner_or_admin(reservation, current_user)
    return ApiResponse(message="Reservation details retrieved.", data=_to_reservation_detail(reservation))


@router.patch(
    "/{reservation_id}/cancel",
    response_model=ApiResponse[ReservationDetail],
    status_code=status.HTTP_200_OK,
)
def cancel_reservation(
        reservation_id: int,
        payload: ReservationCancelRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found.")

    _ensure_owner_or_admin(reservation, current_user)

    if reservation.status not in {ReservationStatus.PENDING.value, ReservationStatus.CONFIRMED.value}:
        raise HTTPException(status_code=400, detail="Only pending or confirmed reservations can be cancelled.")

    reservation.status = ReservationStatus.CANCELLED.value
    if payload.reason:
        reservation.notes = f"{reservation.notes or ''} | Cancelled: {payload.reason}"

    db.commit()
    db.refresh(reservation)

    return ApiResponse(message="Reservation successfully cancelled.", data=_to_reservation_detail(reservation))


@router.patch(
    "/{reservation_id}/status",
    response_model=ApiResponse[ReservationDetail],
    status_code=status.HTTP_200_OK,
)
def update_reservation_status(
        reservation_id: int,
        payload: ReservationStatusUpdateRequest,
        _: User = Depends(require_admin),
        db: Session = Depends(get_db),
):
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found.")

    reservation.status = payload.status.value
    db.commit()
    db.refresh(reservation)

    return ApiResponse(message="Reservation status updated successfully.", data=_to_reservation_detail(reservation))

def _expire_past_reservations(db: Session):
    from datetime import datetime

    now = datetime.now()

    reservations = db.query(Reservation).filter(
        Reservation.status.in_([
            ReservationStatus.PENDING.value,
            ReservationStatus.CONFIRMED.value,
            ReservationStatus.OCCUPIED.value,
        ])
    ).all()

    updated = 0

    for r in reservations:
        if r.reservation_date and r.end_time:
            end_dt = datetime.combine(r.reservation_date, r.end_time)

            if end_dt <= now:
                r.status = ReservationStatus.EXPIRED.value
                updated += 1

    if updated > 0:
        db.commit()

    print(f"EXPIRED {updated} RESERVATIONS")