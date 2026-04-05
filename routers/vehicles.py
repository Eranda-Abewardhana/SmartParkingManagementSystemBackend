from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from core.database import get_db
from models.vehicles import Vehicle
from models.users import User
from routers.auth import get_current_user, require_admin
from schemas.vehicles import (
    ApiResponse,
    VehicleCreateRequest,
    VehicleDetail,
    VehicleListResponse,
    VehiclePrimaryUpdateRequest,
    VehicleSummary,
    VehicleUpdateRequest,
)

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


def _to_vehicle_summary(vehicle: Vehicle) -> VehicleSummary:
    return VehicleSummary.model_validate(vehicle)


def _to_vehicle_detail(vehicle: Vehicle) -> VehicleDetail:
    return VehicleDetail.model_validate(vehicle)


def _ensure_owner_or_admin(vehicle: Vehicle, current_user: User) -> None:
    if vehicle.owner_user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this vehicle.",
        )


def _set_primary_vehicle_for_user(db: Session, user_id: int, vehicle_id: int) -> None:
    """
    Ensure only one active primary vehicle per user.
    """
    db.query(Vehicle).filter(
        Vehicle.owner_user_id == user_id,
        Vehicle.is_active == True
    ).update({Vehicle.is_primary: False}, synchronize_session=False)

    db.query(Vehicle).filter(
        Vehicle.id == vehicle_id
    ).update({Vehicle.is_primary: True}, synchronize_session=False)
    db.commit()


@router.post(
    "/",
    response_model=ApiResponse[VehicleDetail],
    status_code=status.HTTP_201_CREATED,
)
def create_vehicle(
    payload: VehicleCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a vehicle. Admins can specify owner_user_id.
    """
    # Determine the owner
    owner_id = current_user.id
    if payload.owner_user_id is not None:
        if current_user.role != "admin":
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can specify an owner_user_id.",
            )
        owner_id = payload.owner_user_id

    existing = db.query(Vehicle).filter(
        Vehicle.plate_number == payload.plate_number.strip().upper(),
        Vehicle.is_active == True
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A vehicle with this plate number already exists.",
        )

    new_vehicle = Vehicle(
        owner_user_id=owner_id,
        plate_number=payload.plate_number.strip().upper(),
        vehicle_type=payload.vehicle_type.value,
        brand=payload.brand,
        model=payload.model,
        color=payload.color,
        is_primary=payload.is_primary,
        is_active=True,
    )

    db.add(new_vehicle)
    db.commit()
    db.refresh(new_vehicle)

    if payload.is_primary:
        _set_primary_vehicle_for_user(db, owner_id, new_vehicle.id)
    else:
        # If this is the only active vehicle, make it primary
        count = db.query(Vehicle).filter(
            Vehicle.owner_user_id == owner_id,
            Vehicle.is_active == True
        ).count()
        if count == 1:
            new_vehicle.is_primary = True
            db.commit()
            db.refresh(new_vehicle)

    return ApiResponse(
        message="Vehicle created successfully.",
        data=_to_vehicle_detail(new_vehicle),
    )


@router.get(
    "/me",
    response_model=ApiResponse[List[VehicleSummary]],
    status_code=status.HTTP_200_OK,
)
def get_my_vehicles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Return all active vehicles of the current user.
    """
    vehicles = db.query(Vehicle).filter(
        Vehicle.owner_user_id == current_user.id,
        Vehicle.is_active == True
    ).all()

    return ApiResponse(
        message="User vehicles retrieved successfully.",
        data=[_to_vehicle_summary(v) for v in vehicles],
    )


@router.get(
    "/{vehicle_id}",
    response_model=ApiResponse[VehicleDetail],
    status_code=status.HTTP_200_OK,
)
def get_vehicle(
    vehicle_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Return one vehicle.
    """
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id,
        Vehicle.is_active == True
    ).first()

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found.",
        )

    _ensure_owner_or_admin(vehicle, current_user)

    return ApiResponse(
        message="Vehicle retrieved successfully.",
        data=_to_vehicle_detail(vehicle),
    )


@router.put(
    "/{vehicle_id}",
    response_model=ApiResponse[VehicleDetail],
    status_code=status.HTTP_200_OK,
)
def update_vehicle(
    vehicle_id: int,
    payload: VehicleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update a vehicle.
    """
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id,
        Vehicle.is_active == True
    ).first()

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found.",
        )

    _ensure_owner_or_admin(vehicle, current_user)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update.",
        )

    if "plate_number" in update_data:
        new_plate = update_data["plate_number"].strip().upper()
        duplicate = db.query(Vehicle).filter(
            Vehicle.plate_number == new_plate,
            Vehicle.id != vehicle_id,
            Vehicle.is_active == True
        ).first()
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A vehicle with this plate number already exists.",
            )
        vehicle.plate_number = new_plate

    if "vehicle_type" in update_data:
        vehicle.vehicle_type = update_data["vehicle_type"].value

    for field in ["brand", "model", "color"]:
        if field in update_data:
            setattr(vehicle, field, update_data[field])

    db.commit()
    db.refresh(vehicle)

    if update_data.get("is_primary"):
        _set_primary_vehicle_for_user(db, vehicle.owner_user_id, vehicle.id)
        db.refresh(vehicle)

    return ApiResponse(
        message="Vehicle updated successfully.",
        data=_to_vehicle_detail(vehicle),
    )


