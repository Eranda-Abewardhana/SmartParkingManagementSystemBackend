from datetime import datetime
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class NotificationType(str, Enum):
    RESERVATION = "reservation"
    ENTRY = "entry"
    EXIT = "exit"
    ALERT = "alert"
    SYSTEM = "system"


class NotificationSummary(BaseModel):
    id: int
    user_id: int
    title: str
    message: str
    type: NotificationType
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationDetail(NotificationSummary):
    pass


class NotificationListResponse(BaseModel):
    items: List[NotificationSummary]
    total: int


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: Optional[T] = None