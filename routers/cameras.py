import time
import cv2
import numpy as np
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.database import get_db, SessionLocal
from models.cameras import Camera
from schemas.cameras import CameraUpdateRequest, CameraCreateRequest
from services import vision_ai_service, camera_processor
from services.streaming_service import CameraStreamer, is_youtube_url

cameras_router = APIRouter(prefix="/cameras", tags=["cameras"])

def ai_frame_generator(camera_id: int):
    """
    Yields the latest AI-annotated frame from the background processor.
    """
    while True:
        try:
            # This frame is updated by the CameraWorker in camera_processor.py
            frame = vision_ai_service.latest_frames.get(camera_id)

            if frame:
                yield frame
            else:
                # Fallback blank frame with info
                blank = 255 * np.ones((480, 640, 3), dtype="uint8")
                cv2.putText(blank, "AI Monitoring Not Started", (100, 240), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                cv2.putText(blank, "Call /start-ai to begin", (150, 280), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (50, 50, 50), 2)
                ok, buffer = cv2.imencode(".jpg", blank)
                if ok:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")

            time.sleep(0.1) # Smooth stream refresh rate
        except Exception as e:
            print(f"[ROUTER ERROR] AI stream failure: {e}")
            time.sleep(1)

@cameras_router.get("/")
def list_cameras(db: Session = Depends(get_db)):
    return db.query(Camera).all()

@cameras_router.post("/", status_code=201)
def add_camera(payload: CameraCreateRequest, db: Session = Depends(get_db)):
    url = (payload.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Camera URL is required")
    if is_youtube_url(url):
        raise HTTPException(status_code=400, detail="YouTube URLs not supported")

    new_cam = Camera(name=payload.name.strip(), url=url, zone_id=payload.zone_id)
    db.add(new_cam)
    db.commit()
    db.refresh(new_cam)
    return new_cam

@cameras_router.get("/stream/{camera_id}")
def stream_camera(camera_id: int, db: Session = Depends(get_db)):
    """Standard raw stream."""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    try:
        streamer = CameraStreamer(camera.url)
        return StreamingResponse(
            streamer.generate_raw_frames(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@cameras_router.get("/ai-stream/{camera_id}")
def ai_stream_camera(camera_id: int, db: Session = Depends(get_db)):
    """Annotated stream with slot boxes and plate numbers."""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    return StreamingResponse(
        ai_frame_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

@cameras_router.post("/{camera_id}/start-ai")
def start_ai(camera_id: int, db: Session = Depends(get_db)):
    """Starts the continuous background AI monitoring."""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    if camera_processor.is_running(camera_id):
        return {"message": "AI already running"}

    # Trigger background thread
    camera_processor.start_monitoring(camera.id, camera.url, camera.zone_id)
    print(f"[ROUTER] Triggered AI Worker for camera {camera_id}", flush=True)
    
    return {
        "message": "AI monitoring started successfully",
        "camera_id": camera.id,
        "zone_id": camera.zone_id,
    }

@cameras_router.post("/{camera_id}/stop-ai")
def stop_ai(camera_id: int, db: Session = Depends(get_db)):
    """Stops the continuous background AI monitoring."""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    camera_processor.stop_monitoring(camera_id)
    return {"message": "AI monitoring stopped"}

@cameras_router.get("/{camera_id}/ai-results")
def get_ai_results(camera_id: int, db: Session = Depends(get_db)):
    """Returns the latest JSON analysis for occupancy and plates."""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    data = vision_ai_service.latest_results.get(camera_id)
    if not data:
        return {"camera_id": camera_id, "message": "No AI results available. Start AI first."}

    return data

@cameras_router.get("/{camera_id}/ai-status")
def get_ai_status(camera_id: int, db: Session = Depends(get_db)):
    """Checks if AI worker is alive."""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    return {
        "camera_id": camera_id,
        "running": camera_processor.is_running(camera_id),
        "last_update": vision_ai_service.latest_results.get(camera_id, {}).get("timestamp")
    }

@cameras_router.post("/{camera_id}/detect-once")
def detect_once(camera_id: int, db: Session = Depends(get_db)):
    """Manual single-frame detection (Debug)."""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    try:
        streamer = CameraStreamer(camera.url)
        cap = streamer.get_capture()
        ok, frame = cap.read()
        cap.release()

        if not ok or frame is None:
            raise HTTPException(status_code=400, detail="Failed to read frame from source")

        result = vision_ai_service.process_frame(
            camera_id=camera_id,
            zone_id=camera.zone_id,
            frame=frame,
            refresh_slots=True,
            db=db,
        )
        return {"message": "Manual detection completed", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@cameras_router.delete("/{camera_id}")
def delete_camera(camera_id: int, db: Session = Depends(get_db)):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    camera_processor.stop_monitoring(camera_id)
    vision_ai_service.latest_frames.pop(camera_id, None)
    vision_ai_service.latest_results.pop(camera_id, None)

    db.delete(camera)
    db.commit()
    return {"message": "Camera deleted and monitoring stopped"}

@cameras_router.put("/{camera_id}")
def update_camera(camera_id: int, payload: CameraUpdateRequest, db: Session = Depends(get_db)):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    if payload.name: camera.name = payload.name.strip()
    if payload.url: camera.url = payload.url.strip()
    if payload.zone_id is not None: camera.zone_id = payload.zone_id

    db.commit()
    return camera
