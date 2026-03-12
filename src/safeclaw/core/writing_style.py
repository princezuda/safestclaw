"""
SafeClaw Writing Style Profiler - Deterministic fuzzy learning.

Learns HOW users write by analyzing their actual blog posts and commands.
No LLM required - uses statistical text analysis to build a writing profile
that can be used to generate system prompts matching the user's voice.

Features:
- Sentence length distribution (short/medium/long preference)
- Vocabulary complexity (simple vs. advanced word usage)
- Punctuation habits (em-dashes, semicolons, exclamation marks)
- Paragraph structure preferences
- Tone profile (formal/casual, positive/negative)
- Favorite phrases and word patterns (n-grams)
- Heading style preferences
- Content structure patterns (listy, narrative, technical)

All deterministic. All local. All private.
"""

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Common English words for vocabulary complexity scoring
BASIC_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
    "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
    "this", "but", "his", "by", "from", "they", "we", "say", "her", "she",
    "or", "an", "will", "my", "one", "all", "would", "there", "their",
    "what", "so", "up", "out", "if", "about", "who", "get", "which", "go",
    "me", "when", "make", "can", "like", "time", "no", "just", "him",
    "know", "take", "people", "into", "year", "your", "good", "some",
    "could", "them", "see", "other", "than", "then", "now", "look",
    "only", "come", "its", "over", "think", "also", "back", "after",
    "use", "two", "how", "our", "work", "first", "well", "way", "even",
    "new", "want", "because", "any", "these", "give", "day", "most", "us",
    "is", "are", "was", "were", "been", "being", "has", "had", "did",
    "very", "really", "thing", "things", "much", "many", "still", "here",
    "should", "need", "does", "got", "going", "right", "too", "big",
    "small", "long", "little", "old", "great", "same", "another", "more",
}


