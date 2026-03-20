from datetime import datetime
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LprReviewStatus(str, Enum):
    PENDING = "pending"
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    CORRECTED = "corrected"


class LprDetectionCreateRequest(BaseModel):
    detected_plate: str = Field(..., min_length=2, max_length=20)
    confidence: float = Field(..., ge=0.0, le=1.0)
    image_url_or_path: str = Field(..., min_length=1, max_length=500)
    source_camera: str = Field(..., min_length=1, max_length=100)
    detected_at: Optional[datetime] = None

    @field_validator("detected_plate")
    @classmethod
    def normalize_detected_plate(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Detected plate cannot be empty.")
        return normalized


class LprDetectionReviewUpdateRequest(BaseModel):
    review_status: LprReviewStatus
    corrected_plate: Optional[str] = Field(default=None, min_length=2, max_length=20)
    matched_vehicle_id: Optional[int] = Field(default=None, ge=1)
    matched_user_id: Optional[int] = Field(default=None, ge=1)
    matched_reservation_id: Optional[int] = Field(default=None, ge=1)

    @field_validator("corrected_plate")
    @classmethod
    def normalize_corrected_plate(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Corrected plate cannot be empty.")
        return normalized


class LprDetectionSummary(BaseModel):
    id: int
    detected_plate: str
    confidence: float
    image_url_or_path: str
    source_camera: str
    detected_at: datetime
    matched_vehicle_id: Optional[int] = None
    matched_user_id: Optional[int] = None
    matched_reservation_id: Optional[int] = None
    review_status: LprReviewStatus
    corrected_plate: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class LprDetectionDetail(LprDetectionSummary):
    pass


class LprDetectionListResponse(BaseModel):
    items: List[LprDetectionSummary]
    total: int


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: Optional[T] = None