"""
SafestClaw Text Analyzer - Sentiment, keywords, readability.

All rule-based, no AI required:
- VADER for sentiment analysis
- TF-IDF / RAKE for keyword extraction
- Flesch-Kincaid for readability
"""

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import vaderSentiment, fall back to basic sentiment
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    HAS_VADER = True
except ImportError:
    HAS_VADER = False
    logger.warning("vaderSentiment not installed, using basic sentiment")


@dataclass
class SentimentResult:
    """Result of sentiment analysis."""
    text: str
    positive: float
    negative: float
    neutral: float
    compound: float  # -1 (negative) to +1 (positive)
    label: str  # "positive", "negative", "neutral"


@dataclass
class ReadabilityResult:
    """Result of readability analysis."""
    text_length: int
    word_count: int
    sentence_count: int
    avg_word_length: float
    avg_sentence_length: float
    flesch_reading_ease: float  # 0-100, higher = easier
    flesch_kincaid_grade: float  # US grade level
    reading_level: str  # "easy", "medium", "hard"


@dataclass
class AnalysisResult:
    """Complete text analysis result."""
    sentiment: SentimentResult
    readability: ReadabilityResult
    keywords: list[str]
    word_count: int
    char_count: int


class TextAnalyzer:
    """
    Rule-based text analyzer.

    Features:
    - VADER sentiment analysis (no ML, lexicon-based)
    - Keyword extraction (TF-IDF style)
    - Readability scoring (Flesch-Kincaid)
    - Basic statistics
    """

    # Common English stop words
    STOP_WORDS = {
        'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
        'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
        'to', 'was', 'were', 'will', 'with', 'the', 'this', 'but', 'they',
        'have', 'had', 'what', 'when', 'where', 'who', 'which', 'why', 'how',
        'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
        'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
        'than', 'too', 'very', 'just', 'can', 'could', 'should', 'would',
        'may', 'might', 'must', 'shall', 'will', 'would', 'now', 'then',
        'also', 'been', 'being', 'do', 'does', 'did', 'doing', 'done',
        'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves',
        'you', 'your', 'yours', 'yourself', 'yourselves', 'him', 'his',
        'himself', 'she', 'her', 'hers', 'herself', 'them', 'their',
        'theirs', 'themselves', 'what', 'which', 'who', 'whom',
    }

    def __init__(self):
        if HAS_VADER:
            self._vader = SentimentIntensityAnalyzer()
        else:
            self._vader = None

        # Basic sentiment lexicon fallback
        self._positive_words = {
            'good', 'great', 'excellent', 'amazing', 'wonderful', 'fantastic',
            'awesome', 'love', 'best', 'happy', 'joy', 'beautiful', 'perfect',
            'brilliant', 'superb', 'outstanding', 'positive', 'success',
            'win', 'winning', 'better', 'improve', 'improved', 'growth',
        }
        self._negative_words = {
            'bad', 'terrible', 'awful', 'horrible', 'worst', 'hate', 'poor',
            'disappointing', 'sad', 'angry', 'fail', 'failure', 'negative',
            'wrong', 'problem', 'issue', 'error', 'bug', 'broken', 'crash',
            'loss', 'losing', 'worse', 'decline', 'drop', 'fall', 'down',
        }

    def analyze_sentiment(self, text: str) -> SentimentResult:
        """
        Analyze sentiment using VADER or fallback.

        VADER is rule-based, not ML - it uses a lexicon of words
        with sentiment scores and rules for handling negation,
        capitalization, punctuation, etc.
        """
        if not text:
            return SentimentResult(
                text="",
                positive=0.0,
                negative=0.0,
                neutral=1.0,
                compound=0.0,
                label="neutral",
            )

        if self._vader:
            scores = self._vader.polarity_scores(text)
            compound = scores['compound']
        else:
            # Fallback: simple word counting
            words = set(text.lower().split())
            pos_count = len(words & self._positive_words)
            neg_count = len(words & self._negative_words)
            total = pos_count + neg_count + 1

            scores = {
                'pos': pos_count / total,
                'neg': neg_count / total,
                'neu': 1 - (pos_count + neg_count) / total,
            }
            compound = (pos_count - neg_count) / total

        # Determine label
        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"

        return SentimentResult(
            text=text[:100] + "..." if len(text) > 100 else text,
            positive=scores.get('pos', 0.0),
            negative=scores.get('neg', 0.0),
            neutral=scores.get('neu', 0.0),
            compound=compound,
            label=label,
        )

    def analyze_readability(self, text: str) -> ReadabilityResult:
        """
        Analyze text readability using Flesch-Kincaid formulas.

        Flesch Reading Ease: 206.835 - 1.015(words/sentences) - 84.6(syllables/words)
        Flesch-Kincaid Grade: 0.39(words/sentences) + 11.8(syllables/words) - 15.59
        """
        if not text:
            return ReadabilityResult(
                text_length=0,
                word_count=0,
                sentence_count=0,
                avg_word_length=0.0,
                avg_sentence_length=0.0,
                flesch_reading_ease=0.0,
                flesch_kincaid_grade=0.0,
                reading_level="unknown",
            )

        # Count sentences (split on . ! ?)
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        sentence_count = max(len(sentences), 1)

        # Count words
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        word_count = max(len(words), 1)

        # Count syllables (approximate)
        syllable_count = sum(self._count_syllables(word) for word in words)

        # Calculate metrics
        avg_sentence_length = word_count / sentence_count
        avg_syllables_per_word = syllable_count / word_count
        avg_word_length = sum(len(w) for w in words) / word_count

        # Flesch Reading Ease
        flesch_ease = 206.835 - (1.015 * avg_sentence_length) - (84.6 * avg_syllables_per_word)
        flesch_ease = max(0, min(100, flesch_ease))

        # Flesch-Kincaid Grade Level
        fk_grade = (0.39 * avg_sentence_length) + (11.8 * avg_syllables_per_word) - 15.59
        fk_grade = max(0, fk_grade)

        # Determine reading level
        if flesch_ease >= 70:
            reading_level = "easy"
        elif flesch_ease >= 50:
            reading_level = "medium"
        else:
            reading_level = "hard"

        return ReadabilityResult(
            text_length=len(text),
            word_count=word_count,
            sentence_count=sentence_count,
            avg_word_length=avg_word_length,
            avg_sentence_length=avg_sentence_length,
            flesch_reading_ease=flesch_ease,
            flesch_kincaid_grade=fk_grade,
            reading_level=reading_level,
        )

    def _count_syllables(self, word: str) -> int:
        """Count syllables in a word (approximate)."""
        word = word.lower()
        if len(word) <= 3:
            return 1

        # Count vowel groups
        vowels = "aeiouy"
        count = 0
        prev_vowel = False

        for char in word:
            is_vowel = char in vowels
            if is_vowel and not prev_vowel:
                count += 1
            prev_vowel = is_vowel

        # Adjust for silent e
        if word.endswith('e'):
            count -= 1

        # Adjust for -le ending
        if word.endswith('le') and len(word) > 2 and word[-3] not in vowels:
            count += 1

        return max(1, count)

    def extract_keywords(
        self,
        text: str,
        top_n: int = 10,
        min_word_length: int = 3,
    ) -> list[str]:
        """
        Extract keywords using TF-IDF-like scoring.

        Simple approach: word frequency minus stop words,
        weighted by word length and position.
        """
        if not text:
            return []

        # Tokenize
        words = re.findall(rf'\b[a-zA-Z]{{{min_word_length},}}\b', text.lower())

        # Remove stop words
        words = [w for w in words if w not in self.STOP_WORDS]

        # Count frequencies
        freq = Counter(words)

        # Score: frequency * log(word_length) for importance
        scored = [
            (word, count * math.log(len(word) + 1))
            for word, count in freq.items()
        ]

        # Sort by score
        scored.sort(key=lambda x: x[1], reverse=True)

        return [word for word, _ in scored[:top_n]]

    def analyze(self, text: str) -> AnalysisResult:
        """Perform complete text analysis."""
        sentiment = self.analyze_sentiment(text)
        readability = self.analyze_readability(text)
        keywords = self.extract_keywords(text)

        return AnalysisResult(
            sentiment=sentiment,
            readability=readability,
            keywords=keywords,
            word_count=readability.word_count,
            char_count=len(text),
        )

    def analyze_news_sentiment(self, headlines: list[str]) -> dict:
        """
        Analyze sentiment across multiple headlines.

        Returns overall sentiment distribution.
        """
        if not headlines:
            return {"positive": 0, "negative": 0, "neutral": 0, "overall": "neutral"}

        sentiments = [self.analyze_sentiment(h) for h in headlines]

        positive = sum(1 for s in sentiments if s.label == "positive")
        negative = sum(1 for s in sentiments if s.label == "negative")
        neutral = sum(1 for s in sentiments if s.label == "neutral")

        total = len(sentiments)
        avg_compound = sum(s.compound for s in sentiments) / total

        if avg_compound >= 0.05:
            overall = "positive"
        elif avg_compound <= -0.05:
            overall = "negative"
        else:
            overall = "neutral"

        return {
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
            "positive_pct": positive / total * 100,
            "negative_pct": negative / total * 100,
            "neutral_pct": neutral / total * 100,
            "avg_compound": avg_compound,
            "overall": overall,
            "total": total,
        }
