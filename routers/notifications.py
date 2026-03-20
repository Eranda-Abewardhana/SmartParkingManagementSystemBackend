from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from core.database import get_db
from core.websocket_manager import manager
from models.notifications import Notification
from models.users import User
from routers.auth import get_current_user, require_admin
from schemas.auth import ApiResponse
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/notifications", tags=["notifications"])

# --- Schemas ---
class NotificationSummary(BaseModel):
    id: int
    user_id: int
    title: str
    message: str
    type: str
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class NotificationListResponse(BaseModel):
    items: List[NotificationSummary]
    total: int

# --- WebSocket Endpoint ---
@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """
    Live notification feed for users and dashboard.
    """
    await manager.connect(websocket, user_id)
    try:
        while True:
            # Keep connection alive, though we mostly push server-to-client
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)

# --- Internal Helper for Real-time Alerts ---
async def create_and_notify(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    notif_type: str = "info"
):
    """
    Saves a notification to DB and pushes it via WebSocket if user is online.
    """
    new_notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=notif_type,
        is_read=False,
        created_at=datetime.utcnow()
    )
    db.add(new_notif)
    db.commit()
    db.refresh(new_notif)

    payload = {
        "event": "new_notification",
        "data": NotificationSummary.model_validate(new_notif).model_dump()
    }
    
    # Send to specific user
    await manager.send_personal_message(payload, user_id)
    
    # Also broadcast to admins for dashboard monitoring
    # (Assuming user_id=1 or role='admin' connections exist)
    await manager.broadcast({
        "event": "admin_alert",
        "data": payload["data"]
    })

# --- REST Endpoints ---
@router.get(
    "/me",
    response_model=ApiResponse[NotificationListResponse],
    status_code=status.HTTP_200_OK,
)
def get_my_notifications(
    unread_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve notification history for current user.
    """
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    
    if unread_only:
        query = query.filter(Notification.is_read == False)

    notifications = query.order_by(desc(Notification.created_at)).all()
    
    return ApiResponse(
        message="Notifications retrieved successfully.",
        data=NotificationListResponse(
            items=[NotificationSummary.model_validate(n) for n in notifications],
            total=len(notifications)
        )
    )

@router.patch("/mark-read/{notif_id}", response_model=ApiResponse)
def mark_as_read(
    notif_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mark a specific notification as read.
    """
    notif = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.user_id == current_user.id
    ).first()
    
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found.")

    notif.is_read = True
    db.commit()
    
    return ApiResponse(message="Notification marked as read.")
