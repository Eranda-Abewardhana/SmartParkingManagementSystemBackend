from datetime import datetime, timedelta, time
from fastapi import APIRouter, Depends, status
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from core.database import get_db
from models.users import User
from models.zones import Zone
from models.reservations import Reservation
from models.entry_exit_logs import EntryExitLog
from models.lpr import LprDetection
from models.admin import AuditLog
from routers.auth import require_admin
from schemas.admin import (
    AdminActionType,
    ApiResponse,
    AuditLogItem,
    DashboardSummary,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _to_audit_item(item: AuditLog) -> AuditLogItem:
    return AuditLogItem.model_validate(item)


def _get_today_window() -> tuple[datetime, datetime]:
    now = datetime.now()
    today_start = datetime.combine(now.date(), time.min)
    return today_start, now


def _count_today_entries(db: Session, start_dt: datetime, end_dt: datetime) -> int:
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
    return (
        db.query(EntryExitLog)
        .filter(
            EntryExitLog.gate_type == "exit",
            EntryExitLog.timestamp >= start_dt,
            EntryExitLog.timestamp <= end_dt,
        )
        .count()
    )


def _count_vehicles_inside(db: Session, start_dt: datetime, end_dt: datetime) -> int:
    latest_per_plate = (
        db.query(
            EntryExitLog.plate_number.label("plate_number"),
            func.max(EntryExitLog.timestamp).label("max_ts"),
        )
        .filter(
            EntryExitLog.timestamp >= start_dt,
            EntryExitLog.timestamp <= end_dt,
            EntryExitLog.plate_number.isnot(None),
            EntryExitLog.plate_number != "",
        )
        .group_by(EntryExitLog.plate_number)
        .subquery()
    )

    return (
        db.query(EntryExitLog)
        .join(
            latest_per_plate,
            and_(
                EntryExitLog.plate_number == latest_per_plate.c.plate_number,
                EntryExitLog.timestamp == latest_per_plate.c.max_ts,
            ),
        )
        .filter(EntryExitLog.gate_type == "entry")
        .count()
    )


def _count_current_occupied_slots(db: Session, current_dt: datetime) -> int:
    current_date = current_dt.date()
    current_time = current_dt.time()

    occupied_rows = (
        db.query(Reservation.zone_id, Reservation.slot_number)
        .filter(
            Reservation.reservation_date == current_date,
            Reservation.start_time <= current_time,
            Reservation.end_time >= current_time,
            Reservation.slot_number.isnot(None),
            Reservation.slot_number != "",
            Reservation.status.in_(["occupied", "active"]),
        )
        .all()
    )

    unique_slots = {
        (zone_id, slot_number.strip())
        for zone_id, slot_number in occupied_rows
        if slot_number and slot_number.strip()
    }

    return len(unique_slots)


def _count_current_active_reservations(db: Session, current_dt: datetime) -> int:
    current_date = current_dt.date()
    current_time = current_dt.time()

    return (
        db.query(Reservation)
        .filter(
            Reservation.reservation_date == current_date,
            Reservation.start_time <= current_time,
            Reservation.end_time >= current_time,
            Reservation.status.in_(["pending", "confirmed", "reserved", "occupied", "active"]),
        )
        .count()
    )


def _count_today_pending_requests(db: Session, current_dt: datetime) -> int:
    current_date = current_dt.date()

    return (
        db.query(Reservation)
        .filter(
            Reservation.reservation_date == current_date,
            Reservation.status == "pending",
        )
        .count()
    )


def _count_recent_alerts(db: Session, window_minutes: int = 60) -> int:
    cutoff = datetime.now() - timedelta(minutes=window_minutes)

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
    today_start, now = _get_today_window()

    total_zones = db.query(Zone).count()
    total_capacity = db.query(func.sum(Zone.capacity)).scalar() or 0

    total_entries = _count_today_entries(db, today_start, now)
    total_exits = _count_today_exits(db, today_start, now)
    vehicles_inside = _count_vehicles_inside(db, today_start, now)

    occupied_count = _count_current_occupied_slots(db, now)
    available_count = max(total_capacity - occupied_count, 0)

    pending_requests = _count_today_pending_requests(db, now)
    active_reservations = _count_current_active_reservations(db, now)

    unmatched_lpr_count = (
        db.query(LprDetection)
        .filter(LprDetection.review_status == "unmatched")
        .count()
    )

    recent_alert_count = _count_recent_alerts(db)

    print(
        f"[DASHBOARD] range={today_start} -> {now} | "
        f"entries={total_entries}, exits={total_exits}, "
        f"inside={vehicles_inside}, occupied={occupied_count}, "
        f"available={available_count}, capacity={total_capacity}, "
        f"pending={pending_requests}, active_reservations={active_reservations}"
    )

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