import csv
import io
from datetime import datetime, date, timedelta
from typing import List, Optional
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from core.database import get_db
from models.entry_exit_logs import EntryExitLog
from models.reservations import Reservation
from models.zones import Zone
from models.users import User
from models.vehicles import Vehicle
from routers.auth import require_admin
from schemas.auth import ApiResponse
from pydantic import BaseModel

router = APIRouter(prefix="/reports", tags=["reports"])


class ExportFormat(str, Enum):
    CSV = "csv"
    PDF = "pdf"


class DailyUsageItem(BaseModel):
    date: str
    total_entries: int
    total_exits: int
    total_reservations: int
    student_count: int
    staff_count: int
    visitor_count: int


class FullSummaryItem(BaseModel):
    id: str
    type: str  # 'Reservation' or 'Movement'
    date: str
    time: str
    plate_number: str
    user_name: str
    zone: str
    slot: Optional[str]
    status: str
    details: str


# -----------------------------
# Helper Logic
# -----------------------------

def _get_daily_usage_data(db: Session, start_date: date, end_date: date) -> List[DailyUsageItem]:
    data = []
    current = start_date

    while current <= end_date:
        day_start = datetime.combine(current, datetime.min.time())
        day_end = datetime.combine(current, datetime.max.time())

        entries = db.query(EntryExitLog).filter(
            EntryExitLog.gate_type == "entry",
            EntryExitLog.timestamp >= day_start,
            EntryExitLog.timestamp <= day_end
        ).count()

        exits = db.query(EntryExitLog).filter(
            EntryExitLog.gate_type == "exit",
            EntryExitLog.timestamp >= day_start,
            EntryExitLog.timestamp <= day_end
        ).count()

        res_count = db.query(Reservation).filter(
            Reservation.reservation_date == current
        ).count()

        students = db.query(EntryExitLog).join(
            User, EntryExitLog.user_id == User.id
        ).filter(
            EntryExitLog.gate_type == "entry",
            EntryExitLog.timestamp >= day_start,
            EntryExitLog.timestamp <= day_end,
            User.role == "student"
        ).count()

        staff = db.query(EntryExitLog).join(
            User, EntryExitLog.user_id == User.id
        ).filter(
            EntryExitLog.gate_type == "entry",
            EntryExitLog.timestamp >= day_start,
            EntryExitLog.timestamp <= day_end,
            User.role == "staff"
        ).count()

        visitors = db.query(EntryExitLog).outerjoin(
            User, EntryExitLog.user_id == User.id
        ).filter(
            EntryExitLog.gate_type == "entry",
            EntryExitLog.timestamp >= day_start,
            EntryExitLog.timestamp <= day_end,
            ((User.role == "visitor") | (EntryExitLog.user_id == None))
        ).count()

        data.append(
            DailyUsageItem(
                date=str(current),
                total_entries=entries,
                total_exits=exits,
                total_reservations=res_count,
                student_count=students,
                staff_count=staff,
                visitor_count=visitors
            )
        )

        current += timedelta(days=1)

    return data


