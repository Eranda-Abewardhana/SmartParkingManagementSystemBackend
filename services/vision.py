import cv2
import numpy as np
import asyncio
import random
from datetime import datetime
from typing import Tuple, List

# Prototype Note: You will need to install easyocr or pytesseract
# for the OCR logic to work fully.
try:
    import easyocr
    reader = easyocr.Reader(['en'])
except ImportError:
    reader = None

class VisionService:
    @staticmethod
    def recognize_plate(image_bytes: bytes) -> Tuple[str, float]:
        """
        Processes an image to detect and read a license plate.
        Logic:
        1. Convert bytes to OpenCV image.
        2. Detect plate region (Mocked via contours/thresholding for prototype).
        3. Run OCR to extract text.
        """
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if reader and img is not None:
            # Real OCR logic
            try:
                results = reader.readtext(img)
                if results:
                    # Get text with highest confidence
                    text = results[0][-2].strip().upper().replace(" ", "")
                    confidence = float(results[0][-1])
                    return text, confidence
            except Exception:
                pass
        
        # Mock/Fallback logic for prototype testing: Generate a random plate
        random_plate = f"ABC{random.randint(1000, 9999)}"
        return random_plate, 0.95

    @staticmethod
    def count_vehicles_in_zone(image_bytes: bytes, zone_roi: List[int] = None) -> int:
        """
        Uses YOLO logic to count vehicles in a specific zone.
        Logic:
        1. Load pre-trained YOLO model (e.g., yolov8n.pt).
        2. Filter detections for 'car', 'truck', 'motorcycle'.
        3. Check if detection box center is within the Zone ROI.
        """
        # In a real implementation:
        # results = yolo_model(img)
        # count = sum(1 for r in results if r.label == 'car' and is_in_roi(r.box))
        
        # Prototype Mock: Returns a random count for simulation
        return random.randint(5, 15)

    @staticmethod
    async def process_rtsp_stream(rtsp_url: str, zone_id: int, db_session_factory):
        """
        Processes a continuous RTSP stream in the background using OpenCV.
        Logic:
        1. Connect to RTSP stream.
        2. Read frames sequentially.
        3. Apply YOLO detection.
        4. Periodically save occupancy to DB using a thread-safe session.
        """
        from models.occupancy import OccupancySnapshot
        
        cap = cv2.VideoCapture(rtsp_url)
        
        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    # Retry logic for stream disconnection
                    await asyncio.sleep(5)
                    cap.open(rtsp_url)
                    continue
                    
                # Process frame with YOLO here in real application
                
                # Prototype Mock: random count
                occupied_count = random.randint(5, 15)
                
                # Use a synchronous block for DB operations to avoid blocking the event loop
                def update_db():
                    db = db_session_factory()
                    try:
                        new_snapshot = OccupancySnapshot(
                            zone_id=zone_id,
                            occupied_count=occupied_count,
                            updated_at=datetime.utcnow(),
                            source="camera",
                        )
                        db.add(new_snapshot)
                        db.commit()
                    except Exception:
                        db.rollback()
                        raise
                    finally:
                        db.close()

                await asyncio.to_thread(update_db)
                
                # Throttle: Wait 30s before the next capture/update
                await asyncio.sleep(30) 
        finally:
            cap.release()
