from datetime import datetime, time, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_

from core.database import get_db
from models.entry_exit_logs import EntryExitLog
from models.vehicles import Vehicle
from models.reservations import Reservation
from models.users import User
from routers.auth import get_current_user, require_admin
from schemas.entry_exit_logs import (
    ApiResponse,
    CurrentInsideItem,
    DurationSummary,
    EntryExitLogDetail,
    EntryExitLogListResponse,
    EntryExitLogSummary,
    EntryExitStatus,
    EntryLogCreateRequest,
    ExitLogCreateRequest,
    ExitResponseDetail,
    GateType,
)

router = APIRouter(prefix="/entry-exit", tags=["entry_exit"])


def _to_log_summary(log: EntryExitLog) -> EntryExitLogSummary:
    return EntryExitLogSummary.model_validate(log)


def _to_log_detail(log: EntryExitLog) -> EntryExitLogDetail:
    return EntryExitLogDetail.model_validate(log)


def _active_reservation_for_vehicle(db: Session, vehicle_id: int, at_time: datetime) -> Optional[Reservation]:
    current_date = at_time.date()
    current_time = at_time.time()
    
    return db.query(Reservation).filter(
        Reservation.vehicle_id == vehicle_id,
        Reservation.status.in_(["pending", "confirmed", "active"]),
        Reservation.reservation_date == current_date,
        Reservation.start_time <= current_time,
        Reservation.end_time >= current_time
    ).first()


def _find_open_entry_log(db: Session, plate_number: str) -> Optional[EntryExitLog]:
    normalized = plate_number.strip().upper()
    latest_log = db.query(EntryExitLog).filter(
        EntryExitLog.plate_number == normalized
    ).order_by(desc(EntryExitLog.timestamp)).first()

    if latest_log and latest_log.gate_type == GateType.ENTRY.value:
        return latest_log
    return None


def _calculate_duration(entry_time: datetime, exit_time: datetime) -> DurationSummary:
    delta = exit_time - entry_time
    total_minutes = delta.total_seconds() / 60
    
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    formatted = f"{hours}h {minutes}m"
    if hours == 0:
        formatted = f"{minutes}m"

    return DurationSummary(
        total_minutes=round(total_minutes, 2),
        formatted_duration=formatted
    )


def _check_overstay(exit_time: datetime, reservation: Optional[Reservation]) -> bool:
    """
    Checks if a vehicle has overstayed its reservation.
    A grace period (e.g., 15 mins) can be added.
    """
    if not reservation:
        return False
    
    # Grace period in minutes
    GRACE_PERIOD = 15
    
    # Combine reservation date and end_time into a datetime for comparison
    end_datetime = datetime.combine(reservation.reservation_date, reservation.end_time)
    
    # Overstayed if exit_time is beyond reservation end time + grace period
    return exit_time > (end_datetime + timedelta(minutes=GRACE_PERIOD))


@router.post(
    "/entry",
    response_model=ApiResponse[EntryExitLogDetail],
    status_code=status.HTTP_201_CREATED,
)
def create_entry_log(payload: EntryLogCreateRequest, db: Session = Depends(get_db)):
    """
    Create an entry gate log.
    """
    timestamp = payload.timestamp or datetime.utcnow()
    normalized_plate = payload.plate_number.strip().upper()

    vehicle = db.query(Vehicle).filter(
        Vehicle.plate_number == normalized_plate,
        Vehicle.is_active == True
    ).first()

    matched_vehicle_id = None
    matched_user_id = None
    matched_reservation_id = None
    log_status = EntryExitStatus.UNMATCHED.value

    if vehicle:
        matched_vehicle_id = vehicle.id
        matched_user_id = vehicle.owner_user_id
        reservation = _active_reservation_for_vehicle(db, vehicle.id, timestamp)
        if reservation:
            matched_reservation_id = reservation.id
            log_status = EntryExitStatus.MATCHED.value
            # Optionally mark reservation as 'active' on entry
            reservation.status = "active"
            db.commit()

    new_log = EntryExitLog(
        plate_number=normalized_plate,
        vehicle_id=matched_vehicle_id,
        user_id=matched_user_id,
        reservation_id=matched_reservation_id,
        gate_type=GateType.ENTRY.value,
        timestamp=timestamp,
        source=payload.source,
        status=log_status,
        notes=payload.notes,
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)

    return ApiResponse(
        message="Entry log created successfully.",
        data=_to_log_detail(new_log),
    )


