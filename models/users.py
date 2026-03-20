from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base
from schemas.users import UserRole
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    password = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    university_id = Column(String, unique=True, index=True, nullable=True)
    role = Column(String, default=UserRole.STUDENT.value, nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Visitor specific fields
    expires_at = Column(DateTime, nullable=True)  # For temporary visitor access
    purpose_of_visit = Column(String(255), nullable=True)
    host_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    vehicles = relationship("Vehicle", back_populates="owner")
    preferences = relationship("UserPreference", back_populates="user", uselist=False)
    
    # Self-referential relationship for host
    host = relationship("User", remote_side=[id])
