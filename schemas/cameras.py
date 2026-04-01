from typing import Optional
from pydantic import BaseModel

class CameraCreateRequest(BaseModel):
    name: str
    url: str
    zone_id: Optional[int] = None

class CameraUpdateRequest(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    zone_id: Optional[int] = None