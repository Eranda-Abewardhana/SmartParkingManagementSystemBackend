from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import threading
import time

from core.config import settings
from core.database import SessionLocal
from models.cameras import Camera
from services import camera_processor

from routers.admin import router as admin_router
from routers.auth import router as auth_router
from routers.cameras import cameras_router
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
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="FastAPI backend for a smart parking management prototype.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
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
app.include_router(cameras_router)

def start_autonomous_monitoring():
    """
    Automatically starts AI monitoring for all cameras in the database on server startup.
    """
    print("\n" + "="*60, flush=True)
    print("AUTONOMOUS MONITORING SYSTEM: Initializing...", flush=True)
    print("="*60, flush=True)
    
    # Wait a few seconds for DB/app to be fully ready
    time.sleep(3)
    
    db = SessionLocal()
    try:
        cameras = db.query(Camera).all()
        if not cameras:
            print("[AUTONOMOUS] No cameras found in database. Monitoring skipped.", flush=True)
            return

        for cam in cameras:
            print(f"[AUTONOMOUS] Starting monitoring for {cam.name} (URL: {cam.url})...", flush=True)
            camera_processor.start_monitoring(cam.id, cam.url, cam.zone_id)
            
        print(f"[AUTONOMOUS] Successfully started monitoring for {len(cameras)} cameras.", flush=True)
    except Exception as e:
        print(f"[AUTONOMOUS ERROR] Failed to start auto-monitoring: {e}", flush=True)
    finally:
        db.close()
    print("="*60 + "\n", flush=True)

@app.on_event("startup")
async def startup_event():
    # Run the monitoring startup in a separate thread so it doesn't block the FastAPI startup
    threading.Thread(target=start_autonomous_monitoring, daemon=True).start()
