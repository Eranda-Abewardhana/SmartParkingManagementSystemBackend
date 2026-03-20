from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from core.database import Base
from datetime import datetime

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action_type = Column(String, nullable=False)
    admin_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    details = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
