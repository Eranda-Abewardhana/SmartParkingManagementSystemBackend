from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from core.database import Base
from datetime import datetime

class OccupancySnapshot(Base):
    __tablename__ = "occupancy_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    occupied_count = Column(Integer, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
    source = Column(String(50), nullable=False)
