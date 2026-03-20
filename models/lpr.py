from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from core.database import Base
from datetime import datetime

class LprDetection(Base):
    __tablename__ = "lpr_detections"

    id = Column(Integer, primary_key=True, index=True)
    detected_plate = Column(String(20), nullable=False)
    confidence = Column(Float, nullable=False)
    image_url_or_path = Column(String(255), nullable=True)
    source_camera = Column(String(100), nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow)
    matched_vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    matched_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    matched_reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=True)
    review_status = Column(String(50), nullable=False) # Store as string from LprReviewStatus Enum
    corrected_plate = Column(String(20), nullable=True)
