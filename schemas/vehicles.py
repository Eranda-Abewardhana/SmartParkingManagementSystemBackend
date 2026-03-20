from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VehicleType(str, Enum):
    CAR = "car"
    BIKE = "bike"
    VAN = "van"
    BUS = "bus"
    OTHER = "other"


class VehicleBase(BaseModel):
    plate_number: str = Field(..., min_length=2, max_length=20)
    vehicle_type: VehicleType
    brand: Optional[str] = Field(default=None, max_length=80)
    model: Optional[str] = Field(default=None, max_length=80)
    color: Optional[str] = Field(default=None, max_length=40)

    @field_validator("plate_number")
    @classmethod
    def normalize_plate_number(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Plate number cannot be empty.")
        return normalized


class VehicleCreateRequest(VehicleBase):
    is_primary: bool = False


class VehicleUpdateRequest(BaseModel):
    plate_number: Optional[str] = Field(default=None, min_length=2, max_length=20)
    vehicle_type: Optional[VehicleType] = None
    brand: Optional[str] = Field(default=None, max_length=80)
    model: Optional[str] = Field(default=None, max_length=80)
    color: Optional[str] = Field(default=None, max_length=40)
    is_primary: Optional[bool] = None

    @field_validator("plate_number")
    @classmethod
    def normalize_plate_number(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Plate number cannot be empty.")
        return normalized


class VehiclePrimaryUpdateRequest(BaseModel):
    is_primary: bool = True


class VehicleSummary(BaseModel):
    id: int
    owner_user_id: int
    plate_number: str
    vehicle_type: VehicleType
    brand: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    is_primary: bool
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class VehicleDetail(VehicleSummary):
    pass


class VehicleListResponse(BaseModel):
    items: List[VehicleSummary]
    total: int


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: Optional[T] = None