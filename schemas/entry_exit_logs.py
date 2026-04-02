from datetime import datetime, timedelta
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GateType(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"
    MONITORING = "monitoring"


class EntryExitStatus(str, Enum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    MANUAL_OVERRIDE = "manual_override"
    DENIED = "denied"
    DETECTED = "detected"


class EntryExitBase(BaseModel):
    plate_number: str = Field(..., min_length=2, max_length=20)
    source: str = Field(..., min_length=1, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=255)

    @field_validator("plate_number")
    @classmethod
    def normalize_plate_number(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Plate number cannot be empty.")
        return normalized


class EntryLogCreateRequest(EntryExitBase):
    timestamp: Optional[datetime] = None


class ExitLogCreateRequest(EntryExitBase):
    timestamp: Optional[datetime] = None


class DurationSummary(BaseModel):
    total_minutes: float
    formatted_duration: str


class EntryExitLogSummary(BaseModel):
    id: int
    plate_number: str
    vehicle_id: Optional[int] = None
    user_id: Optional[int] = None
    reservation_id: Optional[int] = None
    gate_type: GateType
    timestamp: datetime
    source: str
    status: EntryExitStatus
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExitResponseDetail(BaseModel):
    exit_log: EntryExitLogSummary
    entry_log: Optional[EntryExitLogSummary] = None
    duration: Optional[DurationSummary] = None


class EntryExitLogDetail(EntryExitLogSummary):
    pass


class EntryExitLogListResponse(BaseModel):
    items: List[EntryExitLogSummary]
    total: int


class CurrentInsideItem(BaseModel):
    plate_number: str
    vehicle_id: Optional[int] = None
    user_id: Optional[int] = None
    reservation_id: Optional[int] = None
    entry_log_id: int
    entered_at: datetime
    source: str
    status: EntryExitStatus
    notes: Optional[str] = None


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: Optional[T] = None
