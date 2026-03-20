from sqlalchemy import Column, Integer, String, Boolean
from core.database import Base

class UniversityMember(Base):
    """
    A mock table representing the university's official database.
    Used for verifying students/staff during registration.
    """
    __tablename__ = "university_members"

    id = Column(Integer, primary_key=True, index=True)
    university_id = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    official_role = Column(String, nullable=False) # e.g., 'student', 'staff'
    is_active = Column(Boolean, default=True)
