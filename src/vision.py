# vision.py
"""
VisionManager - robust, production-minded version.

Responsibilities:
- OCR (pytesseract) with graceful fallback and clear error messages when system tesseract not installed.
- Image captioning & object detection placeholders (clean, documented).
- Defensive coding: does not crash main process; logs helpful instructions when system deps are missing.

Notes / Senior-dev guidance:
- pytesseract is a Python wrapper around the tesseract binary. The binary must be installed on the host OS.
  - Ubuntu/Debian: sudo apt-get install tesseract-ocr
  - macOS (Homebrew): brew install tesseract
  - Windows: install Tesseract from https://github.com/tesseract-ocr/tesseract/releases
- For real image captioning / object detection replace placeholders with a lightweight model (e.g., torchvision, Detectron2,
  or a small Hugging Face model). Avoid loading heavy models at import time; load lazily at first use.
"""

import logging
import os
from typing import List, Dict, Optional

logger = logging.getLogger("Radhe_Vision")
logger.setLevel(logging.INFO)

# Try to import optional dependencies; fail gracefully if missing.
try:
    from PIL import Image
except Exception:
    Image = None
    logger.warning("PIL (Pillow) is not available. Install with `pip install pillow` for image support.")

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except Exception:
    pytesseract = None
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract not available. Install with `pip install pytesseract` and the Tesseract binary.")

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except Exception:
    cv2 = None
    np = None
    OPENCV_AVAILABLE = False
    logger.warning("OpenCV (cv2) not available. Install with `pip install opencv-python` for advanced CV tasks.")


class VisionManager:
    def __init__(self, tesseract_cmd: Optional[str] = None):
        """
        tesseract_cmd: Optional override for pytesseract.pytesseract.tesseract_cmd
        Example on Windows: r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        """
        if tesseract_cmd and pytesseract:
            try:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            except Exception as e:
                logger.warning("Failed to set pytesseract command: %s", e)

    # -------------------------
    # OCR
    # -------------------------
    def ocr_from_image(self, image_path: str) -> str:
        """
        Extract text from an image using pytesseract.
        Returns empty string on failure (never raises).
        """

        if not os.path.exists(image_path):
            logger.error("OCR failed: image not found: %s", image_path)
            return ""

        if not Image:
            logger.error("OCR failed: Pillow not installed.")
            return ""

        if not TESSERACT_AVAILABLE:
            logger.error(
                "OCR not available: pytesseract or Tesseract binary missing. "
                "Install pytesseract (`pip install pytesseract`) and the Tesseract binary "
                "(Ubuntu: `sudo apt-get install tesseract-ocr`, macOS: `brew install tesseract`)."
            )
            return ""

        try:
            with Image.open(image_path) as img:
                # Optionally convert to grayscale to improve OCR
                try:
                    img = img.convert("L")
                except Exception:
                    pass

                text = pytesseract.image_to_string(img)

                if text is None:
                    return ""

                return text.strip()

        except Exception as e:
            logger.exception("OCR extraction failed for %s: %s", image_path, e)
            return ""


# -------------------------
# Image captioning (placeholder)
# -------------------------

def image_captioning(self, image_path: str) -> str:
    """
    Generate a human-readable caption for an image.
    """

    if not os.path.exists(image_path):
        return "Image file not found."

    if not Image:
        return "Image captioning unavailable: Pillow not installed."

    try:
        with Image.open(image_path) as img:
            w, h = img.size
            return f"An image of size {w} by {h} pixels. (Captioning model not installed.)"

    except Exception as e:
        logger.exception("image_captioning failed: %s", e)
        return "Could not create a caption for the image."

    # -------------------------
    # Object detection (placeholder)
    # -------------------------
    def object_detection(self, image_path: str) -> List[Dict]:
        """
        Detect objects in an image.
        Placeholder returns a dummy object list. Replace with model-based detection (YOLO, SSD, Faster-RCNN).
        The return format is: [{ 'label': str, 'confidence': float, 'bbox': [x, y, w, h] }, ...]
        """
        if not OPENCV_AVAILABLE:
            logger.warning("Object detection not available: OpenCV not installed.")
            # Return a plausible placeholder
            return [{"label": "unknown", "score": 0.0, "bbox": [0, 0, 0, 0]}]

        try:
            img = cv2.imread(image_path)
            if img is None:
                logger.error("Object detection: failed to load image %s", image_path)
                return []
            h, w = img.shape[:2]
            # Placeholder: we return a "scene" object covering entire image with low confidence
            return [{"label": "scene", "score": 0.3, "bbox": [0, 0, w, h]}]
        except Exception as e:
            logger.exception("object_detection failed: %s", e)
            return []

# global instance for convenience
vision_manager = VisionManager()
