import os
import time
import cv2
import numpy as np
import hashlib
import requests
import logging
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Union, Generator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CACHE_DIR = Path("media_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def is_youtube_url(url: str) -> bool:
    lower = (url or "").lower()
    return "youtube.com/watch" in lower or "youtu.be/" in lower

def is_direct_video_file_url(url: str) -> bool:
    lower = (url or "").lower()
    video_extensions = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v")
    if lower.endswith(video_extensions):
        return True
    if "pexels.com/download/video/" in lower:
        return True
    return False

def get_cached_video_path(url: str) -> Path:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".mp4"
    filename = hashlib.md5(url.encode("utf-8")).hexdigest() + suffix
    return CACHE_DIR / filename

def download_video_once(url: str) -> str:
    local_path = get_cached_video_path(url)
    if local_path.exists() and local_path.stat().st_size > 0:
        return str(local_path)

    logger.info(f"Downloading remote video: {url}")
    response = requests.get(url, stream=True, timeout=60, allow_redirects=True)
    response.raise_for_status()

    with open(local_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return str(local_path)

class CameraStreamer:
    """
    Handles pure camera streaming (OpenCV capture and frame generation).
    """
    def __init__(self, url: str):
        self.url = (url or "").strip()
        self.source_label = "unknown"
        if not self.url:
            raise RuntimeError("Camera source URL is empty")
        
        self.capture_url = self._resolve_capture_source()

    def _resolve_capture_source(self) -> Union[int, str]:
        if self.url.isdigit():
            self.source_label = "webcam"
            return int(self.url)

        if os.path.exists(self.url):
            self.source_label = "local_file"
            return self.url

        if self.url.startswith(("http://", "https://")) and is_direct_video_file_url(self.url):
            try:
                return download_video_once(self.url)
            except Exception as e:
                raise RuntimeError(f"Failed to download remote video: {str(e)}")

        self.source_label = "network_stream"
        return self.url

    def get_capture(self) -> cv2.VideoCapture:
        if isinstance(self.capture_url, int):
            return cv2.VideoCapture(self.capture_url)
        return cv2.VideoCapture(self.capture_url, cv2.CAP_FFMPEG)

    def _build_info_frame(self, title: str, message: str) -> bytes:
        blank = 255 * np.ones((480, 640, 3), dtype="uint8")
        cv2.putText(blank, title, (140, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        cv2.putText(blank, message[:60], (30, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        ok, buffer = cv2.imencode(".jpg", blank)
        return (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n") if ok else b""

    def generate_raw_frames(self) -> Generator[bytes, None, None]:
        cap = self.get_capture()
        try:
            while True:
                success, frame = cap.read()
                if not success:
                    if self.source_label in ("local_file", "cached_remote_video"):
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    else:
                        yield self._build_info_frame("Stream Lost", "Reconnecting...")
                        time.sleep(2)
                        cap.release()
                        cap = self.get_capture()
                        continue
                
                ok, buffer = cv2.imencode(".jpg", frame)
                if ok:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
                time.sleep(0.03)
        finally:
            cap.release()
