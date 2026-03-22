from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, File, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import desc

from core.database import get_db
from models.lpr import LprDetection
from models.vehicles import Vehicle
from models.reservations import Reservation
from models.users import User
from routers.auth import require_admin
from schemas.lpr import (
    ApiResponse,
    LprDetectionCreateRequest,
    LprDetectionDetail,
    LprDetectionListResponse,
    LprDetectionReviewUpdateRequest,
    LprDetectionSummary,
    LprReviewStatus,
)
from services.vision import VisionService

router = APIRouter(prefix="/lpr", tags=["lpr"])


def _to_detection_summary(detection: LprDetection) -> LprDetectionSummary:
    return LprDetectionSummary.model_validate(detection)


def _to_detection_detail(detection: LprDetection) -> LprDetectionDetail:
    return LprDetectionDetail.model_validate(detection)


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


@router.post(
    "/detect-from-image",
    response_model=ApiResponse[LprDetectionDetail],
    status_code=status.HTTP_201_CREATED,
)
async def detect_from_image(
    source_camera: str = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    UPLOAD an image and have the backend automatically run OCR to detect the plate.
    """
    image_bytes = await file.read()
    
    # Run the Computer Vision Service
    detected_plate, confidence = VisionService.recognize_plate(image_bytes)
    
    detected_at = datetime.utcnow()
    matched_vehicle_id = None
    matched_user_id = None
    matched_reservation_id = None
    review_status = LprReviewStatus.UNMATCHED.value

    # Search for matching vehicle
    vehicle = db.query(Vehicle).filter(
        Vehicle.plate_number == detected_plate,
        Vehicle.is_active == True
    ).first()

    if vehicle:
        matched_vehicle_id = vehicle.id
        matched_user_id = vehicle.owner_user_id
        reservation = _active_reservation_for_vehicle(db, vehicle.id, detected_at)
        if reservation:
            matched_reservation_id = reservation.id
        review_status = LprReviewStatus.MATCHED.value

    new_detection = LprDetection(
        detected_plate=detected_plate,
        confidence=confidence,
        image_url_or_path=f"upload://{file.filename}",
        source_camera=source_camera,
        detected_at=detected_at,
        matched_vehicle_id=matched_vehicle_id,
        matched_user_id=matched_user_id,
        matched_reservation_id=matched_reservation_id,
        review_status=review_status,
        corrected_plate=None,
    )
    db.add(new_detection)
    db.commit()
    db.refresh(new_detection)

    return ApiResponse(
        message=f"Image processed. Detected Plate: {detected_plate}",
        data=_to_detection_detail(new_detection),
    )


@router.post(
    "/detections",
    response_model=ApiResponse[LprDetectionDetail],
    status_code=status.HTTP_201_CREATED,
)
def create_lpr_detection(payload: LprDetectionCreateRequest, db: Session = Depends(get_db)):
    """
    Receive a detection result from the Python vision service (Pre-processed).
    """
    detected_at = payload.detected_at or datetime.utcnow()
    matched_vehicle_id = None
    matched_user_id = None
    matched_reservation_id = None
    review_status = LprReviewStatus.UNMATCHED.value

    vehicle = db.query(Vehicle).filter(
        Vehicle.plate_number == payload.detected_plate.strip().upper(),
        Vehicle.is_active == True
    ).first()

    if vehicle:
        matched_vehicle_id = vehicle.id
        matched_user_id = vehicle.owner_user_id
        reservation = _active_reservation_for_vehicle(db, vehicle.id, detected_at)
        if reservation:
            matched_reservation_id = reservation.id
        review_status = LprReviewStatus.MATCHED.value

    new_detection = LprDetection(
        detected_plate=payload.detected_plate.strip().upper(),
        confidence=payload.confidence,
        image_url_or_path=payload.image_url_or_path,
        source_camera=payload.source_camera,
        detected_at=detected_at,
        matched_vehicle_id=matched_vehicle_id,
        matched_user_id=matched_user_id,
        matched_reservation_id=matched_reservation_id,
        review_status=review_status,
        corrected_plate=None,
    )
    db.add(new_detection)
    db.commit()
    db.refresh(new_detection)

    return ApiResponse(
        message="LPR detection stored successfully.",
        data=_to_detection_detail(new_detection),
    )


@router.get(
    "/detections",
    response_model=ApiResponse[LprDetectionListResponse],
    status_code=status.HTTP_200_OK,
)
def list_lpr_detections(
    review_status: Optional[LprReviewStatus] = Query(default=None),
    detected_plate: Optional[str] = Query(default=None),
    source_camera: Optional[str] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin only. List LPR detections with filters.
    """
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from cannot be later than date_to.")

    query = db.query(LprDetection)

    if review_status is not None:
        query = query.filter(LprDetection.review_status == review_status.value)

    if detected_plate:
        normalized_plate = f"%{detected_plate.strip().upper()}%"
        query = query.filter(
            (LprDetection.detected_plate.ilike(normalized_plate)) |
            (LprDetection.corrected_plate.ilike(normalized_plate))
        )

    if source_camera:
        query = query.filter(LprDetection.source_camera.ilike(f"%{source_camera.strip()}%"))

    if date_from is not None:
        query = query.filter(LprDetection.detected_at >= date_from)

    if date_to is not None:
        query = query.filter(LprDetection.detected_at <= date_to)

    total = query.count()
    detections = query.order_by(desc(LprDetection.detected_at)).all()

    data = LprDetectionListResponse(
        items=[_to_detection_summary(d) for d in detections],
        total=total,
    )

    return ApiResponse(
        message="LPR detections retrieved successfully.",
        data=data,
    )


@router.get(
    "/detections/{detection_id}",
    response_model=ApiResponse[LprDetectionDetail],
    status_code=status.HTTP_200_OK,
)
def get_lpr_detection(
    detection_id: int, 
    _: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Admin only. Return one LPR detection record by ID.
    """
    detection = db.query(LprDetection).filter(LprDetection.id == detection_id).first()
    if not detection:
        raise HTTPException(status_code=404, detail="LPR detection not found.")

    return ApiResponse(
        message="LPR detection retrieved successfully.",
        data=_to_detection_detail(detection),
    )


@router.patch(
    "/detections/{detection_id}/review",
    response_model=ApiResponse[LprDetectionDetail],
    status_code=status.HTTP_200_OK,
)
def review_lpr_detection(
    detection_id: int,
    payload: LprDetectionReviewUpdateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin only. Review or correct an LPR detection.
    """
    detection = db.query(LprDetection).filter(LprDetection.id == detection_id).first()
    if not detection:
        raise HTTPException(status_code=404, detail="LPR detection not found.")

    if payload.matched_vehicle_id is not None:
        vehicle = db.query(Vehicle).filter(Vehicle.id == payload.matched_vehicle_id, Vehicle.is_active == True).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Matched vehicle not found.")
        detection.matched_vehicle_id = vehicle.id

    if payload.matched_user_id is not None:
        user = db.query(User).filter(User.id == payload.matched_user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Matched user not found.")
        detection.matched_user_id = user.id

    if payload.matched_reservation_id is not None:
        res = db.query(Reservation).filter(Reservation.id == payload.matched_reservation_id).first()
        if not res:
            raise HTTPException(status_code=404, detail="Matched reservation not found.")
        detection.matched_reservation_id = res.id

    detection.review_status = payload.review_status.value

    if payload.corrected_plate is not None:
        detection.corrected_plate = payload.corrected_plate

    db.commit()
    db.refresh(detection)

    return ApiResponse(
        message="LPR detection review updated successfully.",
        data=_to_detection_detail(detection),
    )
