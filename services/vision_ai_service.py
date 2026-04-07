import os
import cv2
import re
import time
import threading
import urllib.request
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import Counter

import torch
import easyocr
from dotenv import load_dotenv
from ultralytics import YOLO

load_dotenv()

latest_frames: Dict[int, bytes] = {}


@dataclass
class TrackState:
    track_id: str
    camera_id: int
    bbox: Tuple[int, int, int, int]
    det_conf: float
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    ocr_history: List[str] = field(default_factory=list)
    best_plate: Optional[str] = None
    stable_plate: Optional[str] = None
    stable_hits: int = 0

    is_confirmed: bool = False
    ocr_attempts: int = 0
    last_ocr_ts: float = 0.0
    last_ocr_area: int = 0


class VisionService:
    _plate_detector = None
    _ocr_reader = None
    _device = "cuda" if torch.cuda.is_available() else "cpu"
    _model_lock = threading.Lock()

    _init_failed = False
    _last_init_error: Optional[str] = None
    _last_init_attempt_ts = 0.0
    _retry_after_sec = float(os.getenv("PLATE_MODEL_RETRY_SEC", "15"))

    # Main local path
    PLATE_DETECTOR_MODEL = os.getenv(
        "PLATE_DETECTOR_MODEL",
        "/home/eranda/PycharmProjects/SmartParkingManagementSystem/models/license_plate_detector.pt"
    )

    # Fallback download location
    PLATE_DETECTOR_CACHE = os.getenv(
        "PLATE_DETECTOR_CACHE",
        "/home/eranda/PycharmProjects/SmartParkingManagementSystem/models/downloaded_license_plate_detector.pt"
    )

    # Public fallback weight
    PLATE_DETECTOR_FALLBACK_URL = os.getenv(
        "PLATE_DETECTOR_FALLBACK_URL",
        "https://raw.githubusercontent.com/Muhammad-Zeerak-Khan/Automatic-License-Plate-Recognition-using-YOLOv8/main/license_plate_detector.pt"
    )

    DETECTOR_CONF = float(os.getenv("PLATE_DETECTOR_CONF", "0.30"))
    DETECTOR_IMGSZ = int(os.getenv("PLATE_DETECTOR_IMGSZ", "640"))
    DETECTOR_IOU = float(os.getenv("PLATE_DETECTOR_IOU", "0.45"))
    DETECTOR_MAX_DET = int(os.getenv("PLATE_DETECTOR_MAX_DET", "20"))

    MIN_BOX_W = int(os.getenv("PLATE_MIN_BOX_W", "40"))
    MIN_BOX_H = int(os.getenv("PLATE_MIN_BOX_H", "15"))
    MAX_BOX_W = int(os.getenv("PLATE_MAX_BOX_W", "500"))
    MAX_BOX_H = int(os.getenv("PLATE_MAX_BOX_H", "250"))

    OCR_INTERVAL_SEC = float(os.getenv("PLATE_OCR_INTERVAL_SEC", "0.80"))
    MAX_OCR_ATTEMPTS = int(os.getenv("PLATE_MAX_OCR_ATTEMPTS", "8"))
    STABLE_HITS_REQUIRED = int(os.getenv("PLATE_STABLE_HITS_REQUIRED", "2"))
    OCR_HISTORY_SIZE = int(os.getenv("PLATE_OCR_HISTORY_SIZE", "6"))

    TRACK_TTL_SEC = float(os.getenv("PLATE_TRACK_TTL_SEC", "3.0"))
    IOU_MATCH_THRESHOLD = float(os.getenv("PLATE_IOU_MATCH_THRESHOLD", "0.30"))
    RECENT_PLATE_COOLDOWN_SEC = float(os.getenv("PLATE_RECENT_COOLDOWN_SEC", "2.0"))

    MIN_PLATE_LEN = int(os.getenv("PLATE_MIN_LEN", "4"))
    MAX_PLATE_LEN = int(os.getenv("PLATE_MAX_LEN", "12"))

    _tracks_by_camera: Dict[int, Dict[str, TrackState]] = {}
    _next_track_id_by_camera: Dict[int, int] = {}
    _recent_plate_logs: Dict[str, float] = {}

    @classmethod
    def _ensure_parent_dir(cls, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)

    @classmethod
    def _download_fallback_model(cls, target_path: str) -> str:
        cls._ensure_parent_dir(target_path)
        print(f"[VISION] Downloading fallback detector to: {target_path}", flush=True)
        urllib.request.urlretrieve(cls.PLATE_DETECTOR_FALLBACK_URL, target_path)
        if not os.path.exists(target_path) or os.path.getsize(target_path) == 0:
            raise RuntimeError("Downloaded detector file is missing or empty.")
        return target_path

    @classmethod
    def _resolve_detector_model_path(cls) -> str:
        # 1) explicit local path
        if cls.PLATE_DETECTOR_MODEL and os.path.exists(cls.PLATE_DETECTOR_MODEL):
            return cls.PLATE_DETECTOR_MODEL

        # 2) cached downloaded path
        if cls.PLATE_DETECTOR_CACHE and os.path.exists(cls.PLATE_DETECTOR_CACHE):
            return cls.PLATE_DETECTOR_CACHE

        # 3) fallback download
        return cls._download_fallback_model(cls.PLATE_DETECTOR_CACHE)

    @classmethod
    def load_models(cls):
        if cls._plate_detector is not None and cls._ocr_reader is not None:
            return

        now = time.time()
        if cls._init_failed and (now - cls._last_init_attempt_ts) < cls._retry_after_sec:
            raise RuntimeError(cls._last_init_error or "ALPR initialization is in retry cooldown.")

        with cls._model_lock:
            if cls._plate_detector is not None and cls._ocr_reader is not None:
                return

            cls._last_init_attempt_ts = time.time()

            try:
                print(f"[VISION] Initializing streaming ALPR on {cls._device}...", flush=True)

                detector_model_path = cls._resolve_detector_model_path()
                print(f"[VISION] Using detector model: {detector_model_path}", flush=True)

                cls._plate_detector = YOLO(detector_model_path)
                try:
                    cls._plate_detector.to(cls._device)
                except Exception:
                    pass

                cls._ocr_reader = easyocr.Reader(
                    ["en"],
                    gpu=torch.cuda.is_available(),
                    verbose=False,
                )

                cls._init_failed = False
                cls._last_init_error = None

                print("[VISION] Streaming ALPR engine ready.", flush=True)

            except Exception as e:
                cls._init_failed = True
                cls._last_init_error = str(e)
                cls._plate_detector = None
                cls._ocr_reader = None
                raise

    @staticmethod
    def clean_plate_text(text: str) -> Optional[str]:
        if not text:
            return None

        text = text.upper().strip()
        text = re.sub(r"[^A-Z0-9]", "", text)

        if len(text) < VisionService.MIN_PLATE_LEN or len(text) > VisionService.MAX_PLATE_LEN:
            return None

        # Reject bad OCR garbage
        if len(set(text)) == 1:
            return None

        return text

    @staticmethod
    def _compute_iou(box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]) -> float:
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b

        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)

        inter_w = max(0, inter_x2 - inter_x1)
        inter_h = max(0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h

        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
        union = area_a + area_b - inter_area

        if union <= 0:
            return 0.0
        return inter_area / union

    @classmethod
    def _get_camera_tracks(cls, camera_id: int) -> Dict[str, TrackState]:
        if camera_id not in cls._tracks_by_camera:
            cls._tracks_by_camera[camera_id] = {}
        if camera_id not in cls._next_track_id_by_camera:
            cls._next_track_id_by_camera[camera_id] = 1
        return cls._tracks_by_camera[camera_id]

    @classmethod
    def _new_track_id(cls, camera_id: int) -> str:
        next_id = cls._next_track_id_by_camera.get(camera_id, 1)
        cls._next_track_id_by_camera[camera_id] = next_id + 1
        return f"{camera_id}:{next_id}"

    @classmethod
    def _match_track(cls, camera_id: int, bbox: Tuple[int, int, int, int]) -> Optional[TrackState]:
        tracks = cls._get_camera_tracks(camera_id)
        best_track = None
        best_iou = 0.0

        for track in tracks.values():
            iou = cls._compute_iou(track.bbox, bbox)
            if iou > best_iou:
                best_iou = iou
                best_track = track

        if best_track and best_iou >= cls.IOU_MATCH_THRESHOLD:
            return best_track
        return None

    @classmethod
    def _cleanup_tracks(cls, camera_id: int, now: float):
        tracks = cls._get_camera_tracks(camera_id)
        expired = [tid for tid, state in tracks.items() if now - state.last_seen > cls.TRACK_TTL_SEC]
        for tid in expired:
            del tracks[tid]

    @staticmethod
    def _crop_with_padding(frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)

        pad_x = int(bw * 0.12)
        pad_y = int(bh * 0.25)

        xx1 = max(0, x1 - pad_x)
        yy1 = max(0, y1 - pad_y)
        xx2 = min(w, x2 + pad_x)
        yy2 = min(h, y2 + pad_y)

        crop = frame[yy1:yy2, xx1:xx2]
        if crop is None or crop.size == 0:
            return None
        return crop

    @staticmethod
    def _preprocess_variants(crop: np.ndarray) -> List[np.ndarray]:
        variants: List[np.ndarray] = []

        if crop is None or crop.size == 0:
            return variants

        variants.append(crop)

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        gray = cv2.bilateralFilter(gray, 7, 60, 60)
        up = cv2.resize(gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)

        sharp_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        sharp = cv2.filter2D(up, -1, sharp_kernel)
        variants.append(cv2.cvtColor(sharp, cv2.COLOR_GRAY2BGR))

        thr = cv2.adaptiveThreshold(
            up,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        variants.append(cv2.cvtColor(thr, cv2.COLOR_GRAY2BGR))

        return variants

    @classmethod
    def run_ocr(cls, crop: np.ndarray) -> Optional[str]:
        if crop is None or crop.size == 0 or cls._ocr_reader is None:
            return None

        candidates: List[str] = []

        try:
            for variant in cls._preprocess_variants(crop):
                results = cls._ocr_reader.readtext(
                    variant,
                    detail=1,
                    paragraph=False,
                    allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                    text_threshold=0.60,
                    low_text=0.30,
                    link_threshold=0.20,
                    width_ths=0.70,
                    height_ths=0.70,
                    decoder="greedy",
                )

                for item in results:
                    if len(item) < 2:
                        continue
                    cleaned = cls.clean_plate_text(item[1])
                    if cleaned:
                        candidates.append(cleaned)

            if not candidates:
                return None

            return Counter(candidates).most_common(1)[0][0]

        except Exception:
            return None

    @classmethod
    def _should_run_ocr(cls, state: TrackState, area: int, now: float) -> bool:
        if state.is_confirmed:
            return False
        if state.ocr_attempts >= cls.MAX_OCR_ATTEMPTS:
            return False
        if now - state.last_ocr_ts < cls.OCR_INTERVAL_SEC:
            return False
        if state.last_ocr_area > 0 and area < int(state.last_ocr_area * 0.70):
            return False
        return True

    @classmethod
    def _update_consensus(cls, state: TrackState, text: str):
        state.ocr_history.append(text)
        if len(state.ocr_history) > cls.OCR_HISTORY_SIZE:
            state.ocr_history = state.ocr_history[-cls.OCR_HISTORY_SIZE:]

        counts = Counter(state.ocr_history)
        best_text, hits = counts.most_common(1)[0]

        state.best_plate = best_text
        state.stable_hits = hits

        if hits >= cls.STABLE_HITS_REQUIRED:
            state.stable_plate = best_text
            state.is_confirmed = True

    @classmethod
    def detect_plates(cls, frame: np.ndarray) -> List[Tuple[Tuple[int, int, int, int], float]]:
        if cls._plate_detector is None:
            return []

        results = cls._plate_detector.predict(
            source=frame,
            conf=cls.DETECTOR_CONF,
            iou=cls.DETECTOR_IOU,
            imgsz=cls.DETECTOR_IMGSZ,
            max_det=cls.DETECTOR_MAX_DET,
            verbose=False,
            device=0 if cls._device == "cuda" else "cpu",
        )

        detections: List[Tuple[Tuple[int, int, int, int], float]] = []
        if not results:
            return detections

        first = results[0]
        if first.boxes is None or len(first.boxes) == 0:
            return detections

        boxes = first.boxes.xyxy.cpu().numpy()
        confs = first.boxes.conf.cpu().numpy()

        for box, conf in zip(boxes, confs):
            x1, y1, x2, y2 = map(int, box)
            w = x2 - x1
            h = y2 - y1

            if w < cls.MIN_BOX_W or h < cls.MIN_BOX_H:
                continue
            if w > cls.MAX_BOX_W or h > cls.MAX_BOX_H:
                continue

            detections.append(((x1, y1, x2, y2), float(conf)))

        return detections

    @classmethod
    def analyze_parking_frame(cls, frame: np.ndarray, cam_id: int = 0) -> List[Dict[str, Any]]:
        cls.load_models()
        if frame is None or cls._plate_detector is None:
            return []

        now = time.time()
        outputs: List[Dict[str, Any]] = []

        detections = cls.detect_plates(frame)
        tracks = cls._get_camera_tracks(cam_id)

        for bbox, det_conf in detections:
            matched = cls._match_track(cam_id, bbox)

            if matched is None:
                track_id = cls._new_track_id(cam_id)
                matched = TrackState(
                    track_id=track_id,
                    camera_id=cam_id,
                    bbox=bbox,
                    det_conf=det_conf,
                )
                tracks[track_id] = matched
            else:
                matched.bbox = bbox
                matched.det_conf = det_conf
                matched.last_seen = now

            x1, y1, x2, y2 = bbox
            area = max(1, (x2 - x1) * (y2 - y1))

            if cls._should_run_ocr(matched, area, now):
                crop = cls._crop_with_padding(frame, bbox)
                text = cls.run_ocr(crop)
                matched.ocr_attempts += 1
                matched.last_ocr_ts = now
                matched.last_ocr_area = area

                if text:
                    print(
                        f"[ALPR-RAW] Cam {cam_id} | Track {matched.track_id} | OCR {text}",
                        flush=True
                    )

                    cls._update_consensus(matched, text)

                    if matched.is_confirmed and matched.stable_plate:
                        dedupe_key = f"{cam_id}:{matched.stable_plate}"
                        last_seen = cls._recent_plate_logs.get(dedupe_key, 0.0)
                        if now - last_seen > cls.RECENT_PLATE_COOLDOWN_SEC:
                            print(
                                f"[ALPR-CONFIRMED] Cam {cam_id} | Track {matched.track_id} | Plate {matched.stable_plate}",
                                flush=True
                            )
                            cls._recent_plate_logs[dedupe_key] = now

            outputs.append({
                "track_id": matched.track_id,
                "camera_id": cam_id,
                "occupied": True,
                "plate_number": matched.stable_plate or matched.best_plate,
                "is_confirmed": matched.is_confirmed,
                "stable_hits": matched.stable_hits,
                "ocr_attempts": matched.ocr_attempts,
                "plate_confidence": round(matched.det_conf, 4),
                "x": x1,
                "y": y1,
                "w": x2 - x1,
                "h": y2 - y1,
            })

        cls._cleanup_tracks(cam_id, now)
        return outputs

    @staticmethod
    def draw_results(frame: np.ndarray, results: List[Dict[str, Any]]) -> np.ndarray:
        out = frame.copy()

        for res in results:
            x, y, w, h = res["x"], res["y"], res["w"], res["h"]
            plate = res.get("plate_number")
            confirmed = res.get("is_confirmed", False)
            hits = res.get("stable_hits", 0)
            conf = res.get("plate_confidence", 0.0)

            color = (0, 255, 0) if confirmed else (0, 165, 255)
            cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)

            if confirmed and plate:
                label = f"{plate} | OK | {conf:.2f}"
            elif plate:
                label = f"{plate} | vote={hits} | {conf:.2f}"
            else:
                label = f"READING... | {conf:.2f}"

            label_y = max(25, y - 8)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(out, (x, label_y - th - 6), (x + tw + 10, label_y + 4), color, -1)
            cv2.putText(out, label, (x + 5, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

        return out


def process_frame(camera_id: int, zone_id: Optional[int], frame: np.ndarray, **kwargs) -> Dict[str, Any]:
    try:
        detections = VisionService.analyze_parking_frame(frame=frame, cam_id=camera_id)
        annotated = VisionService.draw_results(frame, detections)

        ok, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if ok:
            latest_frames[camera_id] = (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )

        confirmed_plates = sorted({
            d["plate_number"]
            for d in detections
            if d.get("is_confirmed") and d.get("plate_number")
        })

        all_detected_plates = sorted({
            d["plate_number"]
            for d in detections
            if d.get("plate_number")
        })

        if all_detected_plates:
            print(
                f"[ALPR-FRAME] Cam {camera_id} | All detected plates: {', '.join(all_detected_plates)}",
                flush=True
            )
        else:
            print(
                f"[ALPR-FRAME] Cam {camera_id} | No readable plates detected",
                flush=True
            )

        return {
            "camera_id": camera_id,
            "zone_id": zone_id,
            "plates": confirmed_plates,
            "all_detected_plates": all_detected_plates,
            "detections": detections,
            "all_detection_details": [
                {
                    "track_id": d.get("track_id"),
                    "plate_number": d.get("plate_number"),
                    "is_confirmed": d.get("is_confirmed", False),
                    "stable_hits": d.get("stable_hits", 0),
                    "ocr_attempts": d.get("ocr_attempts", 0),
                    "plate_confidence": d.get("plate_confidence", 0.0),
                    "bbox": {
                        "x": d.get("x"),
                        "y": d.get("y"),
                        "w": d.get("w"),
                        "h": d.get("h"),
                    },
                }
                for d in detections
            ],
            "confirmed_count": len(confirmed_plates),
            "all_detected_count": len(all_detected_plates),
            "raw_detection_count": len(detections),
        }

    except Exception as e:
        print(f"[ALPR-ERROR] Camera {camera_id}: {e}", flush=True)
        return {
            "camera_id": camera_id,
            "zone_id": zone_id,
            "plates": [],
            "all_detected_plates": [],
            "detections": [],
            "all_detection_details": [],
            "confirmed_count": 0,
            "all_detected_count": 0,
            "raw_detection_count": 0,
            "error": str(e),
        }