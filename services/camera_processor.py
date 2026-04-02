import threading
import time
import cv2
import logging
from typing import Dict, Optional
from core.database import SessionLocal
from services import vision_ai_service

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
        self.capture_source = camera_url

        # Runtime state
        self.cap = None
        self.frame_count = 0
        self.last_status_log_time = 0.0
        self.last_ai_run_time = 0.0
        self.last_slot_refresh_time = 0.0
        self.consecutive_read_failures = 0
        self.consecutive_ai_failures = 0

        # Tunables
        self.status_log_interval = 10          # seconds
        self.ai_interval_seconds = 0.5         # run AI every 0.5 seconds (was 1.0)
        self.slot_refresh_interval = 15.0      # force slot refresh every 15 seconds (was 20)
        self.reconnect_delay = 3.0             # seconds
        self.read_fail_retry_delay = 0.1       # seconds
        self.max_read_failures_before_reconnect = 10
        self.loop_sleep = 0.005

        print(
            f"\n[AUTONOMOUS MONITORING] INIT: Camera {camera_id} "
            f"(Source: {self.capture_source})",
            flush=True
        )

    def stop(self):
        print(f"[AUTONOMOUS MONITORING] STOP: Camera {self.camera_id}", flush=True)
        self._stop_event.set()

    def _open_capture(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass

        self.cap = cv2.VideoCapture(self.capture_source)

        # Optional buffer reduction for live streams
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        if self.cap.isOpened():
            print(
                f"[AUTONOMOUS MONITORING] Camera {self.camera_id} capture opened successfully.",
                flush=True
            )
        else:
            print(
                f"[AUTONOMOUS MONITORING - ERROR] Camera {self.camera_id} failed to open capture.",
                flush=True
            )

    def _log_status(self):
        now = time.time()
        if now - self.last_status_log_time >= self.status_log_interval:
            status = "ONLINE" if self.cap is not None and self.cap.isOpened() else "OFFLINE"
            print(
                f"[AUTONOMOUS MONITORING - STATUS] "
                f"Camera {self.camera_id} is {status} | "
                f"Frames: {self.frame_count} | "
                f"ReadFails: {self.consecutive_read_failures} | "
                f"AIFails: {self.consecutive_ai_failures}",
                flush=True
            )
            self.last_status_log_time = now

    def _should_run_ai(self) -> bool:
        return (time.time() - self.last_ai_run_time) >= self.ai_interval_seconds

    def _should_refresh_slots(self) -> bool:
        return (
            self.frame_count == 1
            or (time.time() - self.last_slot_refresh_time) >= self.slot_refresh_interval
        )

    def _run_ai(self, frame):
        refresh_slots = self._should_refresh_slots()
        db = SessionLocal()

        try:
            result = vision_ai_service.process_frame(
                camera_id=self.camera_id,
                zone_id=self.zone_id,
                frame=frame,
                refresh_slots=refresh_slots,
                db=db,
            )

            self.last_ai_run_time = time.time()

            if refresh_slots:
                self.last_slot_refresh_time = self.last_ai_run_time

            if isinstance(result, dict) and result.get("error"):
                self.consecutive_ai_failures += 1
            else:
                self.consecutive_ai_failures = 0

        except Exception as e:
            self.consecutive_ai_failures += 1
            print(
                f"[AUTONOMOUS MONITORING - AI EXCEPTION] Camera {self.camera_id}: {e}",
                flush=True
            )
        finally:
            db.close()

    def run(self):
        print(
            f"[AUTONOMOUS MONITORING] START: Camera {self.camera_id} loop is now RUNNING.",
            flush=True
        )

        self._open_capture()

        try:
            while not self._stop_event.is_set():
                self._log_status()

                if self.cap is None or not self.cap.isOpened():
                    time.sleep(self.reconnect_delay)
                    self._open_capture()
                    continue

                ret, frame = self.cap.read()

                if not ret or frame is None:
                    self.consecutive_read_failures += 1

                    if self.consecutive_read_failures >= self.max_read_failures_before_reconnect:
                        self._open_capture()
                        self.consecutive_read_failures = 0
                        time.sleep(self.reconnect_delay)
                    else:
                        time.sleep(self.read_fail_retry_delay)

                    continue

                self.consecutive_read_failures = 0
                self.frame_count += 1

                # Keep aspect ratio and avoid giant frames slowing OCR/detection
                try:
                    h, w = frame.shape[:2]
                    max_width = 1920 # Increased from 1280 to allow more detail
                    if w > max_width:
                        scale = max_width / float(w)
                        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
                except Exception as e:
                    pass

                if self._should_run_ai():
                    self._run_ai(frame)

                time.sleep(self.loop_sleep)

        except Exception as e:
            print(
                f"[AUTONOMOUS MONITORING - CRITICAL] Camera {self.camera_id} crashed: {e}",
                flush=True
            )
        finally:
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass

            print(
                f"[AUTONOMOUS MONITORING] FINISHED: Camera {self.camera_id} worker stopped.",
                flush=True
            )


# Registry of active background threads
active_workers: Dict[int, CameraWorker] = {}


def start_monitoring(camera_id: int, camera_url: str, zone_id: Optional[int]):
    """Starts the AI background loop for a specific camera."""
    existing = active_workers.get(camera_id)
    if existing and existing.is_alive():
        return

    worker = CameraWorker(camera_id, camera_url, zone_id)
    active_workers[camera_id] = worker
    worker.start()


def stop_monitoring(camera_id: int):
    """Stops the AI background loop for a specific camera."""
    worker = active_workers.pop(camera_id, None)
    if worker:
        worker.stop()
        worker.join(timeout=3)


def is_running(camera_id: int) -> bool:
    """Checks if the background loop is active."""
    return camera_id in active_workers and active_workers[camera_id].is_alive()
