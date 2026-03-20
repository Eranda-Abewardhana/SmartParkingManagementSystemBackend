from sqlalchemy import Column, Integer, Boolean, ForeignKey, String
from sqlalchemy.orm import relationship
from core.database import Base

class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Example preferences
    notifications_enabled = Column(Boolean, default=True)
    email_alerts_enabled = Column(Boolean, default=True)
    dark_mode = Column(Boolean, default=False)
    language = Column(String(10), default="en")
    
    # Relationship back to user
    user = relationship("User", back_populates="preferences")