def _get_full_summary_data(db: Session, start_date: date, end_date: date) -> List[FullSummaryItem]:
    data = []

    reservations = (
        db.query(Reservation)
        .join(User, Reservation.user_id == User.id)
        .join(Zone, Reservation.zone_id == Zone.id)
        .join(Vehicle, Reservation.vehicle_id == Vehicle.id)
        .filter(
            Reservation.reservation_date >= start_date,
            Reservation.reservation_date <= end_date
        )
        .all()
    )

    for r in reservations:
        data.append(
            FullSummaryItem(
                id=f"RES-{r.id}",
                type="Reservation",
                date=str(r.reservation_date),
                time=f"{r.start_time.strftime('%H:%M')} - {r.end_time.strftime('%H:%M')}",
                plate_number=r.vehicle.plate_number if r.vehicle else "N/A",
                user_name=r.user.full_name if r.user else "N/A",
                zone=r.zone.name if r.zone else "N/A",
                slot=r.slot_number,
                status=r.status,
                details=f"Booked for {r.vehicle.brand} {r.vehicle.model}" if r.vehicle else "Reservation"
            )
        )

    logs = (
        db.query(EntryExitLog)
        .outerjoin(User, EntryExitLog.user_id == User.id)





































































































































































































































































































































































































































































        .filter(
            cast(EntryExitLog.timestamp, Date) >= start_date,
            cast(EntryExitLog.timestamp, Date) <= end_date
        )
        .all()
    )

    for l in logs:
        data.append(
            FullSummaryItem(
                id=f"LOG-{l.id}",
                type="Movement",
                date=str(l.timestamp.date()),
                time=l.timestamp.strftime("%H:%M:%S"),
                plate_number=l.plate_number or "N/A",
                user_name=l.user.full_name if l.user else "Guest",
                zone=l.zone.name if l.zone else "N/A",
                slot=None,
                status=(l.gate_type or "").upper(),
                details=f"Source: {l.source or 'N/A'} | Status: {l.status or 'N/A'}"
            )
        )

    data.sort(key=lambda x: (x.date, x.time), reverse=True)
    return data


def _build_csv_buffer(report_type: str, start_date: date, end_date: date, db: Session) -> io.BytesIO:
    text_output = io.StringIO()
    writer = csv.writer(text_output)

    if report_type == "daily_usage":
        data = _get_daily_usage_data(db, start_date, end_date)
        writer.writerow(["Date", "Entries", "Exits", "Reservations", "Students", "Staff", "Visitors"])
        for item in data:
            writer.writerow([
                item.date,
                item.total_entries,
                item.total_exits,
                item.total_reservations,
                item.student_count,
                item.staff_count,
                item.visitor_count,
            ])

    elif report_type == "full_summary":
        data = _get_full_summary_data(db, start_date, end_date)
        writer.writerow(["ID", "Type", "Date", "Time", "Plate Number", "User", "Zone", "Slot", "Status", "Details"])
        for item in data:
            writer.writerow([
                item.id,
                item.type,
                item.date,
                item.time,
                item.plate_number,
                item.user_name,
                item.zone,
                item.slot or "N/A",
                item.status,
                item.details,
            ])
    else:
        raise HTTPException(status_code=404, detail="Report type not supported")

    byte_output = io.BytesIO()
    byte_output.write(text_output.getvalue().encode("utf-8"))
    byte_output.seek(0)
    return byte_output


def _draw_pdf_page_header(pdf: canvas.Canvas, title: str, start_date: date, end_date: date, page_width: float, page_height: float):
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(20 * mm, page_height - 15 * mm, title)

    pdf.setFont("Helvetica", 10)
    pdf.drawString(20 * mm, page_height - 22 * mm, f"Period: {start_date} to {end_date}")


def _build_daily_usage_pdf(start_date: date, end_date: date, db: Session) -> io.BytesIO:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    data = _get_daily_usage_data(db, start_date, end_date)

    y = height - 30 * mm
    _draw_pdf_page_header(pdf, "Daily Usage Report", start_date, end_date, width, height)
    y -= 10 * mm

    headers = ["Date", "Entries", "Exits", "Reservations", "Students", "Staff", "Visitors"]
    col_x = [15 * mm, 45 * mm, 65 * mm, 85 * mm, 120 * mm, 145 * mm, 165 * mm]

    pdf.setFont("Helvetica-Bold", 9)
    for i, header in enumerate(headers):
        pdf.drawString(col_x[i], y, header)

    y -= 6 * mm
    pdf.setFont("Helvetica", 9)

    for item in data:
        if y < 20 * mm:
            pdf.showPage()
            _draw_pdf_page_header(pdf, "Daily Usage Report", start_date, end_date, width, height)
            y = height - 40 * mm
            pdf.setFont("Helvetica-Bold", 9)
            for i, header in enumerate(headers):
                pdf.drawString(col_x[i], y, header)
            y -= 6 * mm
            pdf.setFont("Helvetica", 9)

        row = [
            item.date,
            str(item.total_entries),
            str(item.total_exits),
            str(item.total_reservations),
            str(item.student_count),
            str(item.staff_count),
            str(item.visitor_count),
        ]

        for i, value in enumerate(row):
            pdf.drawString(col_x[i], y, value)

        y -= 6 * mm

    pdf.save()
    buffer.seek(0)
    return buffer


