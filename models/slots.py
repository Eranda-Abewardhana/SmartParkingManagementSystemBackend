from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base

class ParkingSlot(Base):
    __tablename__ = "parking_slots"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    slot_number = Column(String(20), nullable=False)
    is_active = Column(Boolean, default=True)

    zone = relationship("Zone", back_populates="slots")
    reservations = relationship("Reservation", back_populates="slot")
