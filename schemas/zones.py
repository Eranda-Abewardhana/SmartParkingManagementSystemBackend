from datetime import date, time
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class ZoneType(str, Enum):
    STUDENT = "student"
    STAFF = "staff"
    VISITOR = "visitor"
    MIXED = "mixed"
    DISABLED = "disabled"
    VIP = "vip"


class ZoneBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=20)
    zone_type: ZoneType
    capacity: int = Field(..., ge=0)
    active: bool = True
    blocked: bool = False
    description: Optional[str] = Field(default=None, max_length=255)


class ZoneCreateRequest(ZoneBase):
    pass


class ZoneUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    code: Optional[str] = Field(default=None, min_length=1, max_length=20)
    zone_type: Optional[ZoneType] = None
    capacity: Optional[int] = Field(default=None, ge=0)
    active: Optional[bool] = None
    blocked: Optional[bool] = None
    description: Optional[str] = Field(default=None, max_length=255)


class ZoneStatusUpdateRequest(BaseModel):
    active: Optional[bool] = None
    blocked: Optional[bool] = None


class ZoneSummary(BaseModel):
    id: int
    name: str
    code: str
    zone_type: ZoneType
    capacity: int
    active: bool
    blocked: bool
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ZoneDetail(ZoneSummary):
    pass


class ZoneAvailability(BaseModel):
    zone_id: int
    zone_name: str
    code: str
    capacity: int
    occupied_count: int
    reserved_count: int
    available_count: int
    active: bool
    blocked: bool


class ZoneListResponse(BaseModel):
    items: List[ZoneSummary]
    total: int


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: Optional[T] = None



class SlotAvailability(BaseModel):
    slot_id: int
    slot_number: str
    status: str
    is_available: bool
    reservation_id: Optional[int] = None


class ZoneAvailability(BaseModel):
    zone_id: int
    zone_name: str
    zone_code: str
    zone_type: str
    capacity: int
    active: bool
    blocked: bool
    reservation_date: date
    start_time: time
    end_time: time
    total_slots: int
    available_slots: int
    occupied_slots: int
    slots: List[SlotAvailability]
