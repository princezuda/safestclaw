"""Prompt helpers that accept spelled-out numbers ("one", "two", ...)
in addition to digits. Drop-in replacements for rich.prompt.Prompt and
rich.prompt.IntPrompt so numbered menus work either way.
"""
from __future__ import annotations

from rich.prompt import IntPrompt, Prompt

WORD_TO_DIGIT: dict[str, str] = {
    "zero": "0",
    "one": "1", "first": "1", "1st": "1",
    "two": "2", "second": "2", "2nd": "2",
    "three": "3", "third": "3", "3rd": "3",
    "four": "4", "fourth": "4", "4th": "4",
    "five": "5", "fifth": "5", "5th": "5",
    "six": "6", "sixth": "6", "6th": "6",
    "seven": "7", "seventh": "7", "7th": "7",
    "eight": "8", "eighth": "8", "8th": "8",
    "nine": "9", "ninth": "9", "9th": "9",
    "ten": "10", "tenth": "10", "10th": "10",
    "eleven": "11", "eleventh": "11",
    "twelve": "12", "twelfth": "12",
    "thirteen": "13", "fourteen": "14", "fifteen": "15",
    "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20",
}


def normalize_number_word(value: str) -> str:
    """Map a spelled-out number to its digit form. Pass-through otherwise."""
    if not isinstance(value, str):
        return value
    key = value.strip().lower().rstrip(".")
    return WORD_TO_DIGIT.get(key, value.strip())


class WordPrompt(Prompt):
    """Prompt that accepts "one"/"two"/... as well as digit choices."""

    def process_response(self, value: str):  # type: ignore[override]
        return super().process_response(normalize_number_word(value))


class WordIntPrompt(IntPrompt):
    """IntPrompt that accepts "one"/"two"/... as well as digits."""

    def process_response(self, value: str):  # type: ignore[override]
        return super().process_response(normalize_number_word(value))