@router.post(
    "/exit",
    response_model=ApiResponse[ExitResponseDetail],
    status_code=status.HTTP_201_CREATED,
)
def create_exit_log(payload: ExitLogCreateRequest, db: Session = Depends(get_db)):
    """
    Create an exit gate log, calculate duration, and check for overstay.
    """
    from datetime import timedelta # Explicit import for the check
    timestamp = payload.timestamp or datetime.utcnow()
    normalized_plate = payload.plate_number.strip().upper()

    vehicle = db.query(Vehicle).filter(
        Vehicle.plate_number == normalized_plate,
        Vehicle.is_active == True
    ).first()
    
    open_entry = _find_open_entry_log(db, normalized_plate)

    matched_vehicle_id = None
    matched_user_id = None
    matched_reservation_id = None
    log_status = EntryExitStatus.UNMATCHED.value
    duration = None
    entry_summary = None
    is_overstayed = False

    # 1. Handle matching and duration
    if open_entry:
        matched_vehicle_id = open_entry.vehicle_id
        matched_user_id = open_entry.user_id
        matched_reservation_id = open_entry.reservation_id
        log_status = EntryExitStatus.MATCHED.value
        duration = _calculate_duration(open_entry.timestamp, timestamp)
        entry_summary = _to_log_summary(open_entry)

    # 2. Check for overstay if there was a reservation
    if matched_reservation_id:
        res = db.query(Reservation).filter(Reservation.id == matched_reservation_id).first()
        if res:
            # Re-calculating using helper
            GRACE_PERIOD = 15
            end_dt = datetime.combine(res.reservation_date, res.end_time)
            if timestamp > (end_dt + timedelta(minutes=GRACE_PERIOD)):
                is_overstayed = True
            
            # Mark reservation as completed
            res.status = "completed"

    elif vehicle:
        matched_vehicle_id = vehicle.id
        matched_user_id = vehicle.owner_user_id

    new_log = EntryExitLog(
        plate_number=normalized_plate,
        vehicle_id=matched_vehicle_id,
        user_id=matched_user_id,
        reservation_id=matched_reservation_id,
        gate_type=GateType.EXIT.value,
        timestamp=timestamp,
        source=payload.source,
        status=log_status,
        is_overstayed=is_overstayed,
        notes=payload.notes,
    )
    
    if is_overstayed:
        overstay_msg = f"Overstayed detected. Exit time: {timestamp.strftime('%H:%M')}"
        new_log.notes = f"{new_log.notes or ''} | {overstay_msg}".strip(" | ")

    db.add(new_log)
    db.commit()
    db.refresh(new_log)

    return ApiResponse(
        message="Exit log created successfully.",
        data=ExitResponseDetail(
            exit_log=_to_log_summary(new_log),
            entry_log=entry_summary,
            duration=duration
        ),
    )


@router.get(
    "/overstayed",
    response_model=ApiResponse[EntryExitLogListResponse],
    status_code=status.HTTP_200_OK,
)
def list_overstayed_vehicles(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Admin only. Return all exit logs marked as overstayed.
    """
    logs = db.query(EntryExitLog).filter(EntryExitLog.is_overstayed == True).order_by(desc(EntryExitLog.timestamp)).all()
    
    return ApiResponse(
        message="Overstayed logs retrieved successfully.",
        data=EntryExitLogListResponse(items=[_to_log_summary(l) for l in logs], total=len(logs)),
    )


@router.get(
    "/logs",
    response_model=ApiResponse[EntryExitLogListResponse],
    status_code=status.HTTP_200_OK,
)
def list_entry_exit_logs(
    plate_number: Optional[str] = Query(default=None),
    gate_type: Optional[GateType] = Query(default=None),
    status_filter: Optional[EntryExitStatus] = Query(default=None, alias="status"),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from cannot be later than date_to.")

    query = db.query(EntryExitLog)

    if plate_number:
        query = query.filter(EntryExitLog.plate_number.ilike(f"%{plate_number.strip()}%"))

    if gate_type is not None:
        query = query.filter(EntryExitLog.gate_type == gate_type.value)

    if status_filter is not None:
        query = query.filter(EntryExitLog.status == status_filter.value)

    if date_from is not None:
        query = query.filter(EntryExitLog.timestamp >= date_from)

    if date_to is not None:
        query = query.filter(EntryExitLog.timestamp <= date_to)

    total = query.count()
    logs = query.order_by(desc(EntryExitLog.timestamp)).all()

    data = EntryExitLogListResponse(
        items=[_to_log_summary(log) for log in logs],
        total=total,
    )

    return ApiResponse(
        message="Entry/exit logs retrieved successfully.",
        data=data,
    )
@router.get(
    "/current-inside",
    response_model=ApiResponse[List[CurrentInsideItem]],
    status_code=status.HTTP_200_OK,
)
def get_current_inside(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Admin only. Return vehicles currently inside campus.
    """
    subq = db.query(
        EntryExitLog.plate_number,
        func.max(EntryExitLog.timestamp).label("max_ts")
    ).group_by(EntryExitLog.plate_number).subquery()

    latest_logs = db.query(EntryExitLog).join(
        subq,
        (EntryExitLog.plate_number == subq.c.plate_number) &
        (EntryExitLog.timestamp == subq.c.max_ts)
    ).filter(EntryExitLog.gate_type == GateType.ENTRY.value).order_by(desc(EntryExitLog.timestamp)).all()

    current_inside_items = [
        CurrentInsideItem(
            plate_number=log.plate_number,
            vehicle_id=log.vehicle_id,
            user_id=log.user_id,
            reservation_id=log.reservation_id,
            entry_log_id=log.id,
            entered_at=log.timestamp,
            source=log.source,
            status=log.status,
            notes=log.notes,
        )
        for log in latest_logs
    ]

    return ApiResponse(
        message="Current vehicles inside retrieved successfully.",
        data=current_inside_items,
    )


@router.get(
    "/{log_id}",
    response_model=ApiResponse[EntryExitLogDetail],
    status_code=status.HTTP_200_OK,
)
def get_entry_exit_log(
    log_id: int, 
    _: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Admin only. Return one gate log record by ID.
    """
    log = db.query(EntryExitLog).filter(EntryExitLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Entry/exit log not found.")

    return ApiResponse(
        message="Entry/exit log retrieved successfully.",
        data=_to_log_detail(log),
    )
