import threading
import os
import cv2
import numpy as np
import re
from typing import List, Dict, Any, Optional
from collections import Counter, defaultdict

from huggingface_hub import ***REMOVED***_download, login
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
from ultralytics import YOLO
import torch
from dotenv import load_dotenv

load_dotenv()

latest_frames: Dict[int, bytes] = {}


class VisionService:
    """
    Improved ALPR service:
    - tighter plate crops
    - stricter validation
    - multiple OCR variants
    - temporal voting
    - keeps all valid detections
    """

    _plate_detector = None
    _ocr_processor = None
    _ocr_model = None
    _ocr_available = True
    _device = "cuda" if torch.cuda.is_available() else "cpu"
    _model_lock = threading.Lock()

    HF_TOKEN = os.getenv("HF_TOKEN", "***REMOVED***")

    # Removed AZIIIIIIIIZ/License-plate-detection as it has a corrupted checkpoint
    DETECTOR_SOURCES = [
        {"repo": "yasirfaizahmed/license-plate-object-detection", "file": "best.pt"},
        {"repo": "Koushim/yolov8-license-plate-detection", "file": "model.pt"},
    ]

    OCR_MODEL_REPO = "microsoft/trocr-base-printed"

    DETECTOR_CONFIDENCE = 0.40
    DETECTOR_IMGSZ = 1280
    MIN_PLATE_W = 50
    MIN_PLATE_H = 18
    MAX_HISTORY = 10

    _plate_voter = defaultdict(list)

    @classmethod
    def load_models(cls):
        if cls._plate_detector is not None and cls._ocr_model is not None:
            return

        with cls._model_lock:
            if cls.HF_TOKEN:
                try:
                    login(token=cls.HF_TOKEN)
                except Exception as e:
                    print(f"[VISION] HF Login failed: {e}", flush=True)

            if cls._plate_detector is None:
                for src in cls.DETECTOR_SOURCES:
                    try:
                        print(f"[VISION] Loading detector from {src['repo']}", flush=True)
                        path = ***REMOVED***_download(
                            repo_id=src["repo"],
                            filename=src["file"],
                            token=cls.HF_TOKEN
                        )
                        cls._plate_detector = YOLO(path)
                        cls._plate_detector.to(cls._device)
                        print(f"[VISION] Detector ready: {src['repo']}", flush=True)
                        break
                    except Exception as e:
                        print(f"[VISION] Detector source failed {src['repo']}: {e}", flush=True)

            if cls._ocr_model is None:
                try:
                    cls._ocr_processor = TrOCRProcessor.from_pretrained(
                        cls.OCR_MODEL_REPO,
                        token=cls.HF_TOKEN
                    )
                    cls._ocr_model = VisionEncoderDecoderModel.from_pretrained(
                        cls.OCR_MODEL_REPO,
                        token=cls.HF_TOKEN
                    ).to(cls._device)
                    cls._ocr_model.eval()
                    print(f"[VISION] OCR ready on {cls._device}", flush=True)
                except Exception as e:
                    cls._ocr_available = False
                    print(f"[VISION ERROR] OCR load failed: {e}", flush=True)

    @staticmethod
    def clean_plate_text(text: str) -> str:
        text = text.upper().strip()
        text = re.sub(r"[^A-Z0-9]", "", text)

        # common OCR confusion fixes
        text = text.replace("I", "1") if text[:1].isdigit() else text
        text = text.replace("O", "0") if any(ch.isdigit() for ch in text) else text

        return text

    @staticmethod
    def is_valid_plate(text: str) -> bool:
        if not text:
            return False

        # generic validation for many plate styles
        if len(text) < 5 or len(text) > 10:
            return False

        has_alpha = any(c.isalpha() for c in text)
        has_digit = any(c.isdigit() for c in text)

        if not (has_alpha and has_digit):
            return False

        return True

    @staticmethod
    def preprocess_variants(crop: np.ndarray) -> List[np.ndarray]:
        if crop is None or crop.size == 0:
            return []

        h, w = crop.shape[:2]
        if h < 10 or w < 20:
            return []

        up = cv2.resize(crop, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray_clahe = clahe.apply(gray)

        _, th1 = cv2.threshold(gray_clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        th2 = cv2.adaptiveThreshold(
            gray_clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 8
        )

        sharp_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharp = cv2.filter2D(up, -1, sharp_kernel)

        return [
            up,
            cv2.cvtColor(gray_clahe, cv2.COLOR_GRAY2BGR),
            cv2.cvtColor(th1, cv2.COLOR_GRAY2BGR),
            cv2.cvtColor(th2, cv2.COLOR_GRAY2BGR),
            sharp,
        ]

    @classmethod
    def vote_plate(cls, track_key: str, plate: str) -> str:
        hist = cls._plate_voter[track_key]
        hist.append(plate)
        if len(hist) > cls.MAX_HISTORY:
            hist.pop(0)
        return Counter(hist).most_common(1)[0][0]

    @classmethod
    def run_ocr(cls, crop: np.ndarray, track_key: str) -> Optional[str]:
        cls.load_models()
        if not cls._ocr_available:
            return None

        candidates = []

        for variant in cls.preprocess_variants(crop):
            try:
                img_rgb = cv2.cvtColor(variant, cv2.COLOR_BGR2RGB)
                pixel_values = cls._ocr_processor(images=img_rgb, return_tensors="pt").pixel_values.to(cls._device)

                generated_ids = cls._ocr_model.generate(
                    pixel_values,
                    max_new_tokens=12,
                    num_beams=6,
                    early_stopping=True
                )
                text = cls._ocr_processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
                text = cls.clean_plate_text(text)

                if cls.is_valid_plate(text):
                    candidates.append(text)

            except Exception as e:
                print(f"[OCR] variant failed: {e}", flush=True)

        if not candidates:
            return None

        best = Counter(candidates).most_common(1)[0][0]
        return cls.vote_plate(track_key, best)

    @classmethod
    def detect_plates(cls, frame: np.ndarray, cam_id: int) -> List[Dict[str, Any]]:
        cls.load_models()
        if frame is None or cls._plate_detector is None:
            return []

        results = cls._plate_detector.predict(
            source=frame,
            conf=cls.DETECTOR_CONFIDENCE,
            imgsz=cls.DETECTOR_IMGSZ,
            verbose=False
        )

        detections = []
        if not results or not results[0].boxes:
            return detections

        for i, box in enumerate(results[0].boxes):
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            conf = float(box.conf[0])

            w = x2 - x1
            h = y2 - y1

            if w < cls.MIN_PLATE_W or h < cls.MIN_PLATE_H:
                print(f"[CAM-{cam_id}] Rejected tiny box: {(x1, y1, x2, y2)}", flush=True)
                continue

            aspect = w / max(h, 1)
            if aspect < 1.8 or aspect > 8.5:
                print(f"[CAM-{cam_id}] Rejected bad aspect ratio {aspect:.2f}", flush=True)
                continue

            # tighter padding
            pad_x = int(w * 0.08)
            pad_y = int(h * 0.12)

            x1c = max(0, x1 - pad_x)
            y1c = max(0, y1 - pad_y)
            x2c = min(frame.shape[1], x2 + pad_x)
            y2c = min(frame.shape[0], y2 + pad_y)

            crop = frame[y1c:y2c, x1c:x2c]
            track_key = f"cam{cam_id}_{x1//80}_{y1//80}"

            # Only call OCR if processor/model are ready
            if cls._ocr_model:
                plate_text = cls.run_ocr(crop, track_key)
            else:
                plate_text = None

            if plate_text:
                detections.append({
                    "text": plate_text,
                    "bbox": [x1, y1, x2, y2],
                    "conf": conf,
                })
                print(f"[CAM-{cam_id}] VALID PLATE: {plate_text} | conf={conf:.2f}", flush=True)
            else:
                print(f"[CAM-{cam_id}] OCR rejected box {(x1, y1, x2, y2)}", flush=True)

        return detections

    @classmethod
    def analyze_parking_frame(
        cls,
        frame: np.ndarray,
        refresh_slots: bool = False,
        cam_id: int = 0
    ) -> List[Dict[str, Any]]:
        detections = cls.detect_plates(frame, cam_id)

        output = []
        for idx, det in enumerate(detections, start=1):
            x1, y1, x2, y2 = det["bbox"]
            output.append({
                "slot_id": f"plate_{idx}",
                "occupied": True,
                "plate_number": det["text"],
                "plate_confidence": det["conf"],
                "x": x1,
                "y": y1,
                "w": x2 - x1,
                "h": y2 - y1,
            })

        return output

    @staticmethod
    def draw_results(frame: np.ndarray, plate_results: List[Dict[str, Any]]) -> np.ndarray:
        out = frame.copy()

        for res in plate_results:
            x, y, w, h = res["x"], res["y"], res["w"], res["h"]
            plate = res["plate_number"]
            conf = res.get("plate_confidence", 0.0)

            cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 0), 2)

            label = f"{plate} ({conf:.2f})"
            label_y = max(25, y - 10)
            cv2.rectangle(out, (x, label_y - 22), (x + 250, label_y + 5), (0, 0, 0), -1)
            cv2.putText(
                out,
                label,
                (x + 5, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 0),
                2
            )

        return out


def process_frame(
    camera_id: int,
    zone_id: Optional[int],
    frame: np.ndarray,
    refresh_slots: bool = False,
    db: Any = None
) -> Dict[str, Any]:
    try:
        plate_results = VisionService.analyze_parking_frame(
            frame=frame,
            refresh_slots=refresh_slots,
            cam_id=camera_id
        )

        annotated = VisionService.draw_results(frame, plate_results)

        ok, buffer = cv2.imencode(".jpg", annotated)
        if ok:
            latest_frames[camera_id] = (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )

        plates = [r["plate_number"] for r in plate_results if r["plate_number"]]
        if plates:
            print(f"[CAM-{camera_id}] FINAL DETECTED PLATES: {plates}", flush=True)

        return {
            "camera_id": camera_id,
            "plates": plates,
            "detections": plate_results,
            "count": len(plates),
        }

    except Exception as e:
        print(f"[CAM-{camera_id}] process_frame error: {e}", flush=True)
        return {"error": str(e)}
