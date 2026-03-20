from datetime import datetime
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field


class OccupancySource(str, Enum):
    CAMERA = "camera"
    MANUAL = "manual"
    SYSTEM = "system"


class OccupancyUpdateRequest(BaseModel):
    zone_id: int = Field(..., ge=1)
    occupied_count: int = Field(..., ge=0)
    source: OccupancySource
    updated_at: Optional[datetime] = None


class OccupancyManualAdjustRequest(BaseModel):
    occupied_count: int = Field(..., ge=0)
    source: OccupancySource = OccupancySource.MANUAL
    updated_at: Optional[datetime] = None


class ZoneOccupancySummary(BaseModel):
    zone_id: int
    zone_name: str
    zone_code: str
    occupied_count: int
    available_count: int
    total_capacity: int
    updated_at: datetime
    source: OccupancySource
    active: bool
    blocked: bool


class ZoneOccupancyListResponse(BaseModel):
    items: List[ZoneOccupancySummary]
    total: int


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: Optional[T] = None