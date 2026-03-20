from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.admin import router as admin_router
from routers.auth import router as auth_router
from routers.entry_exit_logs import router as entry_exit_logs_router
from routers.lpr import router as lpr_router
from routers.notifications import router as notifications_router
from routers.occupancy import router as occupancy_router
from routers.reservations import router as reservations_router
from routers.users import router as users_router
from routers.vehicles import router as vehicles_router
from routers.zones import router as zones_router
from routers.preferences import router as preferences_router
from routers.reports import router as reports_router

app = FastAPI(
    title="Smart Parking Management API",
    version="0.1.0",
    description="FastAPI backend for a smart parking management prototype.",
)

# TODO:
# - Restrict allowed origins for production
# - Move CORS settings to config/environment variables
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(vehicles_router)
app.include_router(zones_router)
app.include_router(reservations_router)
app.include_router(entry_exit_logs_router)
app.include_router(lpr_router)
app.include_router(occupancy_router)
app.include_router(admin_router)
app.include_router(notifications_router)
app.include_router(preferences_router)
app.include_router(reports_router)


@app.get("/", tags=["root"])
def read_root():
    """
    Root endpoint for the Smart Parking Management API.
    """
    return {
        "message": "Smart Parking Management API is running.",
        "version": "0.1.0",
    }


@app.get("/health", tags=["health"])
def health_check():
    """
    Basic health check endpoint.
    """
    return {
        "status": "ok",
        "service": "smart-parking-api",
    }