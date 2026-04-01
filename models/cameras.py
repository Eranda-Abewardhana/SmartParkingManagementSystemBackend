from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from core.database import Base

class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False) # Store the RTSP or Stream URL here
    is_active = Column(Boolean, default=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=True)
