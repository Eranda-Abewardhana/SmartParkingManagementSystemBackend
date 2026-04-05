from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from core.database import Base
from schemas.vehicles import VehicleType

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plate_number = Column(String, unique=True, index=True, nullable=False)
    vehicle_type = Column(String, nullable=False) # Store as string from Enum
    brand = Column(String, nullable=True)
    model = Column(String, nullable=True)
    color = Column(String, nullable=True)
    is_primary = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    owner = relationship("User", back_populates="vehicles")

