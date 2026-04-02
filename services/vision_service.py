import os
import threading
import cv2
import numpy as np
import re
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict

from huggingface_hub import ***REMOVED***_download
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
from ultralytics import YOLO
import torch


class VisionService:
    """
    High-Precision ALPR Engine with Multi-Plate Tracking and UK-Pattern Optimization.
    """
    _plate_detector = None
    _ocr_processor = None
    _ocr_model = None
    _ocr_available = True
    _device = "cuda" if torch.cuda.is_available() else "cpu"
    _model_lock = threading.Lock()

    # Authentication & Repos
    HF_TOKEN = "***REMOVED***"
    DETECTOR_REPO = "yasirfaizahmed/license-plate-object-detection"
    OCR_MODEL_REPO = "DunnBC22/trocr-base-printed_license_plates_ocr"

    # Settings
    DETECTOR_CONFIDENCE = 0.25 
    DETECTOR_IMGSZ = 1280
    
    # Temporal Memory (Voter)
    # key: vehicle_id/location -> List of recent OCR reads
    _plate_voter = defaultdict(lambda: list())
    MAX_VOTE_HISTORY = 15

    @classmethod
    def load_models(cls):
        if cls._plate_detector is not None and cls._ocr_model is not None:
            return

        with cls._model_lock:
            if cls._plate_detector is None:
                try:
                    path = ***REMOVED***_download(repo_id=cls.DETECTOR_REPO, filename="best.pt", token=cls.HF_TOKEN)
                    cls._plate_detector = YOLO(path)
                    cls._plate_detector.to(cls._device)
                except Exception as e:
                    print(f"[VISION ERROR] Detector failed: {e}")

            if cls._ocr_model is None:
                try:
                    cls._ocr_processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-printed", token=cls.HF_TOKEN)
                    cls._ocr_model = VisionEncoderDecoderModel.from_pretrained(
                        cls.OCR_MODEL_REPO, use_safetensors=False, token=cls.HF_TOKEN
                    ).to(cls._device)
                    cls._ocr_model.eval()
                except Exception as e:
                    cls._ocr_available = False
                    print(f"[VISION ERROR] OCR failed: {e}")

    @staticmethod
    def advanced_enhance(crop: np.ndarray) -> np.ndarray:
        """Isolates plate characters using Morphological Top-Hat and CLAHE."""
        if crop is None or crop.size == 0: return crop
        
        # 1. High-fidelity upscale
        h, w = crop.shape[:2]
        crop = cv2.resize(crop, (w*3, h*3), interpolation=cv2.INTER_LANCZOS4)
        
        # 2. Convert to Grayscale
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        
        # 3. Apply Morphological Top-Hat to extract black characters from white/yellow BG
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        black_hat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
        
        # 4. Combine Top-Hat with original for extreme contrast
        enhanced = cv2.add(gray, black_hat)
        
        # 5. Local Contrast Normalization
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8,8))
        res = clahe.apply(enhanced)
        
        return cv2.cvtColor(res, cv2.COLOR_GRAY2BGR)

    @classmethod
    def get_stable_plate(cls, track_id: str, new_read: str) -> str:
        """Uses consensus voting over time to eliminate misreads like '0' vs 'O'."""
        history = cls._plate_voter[track_id]
        history.append(new_read)
        if len(history) > cls.MAX_VOTE_HISTORY: history.pop(0)
        
        # Return the most frequent interpretation
        return Counter(history).most_common(1)[0][0]

    @classmethod
    def read_plate_with_consensus(cls, crop: np.ndarray, track_key: str) -> Optional[str]:
        cls.load_models()
        if not cls._ocr_available or crop is None or crop.size == 0: return None
        
        try:
            # Multi-perspective OCR
            enhanced = cls.advanced_enhance(crop)
            img_rgb = cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB)
            pixel_values = cls._ocr_processor(images=img_rgb, return_tensors="pt").pixel_values.to(cls._device)
            
            # Deep Search (10 interpretation beams)
            out_ids = cls._ocr_model.generate(pixel_values, max_new_tokens=15, num_beams=10)
            text = cls._ocr_processor.batch_decode(out_ids, skip_special_tokens=True)[0]
            
            # Clean and validate
            text = re.sub(r"[^A-Z0-9]", "", text.upper())
            if len(text) < 4: return None
            
            return cls.get_stable_plate(track_key, text)
        except:
            return None

    @classmethod
    def analyze_parking_frame(cls, frame: np.ndarray, refresh_slots: bool = False, cam_id: int = 0) -> List[Dict[str, Any]]:
        cls.load_models()
        if frame is None or cls._plate_detector is None: return []

        # 1. Global Detection (Find everything)
        results = cls._plate_detector.predict(source=frame, conf=cls.DETECTOR_CONFIDENCE, imgsz=cls.DETECTOR_IMGSZ, verbose=False)
        
        all_detections = []
        if results and results[0].boxes:
            for i, box in enumerate(results[0].boxes):
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                # Add horizontal 'safety' padding
                bw = x2 - x1
                px = int(bw * 0.15)
                crop = frame[max(0, y1-5):y2+5, max(0, x1-px):x2+px]
                
                # Track using coarse location to maintain consensus
                track_key = f"cam{cam_id}_pos_{x1//100}_{y1//100}"
                text = cls.read_plate_with_consensus(crop, track_key)
                
                if text:
                    all_detections.append({
                        "text": text, "bbox": [x1, y1, x2, y2], "conf": float(box.conf[0])
                    })

        # 2. Mapping to virtual zones/lanes
        h_f, w_f = frame.shape[:2]
        final_results = []
        
        # Simple 3-zone road split
        zones = [
            {"id": "Lane-L", "x": 0, "w": int(w_f*0.33)},
            {"id": "Lane-C", "x": int(w_f*0.34), "w": int(w_f*0.32)},
            {"id": "Lane-R", "x": int(w_f*0.67), "w": int(w_f*0.33)},
        ]

        for zone in zones:
            # Find all plates in this zone
            plates_in_zone = [p for p in all_detections if zone['x'] <= (p['bbox'][0]+p['bbox'][2])/2 <= zone['x']+zone['w']]
            
            if plates_in_zone:
                # If multiple cars in a lane (like your image), pick the clearest/closest one
                plates_in_zone.sort(key=lambda x: x['conf'], reverse=True)
                best = plates_in_zone[0]
                final_results.append({
                    "slot_id": zone['id'], "occupied": True, "plate_number": best['text'], 
                    "x": best['bbox'][0], "y": best['bbox'][1], "w": best['bbox'][2]-best['bbox'][0], "h": best['bbox'][3]-best['bbox'][1]
                })
            else:
                final_results.append({"slot_id": zone['id'], "occupied": False, "plate_number": None, "x": zone['x'], "y": 0, "w": zone['w'], "h": h_f})

        return final_results

    @staticmethod
    def draw_results(frame: np.ndarray, slot_results: List[Dict[str, Any]]) -> np.ndarray:
        out = frame.copy()
        for res in slot_results:
            if res["plate_number"]:
                # High-visibility HUD style box
                tx, ty = res['x'], res['y']
                cv2.rectangle(out, (tx, ty-45), (tx+280, ty), (0, 255, 0), -1)
                cv2.putText(out, res["plate_number"], (tx+10, ty-10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 3)
                cv2.rectangle(out, (tx, ty), (tx+res['w'], ty+res['h']), (0, 255, 0), 3)
        return out
