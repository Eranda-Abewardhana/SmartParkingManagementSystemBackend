from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from core.database import get_db
from core.security import hash_password
from models.users import User
from routers.auth import get_current_user, require_admin
from schemas.users import (
    ApiResponse,
    PaginatedUsers,
    UserCreateRequest,
    UserDetail,
    UserRole,
    UserRoleUpdateRequest,
    UserSelfUpdateRequest,
    UserStatusUpdateRequest,
    UserSummary,
)

router = APIRouter(prefix="/users", tags=["users"])


def _to_user_summary(user: User) -> UserSummary:
    return UserSummary.model_validate(user)


def _to_user_detail(user: User) -> UserDetail:
    return UserDetail.model_validate(user)


@router.post(
    "/",
    response_model=ApiResponse[UserDetail],
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin only. Create a new user.
    """
    existing_user = db.query(User).filter(
        or_(User.username == payload.username, User.email == payload.email)
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists.",
        )

    new_user = User(
        username=payload.username,
        email=payload.email.lower(),
        full_name=payload.full_name,
        password=hash_password(payload.password),
        role=payload.role.value,
        phone_number=payload.phone_number,
        is_active=True,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return ApiResponse(
        message="User created successfully.",
        data=_to_user_detail(new_user),
    )


@router.get(
    "/me",
    response_model=ApiResponse[UserDetail],
    status_code=status.HTTP_200_OK,
)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """
    Return the current authenticated user's profile.
    """
    return ApiResponse(
        message="Current user profile retrieved successfully.",
        data=_to_user_detail(current_user),
    )


@router.put(
    "/me",
    response_model=ApiResponse[UserDetail],
    status_code=status.HTTP_200_OK,
)
def update_my_profile(
    payload: UserSelfUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update current user's basic profile fields.
    """
    update_data = payload.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update.",
        )

    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)

    return ApiResponse(
        message="Profile updated successfully.",
        data=_to_user_detail(current_user),
    )


@router.get(
    "/",
    response_model=ApiResponse[PaginatedUsers],
    status_code=status.HTTP_200_OK,
)
def list_users(
    role: Optional[UserRole] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    search: Optional[str] = Query(default=None, min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin only. List users with optional filters.
    """
    query = db.query(User)

    if role is not None:
        query = query.filter(User.role == role.value)

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    if search:
        term = f"%{search.lower()}%"
        query = query.filter(
            or_(
                User.username.ilike(term),
                User.email.ilike(term),
                User.full_name.ilike(term)
            )
        )

    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()

    data = PaginatedUsers(
        items=[_to_user_summary(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )

    return ApiResponse(
        message="Users retrieved successfully.",
        data=data,
    )


@router.get(
    "/{user_id}",
    response_model=ApiResponse[UserDetail],
    status_code=status.HTTP_200_OK,
)
def get_user_by_id(
    user_id: int, 
    _: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Admin only. Return full user details by user ID.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return ApiResponse(
        message="User retrieved successfully.",
        data=_to_user_detail(user),
    )


@router.patch(
    "/{user_id}/status",
    response_model=ApiResponse[UserDetail],
    status_code=status.HTTP_200_OK,
)
def update_user_status(
    user_id: int,
    payload: UserStatusUpdateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin only. Activate or deactivate a user.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)

    return ApiResponse(
        message="User status updated successfully.",
        data=_to_user_detail(user),
    )


@router.patch(
    "/{user_id}/role",
    response_model=ApiResponse[UserDetail],
    status_code=status.HTTP_200_OK,
)
def update_user_role(
    user_id: int,
    payload: UserRoleUpdateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin only. Change user role.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    user.role = payload.role.value
    db.commit()
    db.refresh(user)

    return ApiResponse(
        message="User role updated successfully.",
        data=_to_user_detail(user),
    )
