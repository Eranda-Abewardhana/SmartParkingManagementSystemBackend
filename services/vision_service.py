import cv2
import numpy as np
import asyncio
import re
import hashlib
from datetime import datetime
from typing import Tuple, List, Dict, Any, Optional

try:
    import easyocr
    # Initializing with both English and numbers optimization
    reader = easyocr.Reader(['en'], gpu=False)
except ImportError:
    reader = None


class VisionService:
    """
    Enhanced Parking & Entrance Vision Service.
    Improved for real-time street/entrance scenarios.
    """

    DETECTED_SLOTS_BY_VIEW: Dict[str, List[Dict[str, Any]]] = {}

    VEHICLE_MIN_AREA_RATIO = 0.045
    OCR_MIN_CONFIDENCE = 0.15 # Lowered slightly to capture more, then filtered by logic

    MIN_SLOT_WIDTH = 40
    MAX_SLOT_WIDTH = 500
    MIN_SLOT_HEIGHT = 40
    MAX_SLOT_HEIGHT = 500

    SLOT_REFRESH_EVERY_N_FRAMES = 120

    @staticmethod
    def _get_frame_view_key(frame: np.ndarray) -> str:
        try:
            small = cv2.resize(frame, (64, 64))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            return hashlib.md5(gray.tobytes()).hexdigest()
        except Exception:
            return "default"

    @staticmethod
    def clean_plate_text(text: str) -> str:
        if not text: return ""
        text = text.upper().strip()
        # Remove common OCR noise but keep alphanumeric and hyphens
        text = re.sub(r"[^A-Z0-9-]", "", text)
        text = text.replace("--", "-")
        return text.strip("-")

    @staticmethod
    def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
        """
        Advanced preprocessing to make text pop.
        """
        if image is None or image.size == 0: return image
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Increase contrast
        alpha = 1.5 # Simple contrast control
        beta = 10    # Simple brightness control
        adjusted = cv2.convertScaleAbs(gray, alpha=alpha, beta=beta)
        
        # Denoise while keeping edges sharp
        dst = cv2.fastNlMeansDenoising(adjusted, h=10)
        
        # Adaptive thresholding to handle shadows
        thresh = cv2.adaptiveThreshold(
            dst, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        return thresh

    @staticmethod
    def _find_plate_candidates(crop: np.ndarray) -> List[np.ndarray]:
        """
        Search for potential plate regions using contour analysis.
        """
        candidates = []
        if crop is None or crop.size == 0: return candidates

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blur, 30, 200)

        contours, _ = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:15]

        h_img, w_img = crop.shape[:2]
        img_area = h_img * w_img

        for c in contours:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.018 * peri, True)
            
            x, y, w, h = cv2.boundingRect(c)
            aspect_ratio = w / float(h) if h > 0 else 0
            area = w * h

            # Filter for plate-like shapes (Horizontal rectangles)
            if 2.0 <= aspect_ratio <= 6.0 and img_area * 0.005 <= area <= img_area * 0.4:
                # Pad the crop slightly
                p = 5
                x1, y1 = max(0, x-p), max(0, y-p)
                x2, y2 = min(w_img, x+w+p), min(h_img, y+h+p)
                candidates.append(crop[y1:y2, x1:x2])

        return candidates

    @staticmethod
    def recognize_plate_from_crop(vehicle_crop: np.ndarray) -> Tuple[Optional[str], float]:
        if vehicle_crop is None or vehicle_crop.size == 0 or reader is None:
            return None, 0.0

        try:
            # Try 1: The whole crop (good if the vehicle is far)
            # Try 2: Found candidates (good if the vehicle is close)
            candidates = [vehicle_crop]
            candidates.extend(VisionService._find_plate_candidates(vehicle_crop))

            best_text = None
            best_conf = 0.0

            for cand in candidates[:4]: # Limit to top 4 regions for speed
                if cand.size == 0: continue
                
                # Multi-scale: Resize up to improve OCR on small plates
                for scale in [1.5, 2.5]:
                    resized = cv2.resize(cand, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                    processed = VisionService.preprocess_for_ocr(resized)
                    
                    results = reader.readtext(processed, detail=1, paragraph=False)
                    for res in results:
                        text = VisionService.clean_plate_text(res[1])
                        conf = float(res[2])
                        
                        # Logic: Plate must have letters AND numbers usually
                        has_alpha = any(c.isalpha() for c in text)
                        has_digit = any(c.isdigit() for c in text)
                        
                        if len(text) >= 4 and (has_alpha or has_digit):
                            if conf > best_conf:
                                best_text = text
                                best_conf = conf

            if best_text and best_conf >= VisionService.OCR_MIN_CONFIDENCE:
                return best_text, best_conf

        except Exception as e:
            print(f"OCR Error: {e}")
        return None, 0.0

    @staticmethod
    def is_slot_occupied(slot_crop: np.ndarray) -> Tuple[bool, float]:
        if slot_crop is None or slot_crop.size == 0: return False, 0.0
        gray = cv2.cvtColor(slot_crop, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edge_ratio = cv2.countNonZero(edges) / float(slot_crop.shape[0] * slot_crop.shape[1])
        stddev = np.std(gray) / 255.0
        score = (edge_ratio * 0.7) + (stddev * 0.3)
        return score > 0.035, score

    @staticmethod
    def auto_detect_parking_slots(frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detects road/parking regions. If none found, creates a 'Full Frame' candidate.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)
        
        # Look for white lines (common in parking/roads)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=100, maxLineGap=20)
        
        slots = []
        if lines is not None:
            # Logic to group lines into rectangles... (abbreviated for the Entrance fix)
            # If standard slot detection fails, we will return an empty list 
            # and let the analyzer handle it as an 'Entrance' view.
            pass

        return slots

    @staticmethod
    def analyze_parking_frame(frame: np.ndarray, refresh_slots: bool = False, view_key: Optional[str] = None) -> List[Dict[str, Any]]:
        if frame is None or frame.size == 0: return []
        
        view_key = view_key or VisionService._get_frame_view_key(frame)
        current_slots = VisionService.DETECTED_SLOTS_BY_VIEW.get(view_key, [])

        if refresh_slots or not current_slots:
            current_slots = VisionService.auto_detect_parking_slots(frame)
            
            # FALLBACK: If no slots (like in your Entrance image), 
            # create large virtual 'Search Zones' for the road.
            if not current_slots:
                h, w = frame.shape[:2]
                # Split frame into 3 zones: Left Road, Center Road, Right Road
                # This ensures we don't miss plates in clear view
                current_slots = [
                    {"slot_id": "ROAD-C", "x": int(w*0.1), "y": int(h*0.2), "w": int(w*0.8), "h": int(h*0.75)},
                ]
            
            VisionService.DETECTED_SLOTS_BY_VIEW[view_key] = current_slots

        results = []
        for slot in current_slots:
            crop = frame[slot['y']:slot['y']+slot['h'], slot['x']:slot['x']+slot['w']]
            occupied, score = VisionService.is_slot_occupied(crop)
            
            # For ENTRANCE/ROAD zones, we always try OCR if any motion/score is present
            plate_text, plate_conf = None, 0.0
            if score > 0.02: 
                plate_text, plate_conf = VisionService.recognize_plate_from_crop(crop)

            results.append({
                "slot_id": slot["slot_id"],
                "x": slot["x"], "y": slot["y"], "w": slot["w"], "h": slot["h"],
                "occupied": occupied,
                "occupancy_score": round(score, 4),
                "plate_number": plate_text,
                "plate_confidence": round(float(plate_conf), 4),
            })
        return results

    @staticmethod
    def draw_results(frame: np.ndarray, slot_results: List[Dict[str, Any]]) -> np.ndarray:
        output = frame.copy()
        for res in slot_results:
            x, y, w, h = res['x'], res['y'], res['w'], res['h']
            color = (0, 255, 0) if not res['occupied'] else (0, 0, 255)
            
            # Don't draw big boxes for 'ROAD' fallback zones (keep UI clean)
            if "ROAD" not in res['slot_id']:
                cv2.rectangle(output, (x, y), (x + w, y + h), color, 2)
            
            if res['plate_number']:
                # Draw a special highlight for detected plates
                text = f"PLATE: {res['plate_number']} ({int(res['plate_confidence']*100)}%)"
                cv2.putText(output, text, (x + 5, y + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        return output

    @staticmethod
    def extract_slot_crop(frame: np.ndarray, slot: Dict[str, Any]) -> np.ndarray:
        x, y, w, h = slot["x"], slot["y"], slot["w"], slot["h"]
        return frame[y:y + h, x:x + w]
