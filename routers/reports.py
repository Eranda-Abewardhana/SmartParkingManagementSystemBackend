import csv
import io
from datetime import datetime, timedelta
from typing import List, Optional
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from core.database import get_db
from models.entry_exit_logs import EntryExitLog
from models.reservations import Reservation
from models.zones import Zone
from models.users import User
from routers.auth import require_admin
from schemas.auth import ApiResponse
from pydantic import BaseModel

router = APIRouter(prefix="/reports", tags=["reports"])

class ExportFormat(str, Enum):
    CSV = "csv"
    JSON = "json"

class PeakHourItem(BaseModel):
    hour: int
    count: int

class ReportSummary(BaseModel):
    total_entries: int
    total_reservations: int
    peak_hours: List[PeakHourItem]

# --- Peak Hour Analysis Logic ---
def _get_peak_hour_data(db: Session, date_from: datetime, date_to: datetime) -> List[PeakHourItem]:
    """
    Analyzes entry logs to find peak hours within a date range.
    """
    results = db.query(
        extract('hour', EntryExitLog.timestamp).label('hour'),
        func.count(EntryExitLog.id).label('count')
    ).filter(
        EntryExitLog.gate_type == "entry",
        EntryExitLog.timestamp >= date_from,
        EntryExitLog.timestamp <= date_to
    ).group_by('hour').order_by('hour').all()

    return [PeakHourItem(hour=int(r.hour), count=r.count) for r in results]

# --- API Endpoints ---

@router.get("/summary", response_model=ApiResponse[ReportSummary])
def get_report_summary(
    date_from: datetime = Query(
        ..., 
        description="Start date and time in ISO format (YYYY-MM-DDTHH:MM:SS)",
        examples=["2023-10-01T00:00:00"]
    ),
    date_to: datetime = Query(
        ..., 
        description="End date and time in ISO format (YYYY-MM-DDTHH:MM:SS)",
        examples=["2023-10-31T23:59:59"]
    ),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Returns a summary of activity and peak hour analysis for the dashboard.
    """
    total_entries = db.query(EntryExitLog).filter(
        EntryExitLog.gate_type == "entry",
        EntryExitLog.timestamp >= date_from,
        EntryExitLog.timestamp <= date_to
    ).count()

    total_res = db.query(Reservation).filter(
        Reservation.reservation_date >= date_from.date(),
        Reservation.reservation_date <= date_to.date()
    ).count()

    peak_hours = _get_peak_hour_data(db, date_from, date_to)

    return ApiResponse(
        message="Report summary generated successfully.",
        data=ReportSummary(
            total_entries=total_entries,
            total_reservations=total_res,
            peak_hours=peak_hours
        )
    )

@router.get("/export/entries")
def export_entries(
    format: ExportFormat = Query(default=ExportFormat.CSV),
    date_from: datetime = Query(
        ..., 
        description="Start date and time (ISO format)",
        examples=["2023-10-01T00:00:00"]
    ),
    date_to: datetime = Query(
        ..., 
        description="End date and time (ISO format)",
        examples=["2023-10-31T23:59:59"]
    ),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Export entry/exit logs in the chosen format.
    """
    logs = db.query(EntryExitLog).filter(
        EntryExitLog.timestamp >= date_from,
        EntryExitLog.timestamp <= date_to
    ).order_by(EntryExitLog.timestamp.desc()).all()

    if format == ExportFormat.CSV:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Plate Number", "Gate Type", "Timestamp", "Status", "Is Overstayed", "Notes"])
        
        for log in logs:
            writer.writerow([
                log.id, 
                log.plate_number, 
                log.gate_type, 
                log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                log.status,
                log.is_overstayed,
                log.notes
            ])
        
        output.seek(0)
        filename = f"entry_exit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return StreamingResponse(
            output, 
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    return ApiResponse(
        message="Logs retrieved for export.",
        data=[{
            "id": l.id,
            "plate_number": l.plate_number,
            "gate_type": l.gate_type,
            "timestamp": l.timestamp,
            "status": l.status,
            "overstayed": l.is_overstayed
        } for l in logs]
    )

@router.get("/export/reservations")
def export_reservations(
    format: ExportFormat = Query(default=ExportFormat.CSV),
    date_from: datetime = Query(
        ..., 
        description="Start date and time (ISO format)",
        examples=["2023-10-01T00:00:00"]
    ),
    date_to: datetime = Query(
        ..., 
        description="End date and time (ISO format)",
        examples=["2023-10-31T23:59:59"]
    ),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Export reservation data in the chosen format.
    """
    res_list = db.query(Reservation).filter(
        Reservation.reservation_date >= date_from.date(),
        Reservation.reservation_date <= date_to.date()
    ).all()

    if format == ExportFormat.CSV:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "User ID", "Vehicle ID", "Zone ID", "Date", "Start", "End", "Status"])
        
        for r in res_list:
            writer.writerow([
                r.id, r.user_id, r.vehicle_id, r.zone_id,
                r.reservation_date.strftime("%Y-%m-%d"),
                r.start_time.strftime("%H:%M"),
                r.end_time.strftime("%H:%M"),
                r.status
            ])
        
        output.seek(0)
        filename = f"reservations_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return StreamingResponse(
            output, 
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    return ApiResponse(message="Reservations retrieved for export.", data=res_list)