@router.delete(
    "/{vehicle_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_vehicle(
    vehicle_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Soft delete (deactivate) a vehicle.
    """
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id,
        Vehicle.is_active == True
    ).first()

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found.",
        )

    _ensure_owner_or_admin(vehicle, current_user)

    was_primary = vehicle.is_primary
    owner_id = vehicle.owner_user_id

    vehicle.is_active = False
    vehicle.is_primary = False
    db.commit()

    if was_primary:
        # Assign primary to another active vehicle of the same owner
        next_primary = db.query(Vehicle).filter(
            Vehicle.owner_user_id == owner_id,
            Vehicle.is_active == True
        ).first()
        if next_primary:
            next_primary.is_primary = True
            db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{vehicle_id}/primary",
    response_model=ApiResponse[VehicleDetail],
    status_code=status.HTTP_200_OK,
)
def mark_vehicle_as_primary(
    vehicle_id: int,
    payload: VehiclePrimaryUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mark a vehicle as the primary/default vehicle for the current user.
    """
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id,
        Vehicle.is_active == True
    ).first()

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found.",
        )

    if vehicle.owner_user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify primary vehicle status.",
        )

    if payload.is_primary is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint only supports setting a vehicle as primary.",
        )

    _set_primary_vehicle_for_user(db, vehicle.owner_user_id, vehicle.id)
    db.refresh(vehicle)

    return ApiResponse(
        message="Vehicle marked as primary successfully.",
        data=_to_vehicle_detail(vehicle),
    )


@router.get(
    "/",
    response_model=ApiResponse[VehicleListResponse],
    status_code=status.HTTP_200_OK,
)
def list_all_vehicles(
    plate_number: Optional[str] = Query(default=None),
    user_id: Optional[int] = Query(default=None, ge=1),
    is_active: Optional[bool] = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin only. List all vehicles with filters.
    """
    query = db.query(Vehicle)

    if plate_number:
        query = query.filter(Vehicle.plate_number.ilike(f"%{plate_number.strip()}%"))

    if user_id is not None:
        query = query.filter(Vehicle.owner_user_id == user_id)

    if is_active is not None:
        query = query.filter(Vehicle.is_active == is_active)

    vehicles = query.all()

    data = VehicleListResponse(
        items=[_to_vehicle_summary(v) for v in vehicles],
        total=len(vehicles),
    )

    return ApiResponse(
        message="Vehicles retrieved successfully.",
        data=data,
    )
