from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, EmailStr


class UserRole(str, Enum):
    STUDENT = "student"
    STAFF = "staff"
    VISITOR = "visitor"
    ADMIN = "admin"


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.STUDENT
    phone_number: Optional[str] = Field(default=None, max_length=30)
    university_id: Optional[str] = Field(default=None, max_length=50)


class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.STUDENT
    phone_number: Optional[str] = Field(default=None, max_length=30)
    university_id: Optional[str] = Field(default=None, max_length=50)


class UserSummary(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    phone_number: Optional[str] = None
    university_id: Optional[str] = None
    role: UserRole
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class UserDetail(UserSummary):
    pass


class UserSelfUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    phone_number: Optional[str] = Field(default=None, max_length=30)


class UserStatusUpdateRequest(BaseModel):
    is_active: bool


class UserRoleUpdateRequest(BaseModel):
    role: UserRole


class UserListQuery(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    search: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: Optional[T] = None


class PaginatedUsers(BaseModel):
    items: List[UserSummary]
    total: int
    page: int
    page_size: int
