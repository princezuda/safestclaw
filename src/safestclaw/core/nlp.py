"""
SafestClaw NLP - Named Entity Recognition with spaCy.

No LLM required - uses trained statistical models.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    import spacy
    HAS_SPACY = True
except ImportError:
    HAS_SPACY = False

try:
    from langdetect import detect_langs
    HAS_LANGDETECT = True
except ImportError:
    HAS_LANGDETECT = False


@dataclass
class Entity:
    """A named entity."""
    text: str
    label: str
    start: int
    end: int

    @property
    def label_name(self) -> str:
        labels = {
            "PERSON": "Person", "ORG": "Organization", "GPE": "Location",
            "LOC": "Location", "DATE": "Date", "TIME": "Time",
            "MONEY": "Money", "PERCENT": "Percentage", "PRODUCT": "Product",
            "EVENT": "Event", "NORP": "Group", "FAC": "Facility",
        }
        return labels.get(self.label, self.label)


@dataclass
class NLPResult:
    """NLP analysis result."""
    text: str
    entities: list[Entity]
    language: str | None = None
    noun_phrases: list[str] = None

    def __post_init__(self):
        if self.noun_phrases is None:
            self.noun_phrases = []

    @property
    def people(self) -> list[str]:
        return [e.text for e in self.entities if e.label == "PERSON"]

    @property
    def organizations(self) -> list[str]:
        return [e.text for e in self.entities if e.label == "ORG"]

    @property
    def locations(self) -> list[str]:
        return [e.text for e in self.entities if e.label in ("GPE", "LOC")]

    @property
    def dates(self) -> list[str]:
        return [e.text for e in self.entities if e.label == "DATE"]


class NLPProcessor:
    """NLP processor using spaCy for NER."""

    def __init__(self, model: str = "en_core_web_sm"):
        self._nlp = None
        self._model = model
        if HAS_SPACY:
            self._load_model()

    def _load_model(self) -> bool:
        try:
            self._nlp = spacy.load(self._model)
            return True
        except OSError:
            logger.warning(f"spaCy model not found. Run: python -m spacy download {self._model}")
            return False

    @property
    def is_available(self) -> bool:
        return HAS_SPACY and self._nlp is not None

    def process(self, text: str) -> NLPResult:
        """Extract entities from text."""
        if not self.is_available:
            return NLPResult(text=text, entities=[])

        doc = self._nlp(text)
        entities = [
            Entity(text=ent.text, label=ent.label_, start=ent.start_char, end=ent.end_char)
            for ent in doc.ents
        ]
        noun_phrases = [chunk.text for chunk in doc.noun_chunks]

        language = None
        if HAS_LANGDETECT and text.strip():
            try:
                langs = detect_langs(text)
                language = langs[0].lang if langs else None
            except Exception:
                pass

        return NLPResult(text=text, entities=entities, language=language, noun_phrases=noun_phrases)

    def extract_entities(self, text: str) -> list[Entity]:
        return self.process(text).entities

    def get_entity_summary(self, text: str) -> dict[str, list[str]]:
        """Group entities by type."""
        result = self.process(text)
        summary: dict[str, list[str]] = {}
        for e in result.entities:
            if e.label not in summary:
                summary[e.label] = []
            if e.text not in summary[e.label]:
                summary[e.label].append(e.text)
        return summary
