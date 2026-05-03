"""Core SafestClaw components."""

from safestclaw.core.analyzer import TextAnalyzer
from safestclaw.core.documents import DocumentReader
from safestclaw.core.engine import SafestClaw
from safestclaw.core.memory import Memory
from safestclaw.core.notifications import NotificationManager
from safestclaw.core.parser import CommandParser
from safestclaw.core.scheduler import Scheduler

__all__ = [
    "SafestClaw",
    "CommandParser",
    "Memory",
    "Scheduler",
    "TextAnalyzer",
    "DocumentReader",
    "NotificationManager",
]

# Optional ML imports (heavy dependencies)
try:
    from safestclaw.core.nlp import NLPProcessor
    __all__.append("NLPProcessor")
except ImportError:
    pass  # pip install safestclaw[nlp]

try:
    from safestclaw.core.vision import ObjectDetector, OCRProcessor, VisionProcessor
    __all__.extend(["VisionProcessor", "ObjectDetector", "OCRProcessor"])
except ImportError:
    pass  # pip install safestclaw[vision]
