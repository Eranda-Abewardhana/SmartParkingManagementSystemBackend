from pydantic import BaseModel, Field
from typing import Optional

class UserPreferenceBase(BaseModel):
    notifications_enabled: bool = True
    email_alerts_enabled: bool = True
    dark_mode: bool = False
    language: str = Field("en", max_length=10)

class UserPreferenceRead(UserPreferenceBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True

class UserPreferenceUpdate(BaseModel):
    notifications_enabled: Optional[bool] = None
    email_alerts_enabled: Optional[bool] = None
    dark_mode: Optional[bool] = None
    language: Optional[str] = Field(None, max_length=10)
