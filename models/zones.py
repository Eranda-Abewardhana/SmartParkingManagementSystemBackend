from sqlalchemy import Column, Integer, String, Boolean, Text
from core.database import Base

class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    code = Column(String(20), unique=True, index=True, nullable=False)
    zone_type = Column(String(50), nullable=False)
    capacity = Column(Integer, nullable=False)
    active = Column(Boolean, default=True)
    blocked = Column(Boolean, default=False)
    description = Column(Text, nullable=True)
