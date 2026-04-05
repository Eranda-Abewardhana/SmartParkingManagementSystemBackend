import asyncio
from datetime import datetime, date, time
from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, WebSocket, WebSocketDisconnect, BackgroundTasks, Body
from sqlalchemy.orm import Session
from sqlalchemy import func

from core.database import get_db, SessionLocal
from models.occupancy import OccupancySnapshot
from models.zones import Zone
from models.users import User
from models.reservations import Reservation
from routers.admin import _count_vehicles_inside, _get_today_window
from schemas.reservations import ReservationStatus
from routers.auth import require_admin
from schemas.occupancy import (
    ApiResponse,
    OccupancyManualAdjustRequest,
    OccupancySource,
    OccupancyUpdateRequest,
    ZoneOccupancyListResponse,
    ZoneOccupancySummary,
    StartStreamRequest,
    UnavailableSlots,
)
from services.vision_ai_service import VisionService

router = APIRouter(prefix="/occupancy", tags=["occupancy"])


def _build_zone_summary(zone: Zone, db: Session) -> ZoneOccupancySummary:
    """
    Build zone occupancy summary from zone metadata and reservation data.

    occupied_count:
        Number of unique occupied slots for this specific zone.

    reserved_count:
        Slots currently reserved in the active time window but not physically occupied.
    """
    snapshot = (
        db.query(OccupancySnapshot)
        .filter(OccupancySnapshot.zone_id == zone.id)
        .order_by(OccupancySnapshot.updated_at.desc())
        .first()
    )

    updated_at = snapshot.updated_at if snapshot else datetime.utcnow()
    source = snapshot.source if snapshot else OccupancySource.SYSTEM.value

    now_dt = datetime.now()
    current_date = now_dt.date()
    current_time = now_dt.time()

    occupied_reservations = (
        db.query(Reservation)
        .filter(
            Reservation.zone_id == zone.id,
            Reservation.reservation_date == current_date,

            # 🔑 CRITICAL: current time inside reservation window
            Reservation.start_time <= current_time,
            Reservation.end_time >= current_time,

            # Only truly occupied states
            Reservation.status.in_([
                ReservationStatus.OCCUPIED.value,
                ReservationStatus.RESERVED.value  # include if you use ACTIVE
            ])
        )
        .all()
    )

    # Unique slot count
    occupied_slots = list({
        r.slot_number.strip()
        for r in occupied_reservations
        if r.slot_number and r.slot_number.strip()
    })

    occupied_count = len(occupied_slots)

    # ----------------------------------------
    # RESERVED SLOTS FOR CURRENT ACTIVE WINDOW
    # ----------------------------------------
    reserved_reservations = (
        db.query(Reservation)
        .filter(
            Reservation.zone_id == zone.id,
            Reservation.reservation_date == current_date,
            Reservation.status.in_([
                ReservationStatus.RESERVED.value,
                ReservationStatus.CONFIRMED.value,
                ReservationStatus.PENDING.value,
            ]),
            Reservation.start_time <= current_time,
            Reservation.end_time >= current_time
        )
        .all()
    )

    reserved_slots = list({
        r.slot_number.strip()
        for r in reserved_reservations
        if r.slot_number and r.slot_number.strip() and r.slot_number.strip() not in occupied_slots
    })

    unavailable_slots = UnavailableSlots(
        occupied=occupied_slots,
        reserved=reserved_slots
    )

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
        unavailable_slots=unavailable_slots
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
    "/detect-from-camera/{zone_id}",
    response_model=ApiResponse[ZoneOccupancySummary],
    status_code=status.HTTP_200_OK,
)
async def detect_from_camera(
        zone_id: int,
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    """
    UPLOAD an image/video file. The backend will use AI to count vehicles.
    """
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found.")

    image_bytes = await file.read()

    # Run AI vehicle counting service
    occupied_count = VisionService.count_vehicles_in_zone(image_bytes)

    _validate_occupied_count(zone, occupied_count)

    new_snapshot = OccupancySnapshot(
        zone_id=zone_id,
        occupied_count=occupied_count,
        updated_at=datetime.utcnow(),
        source=OccupancySource.CAMERA.value,
    )
    db.add(new_snapshot)
    db.commit()
    db.refresh(new_snapshot)

    return ApiResponse(
        message=f"Detection complete. {occupied_count} vehicles found in {zone.name}.",
        data=_build_zone_summary(zone, db),
    )


@router.post(
    "/start-camera-stream/{zone_id}",
    response_model=ApiResponse[Any],
    status_code=status.HTTP_200_OK,
)
async def start_camera_stream(
        zone_id: int,
        payload: StartStreamRequest,
        background_tasks: BackgroundTasks = BackgroundTasks(),
        db: Session = Depends(get_db)
):
    """
    Input a URL (RTSP/HTTP/0) in the Request Body to start background processing.
    """
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found.")

    # Use our database session factory for the background task
    background_tasks.add_task(VisionService.process_rtsp_stream, payload.url, zone_id, SessionLocal)

    return ApiResponse(
        message=f"Started AI background processing for {zone.name}",
        data={"url": payload.url, "zone_id": zone_id}
    )

@router.websocket("/ws/detect-stream/{zone_id}")
async def detect_stream(websocket: WebSocket, zone_id: int, db: Session = Depends(get_db)):
    await websocket.accept()
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        await websocket.close(code=1008)
        return
    try:
        while True:
            image_bytes = await websocket.receive_bytes()
            occupied_count = VisionService.count_vehicles_in_zone(image_bytes)
            new_snapshot = OccupancySnapshot(
                zone_id=zone_id,
                occupied_count=occupied_count,
                updated_at=datetime.utcnow(),
                source=OccupancySource.CAMERA.value,
            )
            db.add(new_snapshot)
            db.commit()
            await websocket.send_json({"zone_id": zone_id, "occupied_count": occupied_count})
    except WebSocketDisconnect:
        pass

@router.post("/update", response_model=ApiResponse[ZoneOccupancySummary])
def update_occupancy(payload: OccupancyUpdateRequest, db: Session = Depends(get_db)):
    zone = db.query(Zone).filter(Zone.id == payload.zone_id).first()
    if not zone: raise HTTPException(404, "Zone not found.")
    _validate_occupied_count(zone, payload.occupied_count)
    new_snapshot = OccupancySnapshot(zone_id=payload.zone_id, occupied_count=payload.occupied_count, source=payload.source.value)
    db.add(new_snapshot); db.commit(); db.refresh(new_snapshot)
    return ApiResponse(message="Updated", data=_build_zone_summary(zone, db))

@router.get("/zones", response_model=ApiResponse[ZoneOccupancyListResponse])
def get_all_zone_occupancy(db: Session = Depends(get_db)):
    zones = db.query(Zone).all()
    items = [_build_zone_summary(zone, db) for zone in zones]
    return ApiResponse(message="Success", data=ZoneOccupancyListResponse(items=items, total=len(items)))

@router.get("/zones/{zone_id}", response_model=ApiResponse[ZoneOccupancySummary])
def get_zone_occupancy(zone_id: int, db: Session = Depends(get_db)):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone: raise HTTPException(404, "Zone not found.")
    return ApiResponse(message="Success", data=_build_zone_summary(zone, db))

@router.patch("/zones/{zone_id}/manual-adjust", response_model=ApiResponse[ZoneOccupancySummary])
def manual_adjust_zone_occupancy(zone_id: int, payload: OccupancyManualAdjustRequest, db: Session = Depends(get_db)):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone: raise HTTPException(404, "Zone not found.")
    _validate_occupied_count(zone, payload.occupied_count)
    new_snapshot = OccupancySnapshot(zone_id=zone_id, occupied_count=payload.occupied_count, source=payload.source.value)
    db.add(new_snapshot); db.commit(); db.refresh(new_snapshot)
    return ApiResponse(message="Adjusted", data=_build_zone_summary(zone, db))
