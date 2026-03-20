from datetime import date, time
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    NO_SHOW = "no_show"


class ReservationBase(BaseModel):
    vehicle_id: int = Field(..., ge=1)
    zone_id: int = Field(..., ge=1)
    reservation_date: date
    start_time: time
    end_time: time
    notes: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be earlier than end_time.")
        return self


class ReservationCreateRequest(ReservationBase):
    pass


class ReservationRescheduleRequest(BaseModel):
    reservation_date: date
    start_time: time
    end_time: time
    notes: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be earlier than end_time.")
        return self


class ReservationStatusUpdateRequest(BaseModel):
    status: ReservationStatus


class ReservationCancelRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=255)


class ReservationSummary(BaseModel):
    id: int
    user_id: int
    vehicle_id: int
    zone_id: int
    reservation_date: date
    start_time: time
    end_time: time
    status: ReservationStatus
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ReservationDetail(ReservationSummary):
    pass


class ReservationListResponse(BaseModel):
    items: List[ReservationSummary]
    total: int


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: Optional[T] = None