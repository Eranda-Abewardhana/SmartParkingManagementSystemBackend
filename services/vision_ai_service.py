import time
import cv2
import logging
from typing import Dict, Any, Optional, List
from services.vision_service import VisionService

# Global thread-safe state
latest_frames: Dict[int, bytes] = {}
latest_results: Dict[int, Dict[str, Any]] = {}
_recent_plate_logs: Dict[str, float] = {}
# Cache slots per camera to prevent the "jumpy" slot count (5 to 15)
_camera_slot_cache: Dict[int, List[Dict[str, Any]]] = {}

def encode_frame(frame) -> Optional[bytes]:
    if frame is None: return None
    ok, buffer = cv2.imencode(".jpg", frame)
    if not ok: return None
    return (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")

def should_log_plate(camera_id: int, plate_number: str, cooldown_seconds: int = 60) -> bool:
    if not plate_number or len(plate_number) < 4: return False
    now = time.time()
    key = f"{camera_id}:{plate_number}"
    last_logged = _recent_plate_logs.get(key)
    if last_logged is not None and (now - last_logged) < cooldown_seconds: return False
    _recent_plate_logs[key] = now
    return True

def log_plate_detection(db, plate_number: str, zone_id: Optional[int], camera_id: int):
    try:
        from models.entry_exit_logs import EntryExitLog
        new_log = EntryExitLog(
            plate_number=plate_number,
            zone_id=zone_id,
            source=f"Camera-{camera_id}",
            gate_type="monitoring",
            status="detected"
        )
        db.add(new_log)
        db.commit()
    except Exception as e:
        if db: db.rollback()

def process_frame(camera_id: int, zone_id: Optional[int], frame, refresh_slots: bool = False, db=None) -> Dict[str, Any]:
    if frame is None: return {"error": "No frame"}

    # LOGGING HEADER
    cam_tag = f"[CAM-{camera_id}]"
    print(f"\n{cam_tag} {'='*40}", flush=True)
    
    try:
        # Use cached slots if available to prevent jumpy counts, unless refresh is forced
        if refresh_slots or camera_id not in _camera_slot_cache:
            print(f"{cam_tag} Running AUTO-SLOT-DETECTION...", flush=True)
            VisionService.DETECTED_SLOTS_BY_VIEW = {} # Reset internal VisionService cache
            slot_results = VisionService.analyze_parking_frame(frame, refresh_slots=True)
            _camera_slot_cache[camera_id] = slot_results
        else:
            # Use cached geometry but re-check occupancy and OCR
            current_slots = _camera_slot_cache[camera_id]
            slot_results = []
            for slot in current_slots:
                slot_crop = VisionService.extract_slot_crop(frame, slot)
                occupied, score = VisionService.is_slot_occupied(slot_crop)
                plate_text, plate_conf = None, 0.0
                if occupied:
                    # Attempt OCR
                    plate_text, plate_conf = VisionService.recognize_plate_from_crop(slot_crop)
                
                slot_results.append({
                    **slot,
                    "occupied": occupied,
                    "occupancy_score": round(score, 4),
                    "plate_number": plate_text,
                    "plate_confidence": round(float(plate_conf), 4),
                })

        occupied_count = 0
        plate_numbers = []

        for item in slot_results:
            sid = item.get("slot_id")
            occ = item.get("occupied")
            plate = item.get("plate_number")
            conf = item.get("plate_confidence", 0.0)

            if occ:
                occupied_count += 1
                status = "OCCUPIED"
                if plate:
                    plate_numbers.append(plate)
                    if db and should_log_plate(camera_id, plate):
                        log_plate_detection(db, plate, zone_id, camera_id)
                        print(f"{cam_tag} ** PLATE DETECTED: {plate} (Conf: {conf}) **", flush=True)
                else:
                    plate = "NO_PLATE_READ"
            else:
                status = "FREE"
                plate = "N/A"

            print(f"{cam_tag} Slot {sid}: {status.ljust(8)} | Plate: {str(plate).ljust(12)} | OCR Conf: {conf}", flush=True)

        print(f"{cam_tag} SUMMARY: {occupied_count}/{len(slot_results)} slots occupied.", flush=True)
        print(f"{cam_tag} {'='*40}\n", flush=True)

        # Update global results for API
        latest_results[camera_id] = {
            "camera_id": camera_id,
            "occupied_count": occupied_count,
            "slots": slot_results,
            "timestamp": time.time()
        }

        # Update annotated stream
        annotated = VisionService.draw_results(frame, slot_results)
        encoded = encode_frame(annotated)
        if encoded: latest_frames[camera_id] = encoded

        return latest_results[camera_id]

    except Exception as e:
        print(f"{cam_tag} !!! AI ERROR: {e} !!!", flush=True)
        return {"error": str(e)}
