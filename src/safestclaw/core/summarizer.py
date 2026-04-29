"""
SafestClaw Summarizer - Extractive text summarization using sumy.

No GenAI required! Uses mathematical algorithms:
- LSA (Latent Semantic Analysis)
- LexRank (graph-based)
- TextRank (graph-based)
- Luhn (statistical)
- Edmundson (cue phrases)
"""

import logging
from enum import StrEnum

from sumy.nlp.stemmers import Stemmer
from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.edmundson import EdmundsonSummarizer
from sumy.summarizers.lex_rank import LexRankSummarizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.summarizers.luhn import LuhnSummarizer
from sumy.summarizers.text_rank import TextRankSummarizer
from sumy.utils import get_stop_words

logger = logging.getLogger(__name__)


class SummaryMethod(StrEnum):
    """Available summarization algorithms."""
    LSA = "lsa"
    LEXRANK = "lexrank"
    TEXTRANK = "textrank"
    LUHN = "luhn"
    EDMUNDSON = "edmundson"


class Summarizer:
    """
    Extractive text summarizer using sumy library.

    All algorithms are non-AI, using mathematical/statistical methods:

    - LSA: Latent Semantic Analysis - finds semantic patterns
    - LexRank: Graph-based, similar to PageRank for sentences
    - TextRank: Graph-based, uses word co-occurrence
    - Luhn: Statistical, uses word frequency
    - Edmundson: Uses cue phrases and sentence position
    """

    def __init__(
        self,
        language: str = "english",
        default_method: SummaryMethod = SummaryMethod.LEXRANK,
    ):
        self.language = language
        self.default_method = default_method
        self.stemmer = Stemmer(language)
        self.stop_words = get_stop_words(language)

        # Initialize summarizers
        self._summarizers = {
            SummaryMethod.LSA: self._create_lsa(),
            SummaryMethod.LEXRANK: self._create_lexrank(),
            SummaryMethod.TEXTRANK: self._create_textrank(),
            SummaryMethod.LUHN: self._create_luhn(),
            SummaryMethod.EDMUNDSON: self._create_edmundson(),
        }

    def _create_lsa(self) -> LsaSummarizer:
        """Create LSA summarizer."""
        summarizer = LsaSummarizer(self.stemmer)
        summarizer.stop_words = self.stop_words
        return summarizer

    def _create_lexrank(self) -> LexRankSummarizer:
        """Create LexRank summarizer."""
        summarizer = LexRankSummarizer(self.stemmer)
        summarizer.stop_words = self.stop_words
        return summarizer

    def _create_textrank(self) -> TextRankSummarizer:
        """Create TextRank summarizer."""
        summarizer = TextRankSummarizer(self.stemmer)
        summarizer.stop_words = self.stop_words
        return summarizer

    def _create_luhn(self) -> LuhnSummarizer:
        """Create Luhn summarizer."""
        summarizer = LuhnSummarizer(self.stemmer)
        summarizer.stop_words = self.stop_words
        return summarizer

    def _create_edmundson(self) -> EdmundsonSummarizer:
        """Create Edmundson summarizer."""
        summarizer = EdmundsonSummarizer(self.stemmer)
        summarizer.stop_words = self.stop_words
        # Bonus/stigma words for Edmundson
        summarizer.bonus_words = ["important", "key", "significant", "essential"]
        summarizer.stigma_words = ["hardly", "impossible"]
        summarizer.null_words = self.stop_words
        return summarizer

    def summarize(
        self,
        text: str,
        sentences: int = 5,
        method: SummaryMethod | None = None,
    ) -> str:
        """
        Summarize text using extractive summarization.

        Args:
            text: The text to summarize
            sentences: Number of sentences in the summary
            method: Algorithm to use (default: LexRank)

        Returns:
            Summary as a string
        """
        method = method or self.default_method

        if not text or not text.strip():
            return ""

        # Parse text
        parser = PlaintextParser.from_string(text, Tokenizer(self.language))

        # Get summarizer
        summarizer = self._summarizers.get(method)
        if not summarizer:
            logger.warning(f"Unknown method {method}, using LexRank")
            summarizer = self._summarizers[SummaryMethod.LEXRANK]

        # Generate summary
        try:
            summary_sentences = summarizer(parser.document, sentences)
            return " ".join(str(sentence) for sentence in summary_sentences)
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            # Fallback: return first N sentences
            return self._fallback_summary(text, sentences)

    def summarize_to_bullets(
        self,
        text: str,
        points: int = 5,
        method: SummaryMethod | None = None,
    ) -> list[str]:
        """
        Summarize text as bullet points.

        Returns:
            List of key sentences as bullet points
        """
        method = method or self.default_method

        if not text or not text.strip():
            return []

        parser = PlaintextParser.from_string(text, Tokenizer(self.language))
        summarizer = self._summarizers.get(method, self._summarizers[SummaryMethod.LEXRANK])

        try:
            summary_sentences = summarizer(parser.document, points)
            return [str(sentence).strip() for sentence in summary_sentences]
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return self._fallback_bullets(text, points)

    def compare_methods(
        self,
        text: str,
        sentences: int = 3,
    ) -> dict[str, str]:
        """
        Compare all summarization methods on the same text.

        Useful for finding the best method for a particular type of content.

        Returns:
            Dict mapping method name to summary
        """
        results = {}

        for method in SummaryMethod:
            try:
                results[method.value] = self.summarize(text, sentences, method)
            except Exception as e:
                results[method.value] = f"Error: {e}"

        return results

    def _fallback_summary(self, text: str, sentences: int) -> str:
        """Simple fallback: return first N sentences."""
        # Split on sentence boundaries
        import re
        sentence_list = re.split(r'(?<=[.!?])\s+', text)
        return " ".join(sentence_list[:sentences])

    def _fallback_bullets(self, text: str, points: int) -> list[str]:
        """Simple fallback: return first N sentences as bullets."""
        import re
        sentence_list = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentence_list[:points] if s.strip()]

    def get_keywords(self, text: str, top_n: int = 10) -> list[str]:
        """
        Extract keywords from text using word frequency.

        Simple non-AI keyword extraction.
        """
        import re
        from collections import Counter

        # Tokenize and clean
        words = re.findall(r'\b[a-z]{3,}\b', text.lower())

        # Remove stop words
        words = [w for w in words if w not in self.stop_words]

        # Count and return top N
        counter = Counter(words)
        return [word for word, _ in counter.most_common(top_n)]
