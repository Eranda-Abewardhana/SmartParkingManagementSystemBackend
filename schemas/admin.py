from datetime import datetime
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator


class EntryDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class AdminActionType(str, Enum):
    MANUAL_ENTRY_DECISION = "manual_entry_decision"
    MANUAL_ZONE_REASSIGNMENT = "manual_zone_reassignment"
    RESOLVE_UNMATCHED_LPR = "resolve_unmatched_lpr"



class DashboardSummary(BaseModel):
    # Zones & capacity
    total_zones: int
    total_capacity: int
    occupied_count: int
    available_count: int

    # Reservations
    active_reservations: int
    pending_requests: int   # ✅ added

    # Vehicle analytics (TODAY 00:00 → now)
    vehicles_inside: int    # ✅ today net inside
    total_entries: int      # ✅ added
    total_exits: int        # ✅ added

    # Alerts
    unmatched_lpr_count: int
    recent_alert_count: int


class ManualEntryDecisionRequest(BaseModel):
    plate_number: str = Field(..., min_length=2, max_length=20)
    decision: EntryDecision
    reason: str = Field(..., min_length=1, max_length=255)
    reservation_id: Optional[int] = Field(default=None, ge=1)

    @field_validator("plate_number")
    @classmethod
    def normalize_plate_number(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Plate number cannot be empty.")
        return normalized


class ManualZoneReassignmentRequest(BaseModel):
    reservation_id: int = Field(..., ge=1)
    new_zone_id: int = Field(..., ge=1)
    reason: str = Field(..., min_length=1, max_length=255)


class ResolveUnmatchedLprRequest(BaseModel):
    detection_id: int = Field(..., ge=1)
    vehicle_id: Optional[int] = Field(default=None, ge=1)
    corrected_plate: Optional[str] = Field(default=None, min_length=2, max_length=20)
    notes: Optional[str] = Field(default=None, max_length=255)

    @field_validator("corrected_plate")
    @classmethod
    def normalize_corrected_plate(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Corrected plate cannot be empty.")
        return normalized


class AuditLogItem(BaseModel):
    id: int
    action_type: AdminActionType
    admin_user_id: int
    details: str
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: List[AuditLogItem]
    total: int


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: Optional[T] = None