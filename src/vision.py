# vision.py
"""
VisionManager for Radhe.

Fixes applied vs previous version:
- image_captioning() and object_detection() were accidentally defined OUTSIDE
  the class (wrong indentation). Both are now proper class methods.
- object_detection() was nested INSIDE image_captioning() — fixed.
- Added missing `import os` (was used but not imported in the standalone functions).

Goal-aligned improvements:
- analyze_image() added as a single unified entry point: OCR + caption + objects.
  Radhe can call this one method and get a full description of any image.
- screen_capture() added: takes a screenshot and runs analyze_image() on it.
  This is the foundation for "watch my screen and tell me what's happening."

Install notes:
    pip install pillow pytesseract opencv-python-headless pyautogui
    Ubuntu/Debian: sudo apt-get install tesseract-ocr
    macOS:         brew install tesseract
    Windows:       https://github.com/tesseract-ocr/tesseract/releases
"""

import os
import logging
import tempfile
from typing import List, Dict, Optional

logger = logging.getLogger("Radhe_Vision")
logger.setLevel(logging.INFO)

# ── Optional dependency guards ────────────────────────────────────────

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    Image = None
    PIL_AVAILABLE = False
    logger.warning("Pillow not available. Run: pip install pillow")

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except Exception:
    pytesseract = None
    TESSERACT_AVAILABLE = False
    logger.warning(
        "pytesseract not available. "
        "Run: pip install pytesseract  and  install Tesseract binary."
    )

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except Exception:
    cv2  = None
    np   = None
    OPENCV_AVAILABLE = False
    logger.warning("OpenCV not available. Run: pip install opencv-python-headless")

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except Exception:
    pyautogui = None
    PYAUTOGUI_AVAILABLE = False
    logger.warning("pyautogui not available. Run: pip install pyautogui")


# ==================================================================
# VISION MANAGER
# ==================================================================

