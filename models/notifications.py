from typing import List

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from core.database import Base
from datetime import datetime

from schemas.preferences import UserPreferenceRead

class SettingsRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(100), nullable=False)
    message = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class NotificationSummary(BaseModel):
    id: int
    user_id: int
    title: str
    message: str
    type: str
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationListPreview(BaseModel):
    items: List[NotificationSummary]
    total: int
    unread_count: int


class UserSettingsResponse(BaseModel):
    preferences: UserPreferenceRead
    notifications: NotificationListPreview