"""
SafestClaw Vision - Object Detection (YOLO) and OCR.

ML without LLMs - runs locally.
"""

import io
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# YOLO
try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False

# OCR
try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

# Image handling
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


@dataclass
class Detection:
    """A detected object."""
    label: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def center(self) -> tuple[int, int]:
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)


@dataclass
class OCRResult:
    """OCR extraction result."""
    text: str
    confidence: float
    language: str | None = None


@dataclass
class VisionResult:
    """Combined vision analysis result."""
    detections: list[Detection]
    ocr_text: str | None = None
    labels: list[str] = None

    def __post_init__(self):
        if self.labels is None:
            self.labels = list(set(d.label for d in self.detections))

    def get_by_label(self, label: str) -> list[Detection]:
        return [d for d in self.detections if d.label.lower() == label.lower()]

    def count(self, label: str) -> int:
        return len(self.get_by_label(label))


class ObjectDetector:
    """YOLO-based object detection."""

    def __init__(self, model: str = "yolov8n.pt"):
        """
        Initialize detector.

        Args:
            model: YOLO model - yolov8n (nano), yolov8s (small), yolov8m (medium)
        """
        self._model = None
        self._model_name = model
        if HAS_YOLO:
            self._load_model()

    def _load_model(self) -> bool:
        try:
            self._model = YOLO(self._model_name)
            logger.info(f"Loaded YOLO model: {self._model_name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load YOLO: {e}")
            return False

    @property
    def is_available(self) -> bool:
        return HAS_YOLO and self._model is not None

    def detect(
        self,
        image: str | Path | bytes,
        confidence: float = 0.5,
    ) -> list[Detection]:
        """
        Detect objects in image.

        Args:
            image: Path to image or image bytes
            confidence: Minimum confidence threshold
        """
        if not self.is_available:
            return []

        try:
            results = self._model(image, conf=confidence, verbose=False)
            detections = []

            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue

                for i, box in enumerate(boxes):
                    cls_id = int(box.cls[0])
                    label = result.names[cls_id]
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])

                    detections.append(Detection(
                        label=label,
                        confidence=conf,
                        x1=x1, y1=y1, x2=x2, y2=y2,
                    ))

            return detections
        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return []

    def detect_and_count(self, image: str | Path | bytes) -> dict[str, int]:
        """Detect and count objects by type."""
        detections = self.detect(image)
        counts: dict[str, int] = {}
        for d in detections:
            counts[d.label] = counts.get(d.label, 0) + 1
        return counts

    def describe(self, image: str | Path | bytes) -> str:
        """Get a text description of detected objects."""
        counts = self.detect_and_count(image)
        if not counts:
            return "No objects detected."

        parts = []
        for label, count in sorted(counts.items(), key=lambda x: -x[1]):
            if count == 1:
                parts.append(f"1 {label}")
            else:
                parts.append(f"{count} {label}s")

        return "Detected: " + ", ".join(parts)


class OCRProcessor:
    """OCR using Tesseract."""

    def __init__(self, language: str = "eng"):
        """
        Initialize OCR.

        Args:
            language: Tesseract language code (eng, fra, deu, spa, etc.)
        """
        self._language = language

    @property
    def is_available(self) -> bool:
        return HAS_TESSERACT and HAS_PIL

    def extract_text(
        self,
        image: str | Path | bytes,
        language: str | None = None,
    ) -> OCRResult:
        """
        Extract text from image.

        Args:
            image: Path to image or image bytes
            language: Override default language
        """
        if not self.is_available:
            return OCRResult(text="", confidence=0.0)

        lang = language or self._language

        try:
            # Load image
            if isinstance(image, bytes):
                img = Image.open(io.BytesIO(image))
            else:
                img = Image.open(image)

            # Extract text
            text = pytesseract.image_to_string(img, lang=lang)

            # Get confidence
            data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
            confidences = [int(c) for c in data['conf'] if int(c) > 0]
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

            return OCRResult(
                text=text.strip(),
                confidence=avg_conf / 100.0,
                language=lang,
            )
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return OCRResult(text="", confidence=0.0)

    def extract_lines(self, image: str | Path | bytes) -> list[str]:
        """Extract text as list of lines."""
        result = self.extract_text(image)
        return [line.strip() for line in result.text.split('\n') if line.strip()]


class VisionProcessor:
    """Combined vision processor (YOLO + OCR)."""

    def __init__(self, yolo_model: str = "yolov8n.pt", ocr_language: str = "eng"):
        self.detector = ObjectDetector(yolo_model)
        self.ocr = OCRProcessor(ocr_language)

    def analyze(
        self,
        image: str | Path | bytes,
        detect_objects: bool = True,
        extract_text: bool = True,
    ) -> VisionResult:
        """
        Full image analysis.

        Args:
            image: Path to image or bytes
            detect_objects: Run object detection
            extract_text: Run OCR
        """
        detections = []
        ocr_text = None

        if detect_objects and self.detector.is_available:
            detections = self.detector.detect(image)

        if extract_text and self.ocr.is_available:
            ocr_result = self.ocr.extract_text(image)
            ocr_text = ocr_result.text if ocr_result.text else None

        return VisionResult(
            detections=detections,
            ocr_text=ocr_text,
        )

    def describe(self, image: str | Path | bytes) -> str:
        """Get full description of image."""
        result = self.analyze(image)
        parts = []

        if result.detections:
            parts.append(self.detector.describe(image))

        if result.ocr_text:
            preview = result.ocr_text[:200]
            if len(result.ocr_text) > 200:
                preview += "..."
            parts.append(f"Text found: {preview}")

        return "\n".join(parts) if parts else "No content detected."
