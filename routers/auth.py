import random
import string
from datetime import datetime, timedelta
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status, Request
from jose import JWTError
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from core.security import create_access_token, decode_access_token, verify_password, hash_password
from core.rate_limiter import login_rate_limiter
from models.users import User
from models.university import UniversityMember
from models.auth import PasswordResetCode
from schemas.auth import (
    ApiResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    RefreshResponse,
    PasswordResetRequest,
    PasswordResetVerify,
    PasswordResetComplete,
)
from schemas.users import UserRegisterRequest, UserSummary, UserDetail, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_user_summary(user: User) -> UserSummary:
    return UserSummary(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        university_id=user.university_id,
        role=user.role,
        is_active=user.is_active,
    )


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db)
) -> User:
    """
    Retrieve the current authenticated user from the database.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required.",
        )

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format.",
        )

    token = parts[1]

    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if subject is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload.",
            )

        user = db.query(User).filter(User.id == int(subject)).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive.",
            )

        return user

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject.",
        ) from None


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to ensure the current user has an admin role.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user


@router.post(
    "/register",
    response_model=ApiResponse[UserDetail],
    status_code=status.HTTP_201_CREATED,
)
def register(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new user. Verifies university_id if provided for Students/Staff.
    """
    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.username == payload.username) | (User.email == payload.email)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists.",
        )

    # University ID Verification logic
    if payload.role in [UserRole.STUDENT, UserRole.STAFF]:
        if not payload.university_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"University ID is required for {payload.role.value} registration.",
            )
        
        # Check if university_id is already used by another account
        id_taken = db.query(User).filter(User.university_id == payload.university_id).first()
        if id_taken:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This University ID is already linked to an account.",
            )

        # Verify against official university database (mock table)
        uni_member = db.query(UniversityMember).filter(
            UniversityMember.university_id == payload.university_id,
            UniversityMember.is_active == True
        ).first()

        if not uni_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid University ID. Not found in official records.",
            )
        
        # Optional: verify email matches university records
        if uni_member.email.lower() != payload.email.lower():
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email does not match the record for this University ID.",
            )

    new_user = User(
        username=payload.username,
        email=payload.email.lower(),
        full_name=payload.full_name,
        password=hash_password(payload.password),
        role=payload.role.value,
        phone_number=payload.phone_number,
        university_id=payload.university_id,
        is_active=True,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return ApiResponse(
        message="Registration successful.",
        data=UserDetail.model_validate(new_user),
    )


@router.post(
    "/login",
    response_model=ApiResponse[LoginResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(login_rate_limiter)] # Apply Rate Limiting
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate a user using email or username plus password.
    """
    user = db.query(User).filter(
        (User.email == payload.email_or_username.lower()) | 
        (User.username == payload.email_or_username.lower())
    ).first()

    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive.",
        )

    access_token = create_access_token(
        subject=user.id,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return ApiResponse(
        message="Login successful.",
        data=LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user=_to_user_summary(user),
        ),
    )


@router.post("/password-reset/request", response_model=ApiResponse)
def request_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    """
    Step 1: Request a password reset. Sends a 6-digit code to the email.
    """
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user:
        # Avoid user enumeration by returning a generic success message
        return ApiResponse(message="If the email exists, a reset code has been sent.")

    # Generate 6-digit code
    code = "".join(random.choices(string.digits, k=6))
    expires_at = datetime.utcnow() + timedelta(minutes=15)

    # Store code (invalidate any existing codes for this email)
    db.query(PasswordResetCode).filter(PasswordResetCode.email == user.email).update({"is_used": True})
    
    reset_entry = PasswordResetCode(
        email=user.email,
        code=code,
        expires_at=expires_at
    )
    db.add(reset_entry)
    db.commit()

    # PROTOTYPE NOTE: In a real app, you'd call an email service here.
    # Printing to console for debugging/prototype purposes.
    print(f"DEBUG: Password reset code for {user.email} is: {code}")

    return ApiResponse(message="Verification code sent to your email.")


@router.post("/password-reset/verify", response_model=ApiResponse)
def verify_reset_code(payload: PasswordResetVerify, db: Session = Depends(get_db)):
    """
    Step 2: Verify the 6-digit code.
    """
    record = db.query(PasswordResetCode).filter(
        PasswordResetCode.email == payload.email.lower(),
        PasswordResetCode.code == payload.code,
        PasswordResetCode.is_used == False
    ).order_by(PasswordResetCode.created_at.desc()).first()

    if not record or not record.is_valid():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code."
        )

    return ApiResponse(message="Code verified successfully.")


@router.post("/password-reset/complete", response_model=ApiResponse)
def complete_password_reset(payload: PasswordResetComplete, db: Session = Depends(get_db)):
    """
    Step 3: Provide the code again + the new password to update.
    """
    # 1. Validate code again
    record = db.query(PasswordResetCode).filter(
        PasswordResetCode.email == payload.email.lower(),
        PasswordResetCode.code == payload.code,
        PasswordResetCode.is_used == False
    ).first()

    if not record or not record.is_valid():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code."
        )

    # 2. Update user password
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.password = hash_password(payload.new_password)
    record.is_used = True
    db.commit()

    return ApiResponse(message="Password has been reset successfully.")


@router.post(
    "/logout",
    response_model=ApiResponse[LogoutResponse],
    status_code=status.HTTP_200_OK,
)
def logout(current_user: User = Depends(get_current_user)):
    """
    Prototype-safe logout endpoint.
    """
    return ApiResponse(
        message="Logout successful.",
        data=LogoutResponse(detail=f"User '{current_user.username}' logged out."),
    )


@router.get(
    "/me",
    response_model=ApiResponse[UserSummary],
    status_code=status.HTTP_200_OK,
)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Return current authenticated user profile summary.
    """
    return ApiResponse(
        message="Current user retrieved successfully.",
        data=_to_user_summary(current_user),
    )


@router.post(
    "/refresh",
    response_model=ApiResponse[RefreshResponse],
    status_code=status.HTTP_200_OK,
)
def refresh_token(current_user: User = Depends(get_current_user)):
    """
    Issue a new access token for the currently authenticated user.
    """
    new_access_token = create_access_token(
        subject=current_user.id,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return ApiResponse(
        message="Token refreshed successfully.",
        data=RefreshResponse(
            access_token=new_access_token,
            token_type="bearer",
        ),
    )
