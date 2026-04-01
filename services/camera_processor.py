import threading
import time
import cv2
import logging
from typing import Dict, Optional
from core.database import SessionLocal
from services import vision_ai_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CameraWorker(threading.Thread):
    """
    Background worker that continuously reads frames from a camera source
    and runs the AI processing pipeline.
    """
    def __init__(self, camera_id: int, camera_url: str, zone_id: Optional[int]):
        super().__init__(name=f"Worker-{camera_id}", daemon=True)
        self.camera_id = camera_id
        self.camera_url = camera_url
        self.zone_id = zone_id
        self._stop_event = threading.Event()
        
        # Resolve capture source
        if str(camera_url).isdigit():
            self.capture_source = int(camera_url)
        else:
            self.capture_source = camera_url
        
        print(f"\n[AUTONOMOUS MONITORING] INIT: Camera {camera_id} (Source: {self.capture_source})", flush=True)

    def stop(self):
        print(f"[AUTONOMOUS MONITORING] STOP: Camera {self.camera_id}", flush=True)
        self._stop_event.set()

    def run(self):
        print(f"[AUTONOMOUS MONITORING] START: Camera {self.camera_id} loop is now RUNNING.", flush=True)
        
        cap = cv2.VideoCapture(self.capture_source)
        frame_count = 0
        last_log_time = time.time()
        
        try:
            while not self._stop_event.is_set():
                # Periodic status print (every 10s) even if camera is failing
                if time.time() - last_log_time > 10:
                    status = "ONLINE" if cap.isOpened() else "OFFLINE"
                    print(f"[AUTONOMOUS MONITORING - STATUS] Camera {self.camera_id} is {status}. (Frames processed: {frame_count})", flush=True)
                    last_log_time = time.time()

                if not cap.isOpened():
                    print(f"[AUTONOMOUS MONITORING - ERROR] Camera {self.camera_id} source NOT OPEN. Retrying in 5s...", flush=True)
                    cap.release()
                    time.sleep(5)
                    cap = cv2.VideoCapture(self.capture_source)
                    continue

                ret, frame = cap.read()
                
                if not ret or frame is None:
                    # Don't spam, just wait a bit
                    time.sleep(1)
                    continue

                frame_count += 1
                
                # Run AI Pipeline every 30 frames (~1 sec)
                if frame_count % 30 == 0 or frame_count == 1:
                    db = SessionLocal()
                    try:
                        # This will trigger the VisionService and print slot/plate details
                        vision_ai_service.process_frame(
                            camera_id=self.camera_id,
                            zone_id=self.zone_id,
                            frame=frame,
                            refresh_slots=(frame_count % 300 == 0 or frame_count == 1),
                            db=db
                        )
                    except Exception as e:
                        print(f"[AUTONOMOUS MONITORING - AI ERROR] Camera {self.camera_id}: {e}", flush=True)
                    finally:
                        db.close()
                
                # Small sleep to prevent CPU starvation
                time.sleep(0.01)

        except Exception as e:
            print(f"[AUTONOMOUS MONITORING - CRITICAL] Camera {self.camera_id} crashed: {e}", flush=True)
        finally:
            cap.release()
            print(f"[AUTONOMOUS MONITORING] FINISHED: Camera {self.camera_id} worker stopped.", flush=True)


# Registry of active background threads
active_workers: Dict[int, CameraWorker] = {}

def start_monitoring(camera_id: int, camera_url: str, zone_id: Optional[int]):
    """Starts the AI background loop for a specific camera."""
    if camera_id in active_workers and active_workers[camera_id].is_alive():
        return

    worker = CameraWorker(camera_id, camera_url, zone_id)
    active_workers[camera_id] = worker
    worker.start()

def stop_monitoring(camera_id: int):
    """Stops the AI background loop for a specific camera."""
    if worker := active_workers.pop(camera_id, None):
        worker.stop()
        worker.join(timeout=2)

def is_running(camera_id: int) -> bool:
    """Checks if the background loop is active."""
    return camera_id in active_workers and active_workers[camera_id].is_alive()