@dataclass
class WritingProfile:
    """A user's writing style profile, built from their actual writing."""

    user_id: str
    samples_analyzed: int = 0

    # Sentence patterns
    avg_sentence_length: float = 0.0
    sentence_length_std: float = 0.0
    short_sentence_ratio: float = 0.0   # <10 words
    medium_sentence_ratio: float = 0.0  # 10-25 words
    long_sentence_ratio: float = 0.0    # >25 words

    # Vocabulary
    vocabulary_richness: float = 0.0  # unique/total ratio
    avg_word_length: float = 0.0
    complex_word_ratio: float = 0.0   # words not in BASIC_WORDS
    favorite_words: list[str] = field(default_factory=list)  # top recurring non-stop words

    # Punctuation habits
    exclamation_rate: float = 0.0
    question_rate: float = 0.0
    semicolon_rate: float = 0.0
    em_dash_rate: float = 0.0
    ellipsis_rate: float = 0.0
    comma_rate: float = 0.0
    parenthetical_rate: float = 0.0

    # Paragraph structure
    avg_paragraph_length: float = 0.0   # in sentences
    avg_paragraphs_per_post: float = 0.0
    uses_short_paragraphs: bool = False  # 1-2 sentence paragraphs

    # Tone
    formality_score: float = 0.5  # 0=casual, 1=formal
    positivity_score: float = 0.5  # 0=negative, 1=positive
    uses_contractions: bool = True
    uses_first_person: bool = True
    uses_second_person: bool = False

    # Content structure
    uses_headings: bool = False
    uses_lists: bool = False
    uses_code_blocks: bool = False
    uses_bold_italic: bool = False
    preferred_structure: str = "narrative"  # narrative, listy, technical, conversational

    # N-gram patterns (favorite phrases)
    common_bigrams: list[str] = field(default_factory=list)
    common_trigrams: list[str] = field(default_factory=list)

    # Opening/closing patterns
    common_openers: list[str] = field(default_factory=list)  # how they start posts
    common_closers: list[str] = field(default_factory=list)  # how they end posts

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for storage."""
        return {
            "user_id": self.user_id,
            "samples_analyzed": self.samples_analyzed,
            "avg_sentence_length": self.avg_sentence_length,
            "sentence_length_std": self.sentence_length_std,
            "short_sentence_ratio": self.short_sentence_ratio,
            "medium_sentence_ratio": self.medium_sentence_ratio,
            "long_sentence_ratio": self.long_sentence_ratio,
            "vocabulary_richness": self.vocabulary_richness,
            "avg_word_length": self.avg_word_length,
            "complex_word_ratio": self.complex_word_ratio,
            "favorite_words": self.favorite_words,
            "exclamation_rate": self.exclamation_rate,
            "question_rate": self.question_rate,
            "semicolon_rate": self.semicolon_rate,
            "em_dash_rate": self.em_dash_rate,
            "ellipsis_rate": self.ellipsis_rate,
            "comma_rate": self.comma_rate,
            "parenthetical_rate": self.parenthetical_rate,
            "avg_paragraph_length": self.avg_paragraph_length,
            "avg_paragraphs_per_post": self.avg_paragraphs_per_post,
            "uses_short_paragraphs": self.uses_short_paragraphs,
            "formality_score": self.formality_score,
            "positivity_score": self.positivity_score,
            "uses_contractions": self.uses_contractions,
            "uses_first_person": self.uses_first_person,
            "uses_second_person": self.uses_second_person,
            "uses_headings": self.uses_headings,
            "uses_lists": self.uses_lists,
            "uses_code_blocks": self.uses_code_blocks,
            "uses_bold_italic": self.uses_bold_italic,
            "preferred_structure": self.preferred_structure,
            "common_bigrams": self.common_bigrams,
            "common_trigrams": self.common_trigrams,
            "common_openers": self.common_openers,
            "common_closers": self.common_closers,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WritingProfile":
        """Deserialize from stored dict."""
        profile = cls(user_id=data.get("user_id", "unknown"))
        for key, value in data.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        return profile

    def to_prompt_instructions(self) -> str:
        """
        Convert writing profile into system prompt instructions.

        This is the key output - a deterministic description of the user's
        writing style that an LLM can follow to match their voice.
        """
        instructions = []

        # Sentence length
        if self.avg_sentence_length > 0:
            if self.short_sentence_ratio > 0.5:
                instructions.append(
                    "Write with short, punchy sentences. "
                    "Keep most sentences under 10 words."
                )
            elif self.long_sentence_ratio > 0.4:
                instructions.append(
                    "Use longer, more complex sentence structures. "
                    "Elaborate and connect ideas within sentences."
                )
            else:
                instructions.append(
                    "Mix sentence lengths naturally — some short, some medium."
                )

        # Vocabulary
        if self.complex_word_ratio > 0.3:
            instructions.append("Use sophisticated vocabulary. Don't shy away from complex words.")
        elif self.complex_word_ratio < 0.15:
            instructions.append("Use simple, everyday language. Avoid jargon and big words.")

        if self.vocabulary_richness > 0.6:
            instructions.append("Vary your word choice — avoid repeating the same words.")

        # Tone
        if self.formality_score > 0.7:
            instructions.append("Maintain a formal, professional tone.")
        elif self.formality_score < 0.3:
            instructions.append(
                "Keep a casual, conversational tone. Write like you're talking to a friend."
            )

        if self.uses_contractions:
            instructions.append("Use contractions (don't, can't, it's).")
        else:
            instructions.append("Avoid contractions. Write out 'do not', 'cannot', 'it is'.")

        if self.uses_first_person:
            instructions.append("Write in first person (I, we, my).")
        if self.uses_second_person:
            instructions.append("Address the reader directly (you, your).")

        # Punctuation
        punct_notes = []
        if self.exclamation_rate > 0.1:
            punct_notes.append("exclamation marks for emphasis")
        if self.em_dash_rate > 0.05:
            punct_notes.append("em-dashes for asides")
        if self.semicolon_rate > 0.03:
            punct_notes.append("semicolons to connect related ideas")
        if self.ellipsis_rate > 0.05:
            punct_notes.append("ellipses for trailing thoughts")
        if self.parenthetical_rate > 0.05:
            punct_notes.append("parenthetical remarks")
        if punct_notes:
            instructions.append(f"Use {', '.join(punct_notes)}.")

        # Structure
        if self.uses_short_paragraphs:
            instructions.append("Keep paragraphs short — 1-3 sentences each.")
        elif self.avg_paragraph_length > 5:
            instructions.append("Write longer, developed paragraphs with multiple supporting points.")

        if self.uses_headings:
            instructions.append("Use headings to organize sections.")
        if self.uses_lists:
            instructions.append("Include bullet points or numbered lists where appropriate.")
        if self.uses_code_blocks:
            instructions.append("Include code blocks when discussing technical topics.")

        # Structure type
        structure_instructions = {
            "narrative": "Write in a flowing narrative style, telling a story.",
            "listy": "Organize content with clear lists and bullet points.",
            "technical": "Write in a technical, documentation-like style with precision.",
            "conversational": "Write conversationally, as if explaining to someone over coffee.",
        }
        if self.preferred_structure in structure_instructions:
            instructions.append(structure_instructions[self.preferred_structure])

        # Favorite phrases
        if self.common_bigrams:
            phrases = ", ".join(f'"{p}"' for p in self.common_bigrams[:5])
            instructions.append(f"Naturally incorporate phrases like: {phrases}.")

        # Openers/closers
        if self.common_openers:
            openers = ", ".join(f'"{o}"' for o in self.common_openers[:3])
            instructions.append(f"Tend to open with patterns like: {openers}.")

        if not instructions:
            return "Write in a clear, natural style."

        return "\n".join(f"- {inst}" for inst in instructions)

    def get_summary(self) -> str:
        """Return a human-readable summary of the writing profile."""
        lines = [
            f"Writing Style Profile ({self.samples_analyzed} samples analyzed)",
            "",
        ]

        # Tone
        tone = "formal" if self.formality_score > 0.6 else "casual" if self.formality_score < 0.4 else "balanced"
        mood = "positive" if self.positivity_score > 0.6 else "negative" if self.positivity_score < 0.4 else "neutral"
        lines.append(f"Tone: {tone}, {mood}")

        # Sentences
        lines.append(f"Avg sentence: {self.avg_sentence_length:.0f} words")

        # Vocabulary
        complexity = "advanced" if self.complex_word_ratio > 0.25 else "simple" if self.complex_word_ratio < 0.15 else "moderate"
        lines.append(f"Vocabulary: {complexity} (richness: {self.vocabulary_richness:.0%})")

        # Structure
        lines.append(f"Structure: {self.preferred_structure}")

        # Favorite words
        if self.favorite_words:
            lines.append(f"Favorite words: {', '.join(self.favorite_words[:8])}")

        if self.common_bigrams:
            lines.append(f"Common phrases: {', '.join(self.common_bigrams[:5])}")

        return "\n".join(lines)


class WritingStyleProfiler:
    """
    Deterministic writing style analyzer.

    Analyzes text samples from a user to build a WritingProfile
    that captures their unique writing patterns. No AI required.

    Usage:
        profiler = WritingStyleProfiler()
        profiler.add_sample("My first blog post text here...")
        profiler.add_sample("Another piece I wrote...")
        profile = profiler.build_profile("user123")
    """

    def __init__(self):
        self._samples: list[str] = []
        self._all_words: list[str] = []
        self._all_sentences: list[str] = []
        self._all_paragraphs: list[list[str]] = []

    def add_sample(self, text: str) -> None:
        """Add a writing sample for analysis."""
        if text and text.strip():
            self._samples.append(text.strip())

    def clear(self) -> None:
        """Clear all samples."""
        self._samples.clear()
        self._all_words.clear()
        self._all_sentences.clear()
        self._all_paragraphs.clear()

    def build_profile(self, user_id: str) -> WritingProfile:
        """
        Build a writing profile from all added samples.

        Analyzes sentence patterns, vocabulary, punctuation, tone,
        structure, and common phrases to create a deterministic
        profile of the user's writing style.
        """
        profile = WritingProfile(user_id=user_id)

        if not self._samples:
            return profile

        profile.samples_analyzed = len(self._samples)

        # Pre-process all samples
        self._preprocess()

        # Analyze each aspect
        self._analyze_sentences(profile)
        self._analyze_vocabulary(profile)
        self._analyze_punctuation(profile)
        self._analyze_paragraphs(profile)
        self._analyze_tone(profile)
        self._analyze_structure(profile)
        self._analyze_ngrams(profile)
        self._analyze_openers_closers(profile)

        return profile

    def _preprocess(self) -> None:
        """Pre-process samples into words, sentences, paragraphs."""
        self._all_words = []
        self._all_sentences = []
        self._all_paragraphs = []

        for text in self._samples:
            # Split into paragraphs
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            para_sentences = []

            for para in paragraphs:
                # Split into sentences
                sentences = re.split(r'(?<=[.!?])\s+', para)
                sentences = [s.strip() for s in sentences if s.strip()]
                self._all_sentences.extend(sentences)
                para_sentences.append(sentences)

                # Split into words
                words = re.findall(r"\b[a-zA-Z']+\b", para.lower())
                self._all_words.extend(words)

            self._all_paragraphs.append(para_sentences)

    def _analyze_sentences(self, profile: WritingProfile) -> None:
        """Analyze sentence length distribution."""
        if not self._all_sentences:
            return

        lengths = []
        for sentence in self._all_sentences:
            word_count = len(re.findall(r'\b\w+\b', sentence))
            if word_count > 0:
                lengths.append(word_count)

        if not lengths:
            return

        profile.avg_sentence_length = sum(lengths) / len(lengths)

        # Standard deviation
        mean = profile.avg_sentence_length
        variance = sum((n - mean) ** 2 for n in lengths) / len(lengths)
        profile.sentence_length_std = math.sqrt(variance)

        # Ratios
        total = len(lengths)
        profile.short_sentence_ratio = sum(1 for n in lengths if n < 10) / total
        profile.medium_sentence_ratio = sum(1 for n in lengths if 10 <= n <= 25) / total
        profile.long_sentence_ratio = sum(1 for n in lengths if n > 25) / total

    def _analyze_vocabulary(self, profile: WritingProfile) -> None:
        """Analyze vocabulary richness and complexity."""
        if not self._all_words:
            return

        total = len(self._all_words)
        unique = len(set(self._all_words))

        profile.vocabulary_richness = unique / total if total > 0 else 0
        profile.avg_word_length = sum(len(w) for w in self._all_words) / total

        # Complex words (not in basic word list)
        complex_count = sum(
            1 for w in self._all_words
            if w.lower() not in BASIC_WORDS and len(w) > 3
        )
        profile.complex_word_ratio = complex_count / total

        # Favorite words (excluding basic words and short words)
        word_counts = Counter(
            w for w in self._all_words
            if w.lower() not in BASIC_WORDS and len(w) > 3
        )
        profile.favorite_words = [word for word, _ in word_counts.most_common(15)]

    def _analyze_punctuation(self, profile: WritingProfile) -> None:
        """Analyze punctuation habits."""
        all_text = " ".join(self._samples)
        sentence_count = max(len(self._all_sentences), 1)

        profile.exclamation_rate = all_text.count("!") / sentence_count
        profile.question_rate = all_text.count("?") / sentence_count
        profile.semicolon_rate = all_text.count(";") / sentence_count
        profile.em_dash_rate = (all_text.count("—") + all_text.count(" - ")) / sentence_count
        profile.ellipsis_rate = (all_text.count("...") + all_text.count("…")) / sentence_count
        profile.comma_rate = all_text.count(",") / sentence_count
        profile.parenthetical_rate = all_text.count("(") / sentence_count

    def _analyze_paragraphs(self, profile: WritingProfile) -> None:
        """Analyze paragraph structure."""
        if not self._all_paragraphs:
            return

        para_lengths = []
        for sample_paras in self._all_paragraphs:
            for para_sentences in sample_paras:
                para_lengths.append(len(para_sentences))

        if para_lengths:
            profile.avg_paragraph_length = sum(para_lengths) / len(para_lengths)
            profile.uses_short_paragraphs = profile.avg_paragraph_length < 3

        # Average paragraphs per post
        para_counts = [len(sp) for sp in self._all_paragraphs]
        if para_counts:
            profile.avg_paragraphs_per_post = sum(para_counts) / len(para_counts)

    def _analyze_tone(self, profile: WritingProfile) -> None:
        """Analyze formality and tone."""
        all_text = " ".join(self._samples).lower()
        total_words = max(len(self._all_words), 1)

        # Contractions indicate informality
        contraction_patterns = [
            r"\b(i'm|you're|we're|they're|he's|she's|it's)\b",
            r"\b(don't|doesn't|didn't|won't|wouldn't|can't|couldn't)\b",
            r"\b(shouldn't|isn't|aren't|wasn't|weren't|haven't|hasn't)\b",
            r"\b(i'll|you'll|we'll|they'll|he'll|she'll)\b",
            r"\b(i've|you've|we've|they've)\b",
            r"\b(i'd|you'd|we'd|they'd|he'd|she'd)\b",
            r"\b(that's|there's|here's|what's|who's|where's)\b",
            r"\b(gonna|wanna|gotta|kinda|sorta)\b",
        ]
        contraction_count = sum(
            len(re.findall(p, all_text)) for p in contraction_patterns
        )
        profile.uses_contractions = contraction_count > 0

        # First person
        first_person = len(re.findall(r'\b(i|me|my|mine|we|us|our|ours)\b', all_text))
        profile.uses_first_person = (first_person / total_words) > 0.02

        # Second person
        second_person = len(re.findall(r'\b(you|your|yours)\b', all_text))
        profile.uses_second_person = (second_person / total_words) > 0.01

        # Formality score
        # Informal markers: contractions, first person, slang, short sentences
        informal_score = 0.0
        if profile.uses_contractions:
            informal_score += 0.2
        if profile.uses_first_person:
            informal_score += 0.1
        if profile.short_sentence_ratio > 0.4:
            informal_score += 0.1
        if profile.exclamation_rate > 0.1:
            informal_score += 0.1

        # Formal markers: long sentences, complex vocabulary, no contractions
        formal_score = 0.0
        if profile.long_sentence_ratio > 0.3:
            formal_score += 0.2
        if profile.complex_word_ratio > 0.25:
            formal_score += 0.2
        if not profile.uses_contractions:
            formal_score += 0.15
        if profile.semicolon_rate > 0.05:
            formal_score += 0.1

        total_markers = informal_score + formal_score
        if total_markers > 0:
            profile.formality_score = formal_score / total_markers
        else:
            profile.formality_score = 0.5

        # Positivity (basic lexicon approach)
        positive_words = {
            "good", "great", "love", "best", "awesome", "amazing", "wonderful",
            "excellent", "fantastic", "brilliant", "happy", "excited", "beautiful",
            "perfect", "incredible", "enjoy", "fun", "glad", "delighted",
        }
        negative_words = {
            "bad", "terrible", "hate", "worst", "awful", "horrible", "poor",
            "disappointing", "sad", "angry", "unfortunately", "problem", "issue",
            "fail", "failure", "wrong", "broken", "annoy", "frustrat",
        }
        pos = sum(1 for w in self._all_words if w in positive_words)
        neg = sum(1 for w in self._all_words if w in negative_words)
        total_sentiment = pos + neg
        if total_sentiment > 0:
            profile.positivity_score = pos / total_sentiment
        else:
            profile.positivity_score = 0.5

    def _analyze_structure(self, profile: WritingProfile) -> None:
        """Analyze content structure preferences."""
        all_text = "\n".join(self._samples)

        # Check for markdown/HTML headings
        heading_patterns = [
            r'^#{1,6}\s',       # Markdown headings
            r'^<h[1-6]>',      # HTML headings
            r'^[A-Z][^.!?]*:$', # Title-case lines ending with colon
        ]
        heading_count = sum(
            len(re.findall(p, all_text, re.MULTILINE))
            for p in heading_patterns
        )
        profile.uses_headings = heading_count > 0

        # Check for lists
        list_patterns = [
            r'^\s*[-*+]\s',     # Bullet lists
            r'^\s*\d+[.)]\s',   # Numbered lists
        ]
        list_count = sum(
            len(re.findall(p, all_text, re.MULTILINE))
            for p in list_patterns
        )
        profile.uses_lists = list_count > 2

        # Check for code blocks
        profile.uses_code_blocks = "```" in all_text or bool(
            re.search(r'^\s{4}\S', all_text, re.MULTILINE)
        )

        # Check for bold/italic
        profile.uses_bold_italic = bool(
            re.search(r'\*\*[^*]+\*\*|__[^_]+__|_[^_]+_|\*[^*]+\*', all_text)
        )

        # Determine preferred structure
        sentence_count = max(len(self._all_sentences), 1)
        list_ratio = list_count / sentence_count
        heading_ratio = heading_count / max(len(self._samples), 1)

        if list_ratio > 0.2:
            profile.preferred_structure = "listy"
        elif profile.uses_code_blocks and heading_ratio > 0.5:
            profile.preferred_structure = "technical"
        elif profile.uses_first_person and profile.formality_score < 0.4:
            profile.preferred_structure = "conversational"
        else:
            profile.preferred_structure = "narrative"

    def _analyze_ngrams(self, profile: WritingProfile) -> None:
        """Extract common bigrams and trigrams (favorite phrases)."""
        if len(self._all_words) < 5:
            return

        # Filter out basic words for more meaningful n-grams
        words = [w for w in self._all_words if len(w) > 2]

        # Bigrams
        bigrams = [
            f"{words[i]} {words[i+1]}"
            for i in range(len(words) - 1)
        ]
        bigram_counts = Counter(bigrams)
        # Only keep bigrams that appear more than once
        profile.common_bigrams = [
            bg for bg, count in bigram_counts.most_common(10)
            if count > 1
        ]

        # Trigrams
        trigrams = [
            f"{words[i]} {words[i+1]} {words[i+2]}"
            for i in range(len(words) - 2)
        ]
        trigram_counts = Counter(trigrams)
        profile.common_trigrams = [
            tg for tg, count in trigram_counts.most_common(10)
            if count > 1
        ]

    def _analyze_openers_closers(self, profile: WritingProfile) -> None:
        """Analyze how users start and end their posts."""
        openers = []
        closers = []

        for text in self._samples:
            sentences = re.split(r'(?<=[.!?])\s+', text.strip())
            sentences = [s.strip() for s in sentences if s.strip()]

            if sentences:
                # First sentence opener pattern (first 5 words)
                first_words = sentences[0].split()[:5]
                if first_words:
                    openers.append(" ".join(first_words))

                # Last sentence closer pattern (last 5 words)
                if len(sentences) > 1:
                    last_words = sentences[-1].split()[-5:]
                    if last_words:
                        closers.append(" ".join(last_words))

        # Find common opening patterns
        if openers:
            # Group by first 2-3 words
            opener_prefixes = Counter()
            for opener in openers:
                words = opener.split()
                if len(words) >= 2:
                    opener_prefixes[" ".join(words[:3])] += 1
            profile.common_openers = [
                op for op, count in opener_prefixes.most_common(5)
                if count > 1
            ]

        if closers:
            closer_suffixes = Counter()
            for closer in closers:
                words = closer.split()
                if len(words) >= 2:
                    closer_suffixes[" ".join(words[-3:])] += 1
            profile.common_closers = [
                cl for cl, count in closer_suffixes.most_common(5)
                if count > 1
            ]


async def load_writing_profile(memory: Any, user_id: str) -> WritingProfile | None:
    """Load a user's writing profile from memory storage."""
    data = await memory.get(f"writing_profile:{user_id}")
    if data:
        return WritingProfile.from_dict(data)
    return None


async def save_writing_profile(memory: Any, profile: WritingProfile) -> None:
    """Save a user's writing profile to memory storage."""
    await memory.set(f"writing_profile:{profile.user_id}", profile.to_dict())


async def update_writing_profile(
    memory: Any,
    user_id: str,
    new_text: str,
) -> WritingProfile:
    """
    Incrementally update a user's writing profile with new content.

    Loads existing profile, adds the new sample, rebuilds, and saves.
    """
    # Load existing samples
    existing_samples = await memory.get(f"writing_samples:{user_id}") or []

    # Add new sample
    existing_samples.append(new_text)

    # Keep last 50 samples to prevent unbounded growth
    if len(existing_samples) > 50:
        existing_samples = existing_samples[-50:]

    # Save samples
    await memory.set(f"writing_samples:{user_id}", existing_samples)

    # Rebuild profile
    profiler = WritingStyleProfiler()
    for sample in existing_samples:
        profiler.add_sample(sample)

    profile = profiler.build_profile(user_id)

    # Save profile
    await save_writing_profile(memory, profile)

    logger.info(
        f"Updated writing profile for {user_id}: "
        f"{profile.samples_analyzed} samples, "
        f"formality={profile.formality_score:.2f}"
    )

    return profile