def _truncate_text(text: str, max_len: int) -> str:
    if text is None:
        return ""
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def _build_full_summary_pdf(start_date: date, end_date: date, db: Session) -> io.BytesIO:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)

    data = _get_full_summary_data(db, start_date, end_date)

    y = height - 20 * mm
    _draw_pdf_page_header(pdf, "Full Summary Report", start_date, end_date, width, height)
    y -= 10 * mm

    headers = ["ID", "Type", "Date", "Time", "Plate", "User", "Zone", "Slot", "Status", "Details"]
    col_x = [10 * mm, 28 * mm, 50 * mm, 72 * mm, 95 * mm, 125 * mm, 165 * mm, 195 * mm, 215 * mm, 240 * mm]

    pdf.setFont("Helvetica-Bold", 8)
    for i, header in enumerate(headers):
        pdf.drawString(col_x[i], y, header)

    y -= 6 * mm
    pdf.setFont("Helvetica", 8)

    for item in data:
        if y < 15 * mm:
            pdf.showPage()
            _draw_pdf_page_header(pdf, "Full Summary Report", start_date, end_date, width, height)
            y = height - 30 * mm
            pdf.setFont("Helvetica-Bold", 8)
            for i, header in enumerate(headers):
                pdf.drawString(col_x[i], y, header)
            y -= 6 * mm
            pdf.setFont("Helvetica", 8)

        row = [
            item.id,
            item.type,
            item.date,
            item.time,
            _truncate_text(item.plate_number, 12),
            _truncate_text(item.user_name, 18),
            _truncate_text(item.zone, 12),
            item.slot or "N/A",
            _truncate_text(item.status, 10),
            _truncate_text(item.details, 40),
        ]

        for i, value in enumerate(row):
            pdf.drawString(col_x[i], y, str(value))

        y -= 5.5 * mm

    pdf.save()
    buffer.seek(0)
    return buffer


def _build_pdf_buffer(report_type: str, start_date: date, end_date: date, db: Session) -> io.BytesIO:
    if report_type == "daily_usage":
        return _build_daily_usage_pdf(start_date, end_date, db)
    elif report_type == "full_summary":
        return _build_full_summary_pdf(start_date, end_date, db)
    else:
        raise HTTPException(status_code=404, detail="Report type not supported")


# -----------------------------
# API Endpoints
# -----------------------------

@router.get("/daily_usage", response_model=ApiResponse[List[DailyUsageItem]])
def get_daily_usage(
    start_date: date = Query(...),
    end_date: date = Query(...),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")

    data = _get_daily_usage_data(db, start_date, end_date)
    return ApiResponse(message="Daily usage report generated.", data=data)


@router.get("/full_summary", response_model=ApiResponse[List[FullSummaryItem]])
def get_full_summary(
    start_date: date = Query(...),
    end_date: date = Query(...),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")

    data = _get_full_summary_data(db, start_date, end_date)
    return ApiResponse(message="Full summary report generated.", data=data)


@router.get("/{report_type}/download")
def download_report(
    report_type: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    format: ExportFormat = Query(ExportFormat.CSV),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")

    supported_reports = {"daily_usage", "full_summary"}
    if report_type not in supported_reports:
        raise HTTPException(status_code=404, detail="Report type not supported")

    if format == ExportFormat.CSV:
        file_buffer = _build_csv_buffer(report_type, start_date, end_date, db)
        filename = f"{report_type}_{start_date}_to_{end_date}.csv"
        media_type = "text/csv"
    elif format == ExportFormat.PDF:
        file_buffer = _build_pdf_buffer(report_type, start_date, end_date, db)
        filename = f"{report_type}_{start_date}_to_{end_date}.pdf"
        media_type = "application/pdf"
    else:
        raise HTTPException(status_code=400, detail="Invalid export format")

    return StreamingResponse(
        file_buffer,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )