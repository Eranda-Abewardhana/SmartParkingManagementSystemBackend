from datetime import datetime, timedelta, date, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.database import get_db
from models.users import User
from models.zones import Zone
from models.reservations import Reservation
from models.vehicles import Vehicle
from models.entry_exit_logs import EntryExitLog
from models.lpr import LprDetection
from models.admin import AuditLog
from models.occupancy import OccupancySnapshot
from routers.auth import require_admin
from schemas.admin import (
    AdminActionType,
    ApiResponse,
    AuditLogItem,
    AuditLogListResponse,
    DashboardSummary,
    EntryDecision,
    ManualEntryDecisionRequest,
    ManualZoneReassignmentRequest,
    ResolveUnmatchedLprRequest,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _to_audit_item(item: AuditLog) -> AuditLogItem:
    return AuditLogItem.model_validate(item)


def _append_audit_log(
    db: Session,
    *,
    action_type: AdminActionType,
    admin_user_id: int,
    details: str,
) -> AuditLog:
    record = AuditLog(
        action_type=action_type.value,
        admin_user_id=admin_user_id,
        details=details,
        created_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _get_today_window() -> tuple[datetime, datetime]:
    """
    Return today's analytics window:
    00:00:00 -> now
    """
    now = datetime.now()
    today_start = datetime.combine(date.today(), time.min)
    return today_start, now


def _count_today_entries(db: Session, start_dt: datetime, end_dt: datetime) -> int:
    """
    Count all vehicle entry events within today's window.
    """
    return (
        db.query(EntryExitLog)
        .filter(
            EntryExitLog.gate_type == "entry",
            EntryExitLog.timestamp >= start_dt,
            EntryExitLog.timestamp <= end_dt,
        )
        .count()
    )


def _count_today_exits(db: Session, start_dt: datetime, end_dt: datetime) -> int:
    """
    Count all vehicle exit events within today's window.
    """
    return (
        db.query(EntryExitLog)
        .filter(
            EntryExitLog.gate_type == "exit",
            EntryExitLog.timestamp >= start_dt,
            EntryExitLog.timestamp <= end_dt,
        )
        .count()
    )

def _count_vehicles_inside(db: Session) -> int:
    """
    Count vehicles currently inside campus.
    Logic: Count plates whose last gate event was an 'entry'.
    """
    subquery = db.query(
        EntryExitLog.plate_number,
        func.max(EntryExitLog.timestamp).label("max_ts")
    ).group_by(EntryExitLog.plate_number).subquery()

    latest_logs = db.query(EntryExitLog).join(
        subquery,
        (EntryExitLog.plate_number == subquery.c.plate_number) &
        (EntryExitLog.timestamp == subquery.c.max_ts)
    ).filter(EntryExitLog.gate_type == "entry").count()

    return latest_logs


def _count_recent_alerts(db: Session, window_minutes: int = 60) -> int:
    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)

    unmatched_lpr_alerts = (
        db.query(LprDetection)
        .filter(
            LprDetection.review_status == "unmatched",
            LprDetection.detected_at >= cutoff,
        )
        .count()
    )

    denied_entry_alerts = (
        db.query(EntryExitLog)
        .filter(
            EntryExitLog.status == "denied",
            EntryExitLog.timestamp >= cutoff,
        )
        .count()
    )

    return unmatched_lpr_alerts + denied_entry_alerts


@router.get(
    "/dashboard-summary",
    response_model=ApiResponse[DashboardSummary],
    status_code=status.HTTP_200_OK,
)
def get_dashboard_summary(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Return the admin dashboard summary for today only:
    00:00:00 -> now
    """
    today = date.today()
    today_start, now = _get_today_window()

    total_zones = db.query(Zone).count()
    total_capacity = db.query(func.sum(Zone.capacity)).scalar() or 0

    latest_occupancy_subquery = (
        db.query(
            OccupancySnapshot.zone_id,
            func.max(OccupancySnapshot.updated_at).label("max_updated"),
        )
        .group_by(OccupancySnapshot.zone_id)
        .subquery()
    )

    occupied_count = (
        db.query(func.sum(OccupancySnapshot.occupied_count))
        .join(
            latest_occupancy_subquery,
            (OccupancySnapshot.zone_id == latest_occupancy_subquery.c.zone_id)
            & (OccupancySnapshot.updated_at == latest_occupancy_subquery.c.max_updated),
        )
        .scalar()
        or 0
    )

    available_count = max(total_capacity - occupied_count, 0)

    pending_requests = (
        db.query(Reservation)
        .filter(
            Reservation.status == "pending",
            Reservation.reservation_date == today,
        )
        .count()
    )

    total_entries = _count_today_entries(db, today_start, now)
    total_exits = _count_today_exits(db, today_start, now)
    
    # Calculate globally to ensure accurate counts at all times
    vehicles_inside = total_entries - total_exits

    print(total_entries, total_exits, vehicles_inside, available_count)

    active_reservations = (
        db.query(Reservation)
        .filter(Reservation.status.in_(["pending", "confirmed", "active"]))
        .count()
    )

    unmatched_lpr_count = (
        db.query(LprDetection)
        .filter(LprDetection.review_status == "unmatched")
        .count()
    )

    recent_alert_count = _count_recent_alerts(db)

    summary = DashboardSummary(
        total_zones=total_zones,
        total_capacity=total_capacity,
        occupied_count=occupied_count,
        available_count=available_count,
        active_reservations=active_reservations,
        vehicles_inside=vehicles_inside,
        unmatched_lpr_count=unmatched_lpr_count,
        recent_alert_count=recent_alert_count,
        pending_requests=pending_requests,
        total_entries=total_entries,
        total_exits=total_exits,
    )

    return ApiResponse(
        message="Dashboard summary retrieved successfully.",
        data=summary,
    )


@router.post(
    "/manual-entry-decision",
    response_model=ApiResponse[dict],
    status_code=status.HTTP_200_OK,
)
def manual_entry_decision(
    payload: ManualEntryDecisionRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin manually allows or denies vehicle entry.
    """
    if payload.reservation_id is not None:
        reservation = (
            db.query(Reservation)
            .filter(Reservation.id == payload.reservation_id)
            .first()
        )
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found.")

    decision_status = "manual_override" if payload.decision == EntryDecision.ALLOW else "denied"

    entry_log = EntryExitLog(
        plate_number=payload.plate_number,
        reservation_id=payload.reservation_id,
        gate_type="entry",
        timestamp=datetime.utcnow(),
        source="admin_manual_decision",
        status=decision_status,
        notes=payload.reason,
    )
    db.add(entry_log)

    _append_audit_log(
        db,
        action_type=AdminActionType.MANUAL_ENTRY_DECISION,
        admin_user_id=current_admin.id,
        details=f"Manual entry decision '{payload.decision.value}' for plate {payload.plate_number}.",
    )
    db.commit()
    db.refresh(entry_log)

    return ApiResponse(
        message="Manual entry decision recorded successfully.",
        data={
            "log_id": entry_log.id,
            "plate_number": payload.plate_number,
            "decision": payload.decision.value,
            "reservation_id": payload.reservation_id,
            "status": decision_status,
        },
    )


@router.post(
    "/manual-zone-reassignment",
    response_model=ApiResponse[dict],
    status_code=status.HTTP_200_OK,
)
def manual_zone_reassignment(
    payload: ManualZoneReassignmentRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Reassign a reservation to a different zone manually.
    """
    reservation = (
        db.query(Reservation)
        .filter(Reservation.id == payload.reservation_id)
        .first()
    )
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found.")

    zone = db.query(Zone).filter(Zone.id == payload.new_zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="New zone not found.")

    if not zone.active or zone.blocked:
        raise HTTPException(status_code=400, detail="New zone is not available for reassignment.")

    old_zone_id = reservation.zone_id
    reservation.zone_id = payload.new_zone_id

    _append_audit_log(
        db,
        action_type=AdminActionType.MANUAL_ZONE_REASSIGNMENT,
        admin_user_id=current_admin.id,
        details=(
            f"Reassigned reservation {payload.reservation_id} "
            f"from zone {old_zone_id} to zone {payload.new_zone_id}."
        ),
    )
    db.commit()

    return ApiResponse(
        message="Reservation reassigned successfully.",
        data={
            "reservation_id": reservation.id,
            "old_zone_id": old_zone_id,
            "new_zone_id": reservation.zone_id,
            "reason": payload.reason,
        },
    )


@router.post(
    "/resolve-unmatched-lpr",
    response_model=ApiResponse[dict],
    status_code=status.HTTP_200_OK,
)
def resolve_unmatched_lpr(
    payload: ResolveUnmatchedLprRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Resolve an unmatched LPR detection manually.
    """
    detection = (
        db.query(LprDetection)
        .filter(LprDetection.id == payload.detection_id)
        .first()
    )
    if not detection:
        raise HTTPException(status_code=404, detail="LPR detection not found.")

    if payload.vehicle_id is not None:
        vehicle = (
            db.query(Vehicle)
            .filter(
                Vehicle.id == payload.vehicle_id,
                Vehicle.is_active == True,
            )
            .first()
        )
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vehicle not found.")
        detection.matched_vehicle_id = vehicle.id
        detection.matched_user_id = vehicle.owner_user_id

    if payload.corrected_plate is not None:
        detection.corrected_plate = payload.corrected_plate
        detection.review_status = "corrected"
    elif payload.vehicle_id is not None:
        detection.review_status = "matched"

    _append_audit_log(
        db,
        action_type=AdminActionType.RESOLVE_UNMATCHED_LPR,
        admin_user_id=current_admin.id,
        details=f"Resolved LPR detection {payload.detection_id}.",
    )
    db.commit()

    return ApiResponse(
        message="Unmatched LPR detection resolved successfully.",
        data={
            "detection_id": detection.id,
            "review_status": detection.review_status,
            "matched_vehicle_id": detection.matched_vehicle_id,
            "matched_user_id": detection.matched_user_id,
            "corrected_plate": detection.corrected_plate,
            "notes": payload.notes,
        },
    )


@router.get(
    "/audit-log",
    response_model=ApiResponse[AuditLogListResponse],
    status_code=status.HTTP_200_OK,
)
def get_audit_log(
    action_type: Optional[AdminActionType] = Query(default=None),
    admin_user_id: Optional[int] = Query(default=None, ge=1),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Return admin action history.
    """
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from cannot be later than date_to.")

    query = db.query(AuditLog)

    if action_type is not None:
        query = query.filter(AuditLog.action_type == action_type.value)

    if admin_user_id is not None:
        query = query.filter(AuditLog.admin_user_id == admin_user_id)

    if date_from is not None:
        query = query.filter(AuditLog.created_at >= date_from)

    if date_to is not None:
        query = query.filter(AuditLog.created_at <= date_to)

    items = query.order_by(AuditLog.created_at.desc()).all()

    data = AuditLogListResponse(
        items=[_to_audit_item(item) for item in items],
        total=len(items),
    )

    return ApiResponse(
        message="Audit log retrieved successfully.",
        data=data,
    )
