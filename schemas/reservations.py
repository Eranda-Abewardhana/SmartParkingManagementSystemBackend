from datetime import date, time, datetime
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReservationStatus(str, Enum):
    CONFIRMED = "confirmed"
    PENDING = "pending"
    RESERVED = "reserved"
    OCCUPIED = "occupied"
    AVAILABLE = "available"
    EXPIRED = "expired"


class ReservationBase(BaseModel):
    vehicle_id: int = Field(..., ge=1)
    zone_id: int = Field(..., ge=1)
    slot_number: str = Field(..., min_length=1, max_length=20)

    reservation_date: date
    start_time: time
    end_time: time

    notes: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be earlier than end_time.")
        return self

    @model_validator(mode="after")
    def validate_reservation_date(self):
        from datetime import date as _date
        if self.reservation_date < _date.today():
            raise ValueError("reservation_date cannot be in the past.")
        return self


class ReservationCreateRequest(ReservationBase):
    user_id: Optional[int] = Field(default=None, ge=1)


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

    @model_validator(mode="after")
    def validate_reservation_date(self):
        from datetime import date as _date
        if self.reservation_date < _date.today():
            raise ValueError("reservation_date cannot be in the past.")
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
    slot_number: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    message: str
    data: T


class ReservationDetail(BaseModel):
    id: int
    start_time: Optional[str]
    end_time: Optional[str]
    user_id: int
    status: str
    notes: Optional[str]
    vehicle_id: int
    zone_id: int
    vehicalNo: Optional[str] = None
    username: Optional[str] = None
    zone_name: Optional[str] = None
    reservation_date: Optional[str] = None
    slot_number: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ReservationListResponse(BaseModel):
    items: List[ReservationDetail]
    total: int