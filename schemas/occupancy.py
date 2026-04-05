from datetime import datetime
from enum import Enum
from typing import List, Optional, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")

class OccupancySource(str, Enum):
    SYSTEM = "system"
    SENSOR = "sensor"
    CAMERA = "camera"
    MANUAL = "manual"

class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: Optional[T] = None

class OccupancyUpdateRequest(BaseModel):
    zone_id: int
    occupied_count: int
    updated_at: Optional[datetime] = None
    source: OccupancySource = OccupancySource.SYSTEM

class OccupancyManualAdjustRequest(BaseModel):
    occupied_count: int
    updated_at: Optional[datetime] = None
    source: OccupancySource = OccupancySource.MANUAL

class UnavailableSlots(BaseModel):
    occupied: List[str] = []
    reserved: List[str] = []

class ZoneOccupancySummary(BaseModel):
    zone_id: int
    zone_name: str
    zone_code: str
    occupied_count: int
    available_count: int
    total_capacity: int
    updated_at: datetime
    source: str
    active: bool
    blocked: bool
    unavailable_slots: UnavailableSlots = Field(default_factory=UnavailableSlots)

class ZoneOccupancyListResponse(BaseModel):
    items: List[ZoneOccupancySummary]
    total: int

# NEW SCHEMA FOR STREAMING
class StartStreamRequest(BaseModel):
    url: str = Field(..., description="Camera URL (RTSP, HTTP, or 0 for webcam)")
