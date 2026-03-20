from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from core.database import Base
from datetime import datetime, timedelta

class PasswordResetCode(Base):
    """
    Temporary table to store 6-digit verification codes for password reset.
    """
    __tablename__ = "password_reset_codes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def is_valid(self):
        return not self.is_used and datetime.utcnow() < self.expires_at