class VisionManager:

    def __init__(self, tesseract_cmd: Optional[str] = None):
        """
        tesseract_cmd: optional path override for the Tesseract binary.
        Example on Windows: r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
        """
        if tesseract_cmd and TESSERACT_AVAILABLE:
            try:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            except Exception as e:
                logger.warning("Failed to set Tesseract command: %s", e)

    # ==================================================================
    # OCR
    # ==================================================================

    def ocr_from_image(self, image_path: str) -> str:
        """
        Extract text from an image file using pytesseract.
        Returns empty string on failure — never raises.
        """
        if not os.path.exists(image_path):
            logger.error("OCR: image not found: %s", image_path)
            return ""

        if not PIL_AVAILABLE:
            logger.error("OCR: Pillow not installed.")
            return ""

        if not TESSERACT_AVAILABLE:
            logger.error(
                "OCR: pytesseract or Tesseract binary missing. "
                "Install: pip install pytesseract  and the Tesseract binary."
            )
            return ""

        try:
            with Image.open(image_path) as img:
                try:
                    img = img.convert("L")   # grayscale improves OCR accuracy
                except Exception:
                    pass
                text = pytesseract.image_to_string(img)
                return (text or "").strip()

        except Exception as e:
            logger.exception("ocr_from_image failed for %s: %s", image_path, e)
            return ""

    # ==================================================================
    # IMAGE CAPTIONING
    # (Fix: was outside the class in the previous version)
    # ==================================================================

    def image_captioning(self, image_path: str) -> str:
        """
        Generate a basic description of an image.

        Currently returns dimensions + colour info.
        Replace the body with a real model call (e.g. BLIP, GPT-4 Vision)
        when you're ready to upgrade.
        """
        if not os.path.exists(image_path):
            return "Image file not found."

        if not PIL_AVAILABLE:
            return "Image captioning unavailable: Pillow not installed."

        try:
            with Image.open(image_path) as img:
                w, h   = img.size
                mode   = img.mode
                format_= img.format or "unknown"

                # Basic dominant colour hint via thumbnail
                colour_hint = ""
                try:
                    thumb = img.convert("RGB").resize((50, 50))
                    pixels = list(thumb.getdata())
                    r_avg  = sum(p[0] for p in pixels) // len(pixels)
                    g_avg  = sum(p[1] for p in pixels) // len(pixels)
                    b_avg  = sum(p[2] for p in pixels) // len(pixels)
                    if r_avg > g_avg and r_avg > b_avg:
                        colour_hint = " with warm red tones"
                    elif g_avg > r_avg and g_avg > b_avg:
                        colour_hint = " with green tones"
                    elif b_avg > r_avg and b_avg > g_avg:
                        colour_hint = " with cool blue tones"
                except Exception:
                    pass

                return (
                    f"A {format_} image, {w}×{h} pixels, "
                    f"colour mode {mode}{colour_hint}."
                )

        except Exception as e:
            logger.exception("image_captioning failed: %s", e)
            return "Could not generate a caption for the image."

    # ==================================================================
    # OBJECT DETECTION
    # (Fix: was nested inside image_captioning in the previous version)
    # ==================================================================

    def object_detection(self, image_path: str) -> List[Dict]:
        """
        Detect objects in an image.

        Placeholder returns a single scene-level entry.
        Replace with YOLO / SSD / Faster-RCNN when ready.

        Return format:
        [{ 'label': str, 'confidence': float, 'bbox': [x, y, w, h] }, ...]
        """
        if not os.path.exists(image_path):
            logger.error("object_detection: image not found: %s", image_path)
            return []

        if not OPENCV_AVAILABLE:
            logger.warning("object_detection: OpenCV not installed.")
            return [{"label": "unknown", "confidence": 0.0, "bbox": [0, 0, 0, 0]}]

        try:
            img = cv2.imread(image_path)
            if img is None:
                logger.error("object_detection: cv2 could not read %s", image_path)
                return []

            h, w = img.shape[:2]
            # Placeholder — returns full-frame "scene" object
            return [{"label": "scene", "confidence": 0.3, "bbox": [0, 0, w, h]}]

        except Exception as e:
            logger.exception("object_detection failed: %s", e)
            return []

    # ==================================================================
    # UNIFIED ANALYSER
    # Goal: single call gives Radhe a full understanding of an image
    # ==================================================================

    def analyze_image(self, image_path: str) -> str:
        """
        Run OCR + captioning + object detection on a single image and
        return a single natural-language description.

        This is the method Radhe should call when the user says:
        "What is in this image?" / "Read this screenshot."
        """
        if not os.path.exists(image_path):
            return "I can't find that image file."

        parts: List[str] = []

        caption = self.image_captioning(image_path)
        if caption:
            parts.append(caption)

        text = self.ocr_from_image(image_path)
        if text:
            parts.append(f"Text found in image: {text}")

        objects = self.object_detection(image_path)
        labels  = [o["label"] for o in objects if o.get("label") != "scene"]
        if labels:
            parts.append("Objects detected: " + ", ".join(labels))

        return " ".join(parts) if parts else "I couldn't extract any information from the image."

    # ==================================================================
    # SCREEN CAPTURE  (foundation for "watch my screen" feature)
    # ==================================================================

    def capture_screen_and_analyze(self) -> str:
        """
        Take a screenshot of the current screen and analyse it.
        Returns a natural-language description.

        This is the first step toward Radhe understanding
        what is on your screen in real time.
        """
        if not PYAUTOGUI_AVAILABLE:
            return (
                "Screen capture not available. "
                "Run: pip install pyautogui"
            )

        try:
            screenshot = pyautogui.screenshot()

            with tempfile.NamedTemporaryFile(
                suffix=".png", delete=False
            ) as tmp:
                tmp_path = tmp.name
                screenshot.save(tmp_path)

            result = self.analyze_image(tmp_path)

            try:
                os.remove(tmp_path)
            except Exception:
                pass

            return result

        except Exception as e:
            logger.exception("capture_screen_and_analyze failed: %s", e)
            return "I couldn't capture the screen."
    
    # ==================================================================
    # SCREEN DESCRIPTION
    # ==================================================================
    def describe_screen(self) -> str:
        return self.capture_screen_and_analyze()
    
    def read_text(self) -> str:
        """Take a screenshot and run OCR on it."""
        try:
            import pyautogui
            import tempfile
            import os

            screenshot = pyautogui.screenshot()

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                screenshot.save(tmp.name)
                result = self.ocr_from_image(tmp.name)

            try:
                os.remove(tmp.name)
            except Exception:
                pass

            return result if result else "No text found on screen."

        except ImportError:
            return "pyautogui not installed. Install it using pip install pyautogui"

        except Exception as e:
            logger.exception("read_text failed: %s", e)
            return "Could not read text from screen."

# ── Global instance ───────────────────────────────────────────────────
vision_manager = VisionManager()