import csv
import io
from datetime import date, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import func
from sqlalchemy.orm import Session
from core.database import get_db
from models.entry_exit_logs import EntryExitLog
from models.report import DailyUsageItem, DailyUsageResponse
from models.reservations import Reservation
from models.users import User
from routers.auth import require_admin
from schemas.auth import ApiResponse

router = APIRouter(prefix="/reports", tags=["reports"])


def _build_daily_usage_items(
    db: Session,
    start_date: date,
    end_date: date,
) -> List[DailyUsageItem]:
    entry_rows = (
        db.query(
            func.date(EntryExitLog.timestamp).label("day"),
            func.count(EntryExitLog.id).label("count"),
        )
        .filter(
            EntryExitLog.gate_type == "entry",
            func.date(EntryExitLog.timestamp) >= start_date,
            func.date(EntryExitLog.timestamp) <= end_date,
        )
        .group_by(func.date(EntryExitLog.timestamp))
        .all()
    )

    exit_rows = (
        db.query(
            func.date(EntryExitLog.timestamp).label("day"),
            func.count(EntryExitLog.id).label("count"),
        )
        .filter(
            EntryExitLog.gate_type == "exit",
            func.date(EntryExitLog.timestamp) >= start_date,
            func.date(EntryExitLog.timestamp) <= end_date,
        )
        .group_by(func.date(EntryExitLog.timestamp))
        .all()
    )

    reservation_rows = (
        db.query(
            Reservation.reservation_date.label("day"),
            func.count(Reservation.id).label("count"),
        )
        .filter(
            Reservation.reservation_date >= start_date,
            Reservation.reservation_date <= end_date,
        )
        .group_by(Reservation.reservation_date)
        .all()
    )

    entry_map = {row.day: row.count for row in entry_rows}
    exit_map = {row.day: row.count for row in exit_rows}
    reservation_map = {row.day: row.count for row in reservation_rows}

    items: List[DailyUsageItem] = []
    current = start_date

    while current <= end_date:
        items.append(
            DailyUsageItem(
                date=current.isoformat(),
                total_entries=entry_map.get(current, 0),
                total_exits=exit_map.get(current, 0),
                total_reservations=reservation_map.get(current, 0),
            )
        )
        current += timedelta(days=1)

    return items


@router.get("/daily_usage", response_model=ApiResponse[DailyUsageResponse])
def get_daily_usage_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be greater than or equal to start_date.",
        )

    items = _build_daily_usage_items(db, start_date, end_date)

    return ApiResponse(
        message="Daily usage report generated successfully.",
        data=DailyUsageResponse(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            items=items,
        ),
    )


@router.get("/daily_usage/download")
def download_daily_usage_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    format: str = Query(...),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be greater than or equal to start_date.",
        )

    items = _build_daily_usage_items(db, start_date, end_date)
    report_format = format.lower()

    if report_format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Total Entries", "Total Exits", "Total Reservations"])

        for item in items:
            writer.writerow([
                item.date,
                item.total_entries,
                item.total_exits,
                item.total_reservations,
            ])

        output.seek(0)

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=daily_usage_{start_date}_to_{end_date}.csv"
            },
        )

    if report_format == "pdf":
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        y = height - 50

        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(50, y, "Daily Usage Report")

        y -= 25
        pdf.setFont("Helvetica", 11)
        pdf.drawString(50, y, f"From {start_date} to {end_date}")

        y -= 35
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(50, y, "Date")
        pdf.drawString(170, y, "Entries")
        pdf.drawString(260, y, "Exits")
        pdf.drawString(340, y, "Reservations")

        y -= 15
        pdf.line(50, y, 500, y)
        y -= 20

        pdf.setFont("Helvetica", 10)

        for item in items:
            if y < 50:
                pdf.showPage()
                y = height - 50

                pdf.setFont("Helvetica-Bold", 10)
                pdf.drawString(50, y, "Date")
                pdf.drawString(170, y, "Entries")
                pdf.drawString(260, y, "Exits")
                pdf.drawString(340, y, "Reservations")
                y -= 15
                pdf.line(50, y, 500, y)
                y -= 20
                pdf.setFont("Helvetica", 10)

            pdf.drawString(50, y, str(item.date))
            pdf.drawString(170, y, str(item.total_entries))
            pdf.drawString(260, y, str(item.total_exits))
            pdf.drawString(340, y, str(item.total_reservations))
            y -= 18

        pdf.save()
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=daily_usage_{start_date}_to_{end_date}.pdf"
            },
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid format. Supported formats are csv and pdf.",
    )