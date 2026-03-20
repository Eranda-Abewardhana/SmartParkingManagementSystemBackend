from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from core.database import Base
from datetime import datetime

class EntryExitLog(Base):
    __tablename__ = "entry_exit_logs"

    id = Column(Integer, primary_key=True, index=True)
    plate_number = Column(String(20), nullable=False)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=True)
    gate_type = Column(String(10), nullable=False) # 'entry' or 'exit'
    timestamp = Column(DateTime, default=datetime.utcnow)
    source = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False)
    is_overstayed = Column(Boolean, default=False)
    notes = Column(String(255), nullable=True)
