from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from core.database import get_db
from models.users import User
from models.preferences import UserPreference
from models.notifications import Notification, UserSettingsResponse, NotificationListPreview, NotificationSummary, \
    SettingsRequest
from routers.auth import get_current_user
from schemas.auth import ApiResponse
from schemas.preferences import UserPreferenceRead
from pydantic import BaseModel, ConfigDict
from typing import List
from datetime import datetime

router = APIRouter(prefix="/preferences", tags=["settings"])


def _get_or_create_preferences(db: Session, user_id: int) -> UserPreference:
    prefs = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if not prefs:
        prefs = UserPreference(user_id=user_id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs

@router.get(
    "/me",
    response_model=ApiResponse[UserPreferenceRead],
    status_code=status.HTTP_200_OK,
)
def get_my_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get current logged-in user's preferences
    """
    prefs = _get_or_create_preferences(db, current_user.id)

    return ApiResponse(
        message="Preferences retrieved successfully.",
        data=UserPreferenceRead.model_validate(prefs),
    )

@router.patch(
    "/me",
    response_model=ApiResponse[UserSettingsResponse],
    status_code=status.HTTP_200_OK,
)
def get_my_settings(
    payload: SettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prefs = _get_or_create_preferences(db, current_user.id)

    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(desc(Notification.created_at))
        .limit(payload.limit)
        .all()
    )

    unread_count = (
        db.query(func.count(Notification.id))
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
        .scalar()
    )

    total = (
        db.query(func.count(Notification.id))
        .filter(Notification.user_id == current_user.id)
        .scalar()
    )

    return ApiResponse(
        message="Settings retrieved successfully.",
        data=UserSettingsResponse(
            preferences=UserPreferenceRead.model_validate(prefs),
            notifications=NotificationListPreview(
                items=[NotificationSummary.model_validate(n) for n in notifications],
                total=total,
                unread_count=unread_count,
            ),
        ),
    )