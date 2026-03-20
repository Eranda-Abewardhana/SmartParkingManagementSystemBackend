from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from core.database import get_db
from models.users import User
from models.preferences import UserPreference
from schemas.preferences import UserPreferenceRead, UserPreferenceUpdate
from routers.auth import get_current_user
from schemas.auth import ApiResponse

router = APIRouter(prefix="/preferences", tags=["preferences"])


def _get_or_create_preferences(db: Session, user_id: int) -> UserPreference:
    """
    Ensure a preference object exists for the user.
    """
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
    db: Session = Depends(get_db)
):
    """
    Retrieve current user's preferences.
    """
    prefs = _get_or_create_preferences(db, current_user.id)
    return ApiResponse(
        message="Preferences retrieved successfully.",
        data=UserPreferenceRead.model_validate(prefs),
    )


@router.patch(
    "/me",
    response_model=ApiResponse[UserPreferenceRead],
    status_code=status.HTTP_200_OK,
)
def update_my_preferences(
    payload: UserPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update specific user preferences.
    """
    prefs = _get_or_create_preferences(db, current_user.id)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update.",
        )

    for field, value in update_data.items():
        setattr(prefs, field, value)

    db.commit()
    db.refresh(prefs)

    return ApiResponse(
        message="Preferences updated successfully.",
        data=UserPreferenceRead.model_validate(prefs),
    )
