"""Tests for deterministic multilingual command understanding.

Verifies that commands typed in different languages are correctly
mapped to the same English intent names, with no AI or ML involved.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src"


def _load_module(name: str, filepath: Path):
    """Load a Python module directly from file path."""
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Pre-load i18n so the parser import can find it
_i18n_mod = _load_module(
    "safestclaw.core.i18n",
    SRC / "safestclaw" / "core" / "i18n.py",
)


@pytest.fixture()
def i18n():
    return _i18n_mod


# ---------------------------------------------------------------------------
# i18n module unit tests
# ---------------------------------------------------------------------------

class TestI18nModule:

    def test_supported_languages_includes_en(self, i18n):
        langs = i18n.get_supported_languages()
        assert "en" in langs

    def test_supported_languages_includes_all_packs(self, i18n):
        langs = i18n.get_supported_languages()
        for code in ["es", "fr", "de", "pt", "it", "nl", "ru", "zh", "ja", "ko", "ar", "tr"]:
            assert code in langs, f"Missing language: {code}"

    def test_get_language_name(self, i18n):
        assert "Spanish" in i18n.get_language_name("es")
        assert "French" in i18n.get_language_name("fr")
        assert "German" in i18n.get_language_name("de")

    def test_get_language_name_unknown(self, i18n):
        assert i18n.get_language_name("xx") == "xx"

    def test_get_language_pack_exists(self, i18n):
        pack = i18n.get_language_pack("es")
        assert pack is not None
        assert "reminder" in pack
        assert "keywords" in pack["reminder"]
        assert "phrases" in pack["reminder"]

    def test_get_language_pack_missing(self, i18n):
        assert i18n.get_language_pack("xx") is None

    def test_get_keywords_for_intent(self, i18n):
        kw = i18n.get_keywords_for_intent("fr", "weather")
        assert "météo" in kw

    def test_get_phrases_for_intent(self, i18n):
        phrases = i18n.get_phrases_for_intent("de", "reminder")
        assert any("erinnere" in p for p in phrases)

    def test_all_packs_cover_core_intents(self, i18n):
        """Every language pack should translate at least the core intents."""
        core = {"reminder", "weather", "summarize", "news", "help", "email", "calendar"}
        for lang in i18n.LANGUAGE_PACK:
            pack = i18n.get_language_pack(lang)
            covered = set(pack.keys())
            missing = core - covered
            assert not missing, f"Language '{lang}' missing core intents: {missing}"


# ---------------------------------------------------------------------------
# Parser multilingual integration tests
# ---------------------------------------------------------------------------

# Load parser module (depends on i18n being in sys.modules)
_parser_mod = _load_module(
    "safestclaw.core.parser",
    SRC / "safestclaw" / "core" / "parser.py",
)


@pytest.fixture()
def parser():
    """Return a fresh CommandParser instance."""
    return _parser_mod.CommandParser()


@pytest.fixture()
def parser_es():
    """CommandParser with Spanish loaded."""
    p = _parser_mod.CommandParser()
    p.load_language("es")
    return p


@pytest.fixture()
def parser_fr():
    """CommandParser with French loaded."""
    p = _parser_mod.CommandParser()
    p.load_language("fr")
    return p


@pytest.fixture()
def parser_de():
    """CommandParser with German loaded."""
    p = _parser_mod.CommandParser()
    p.load_language("de")
    return p


@pytest.fixture()
def parser_multi():
    """CommandParser with many languages loaded."""
    p = _parser_mod.CommandParser()
    p.load_languages(["es", "fr", "de", "pt", "it", "ru", "zh", "ja", "ko", "ar", "tr", "nl"])
    return p


class TestParserLanguageLoading:

    def test_english_always_loaded(self, parser):
        assert "en" in parser.get_loaded_languages()

    def test_load_single_language(self, parser):
        parser.load_language("es")
        assert "es" in parser.get_loaded_languages()

    def test_load_multiple_languages(self, parser):
        parser.load_languages(["es", "fr", "de"])
        langs = parser.get_loaded_languages()
        assert "es" in langs
        assert "fr" in langs
        assert "de" in langs

    def test_load_english_noop(self, parser):
        before = len(parser.get_loaded_languages())
        parser.load_language("en")
        assert len(parser.get_loaded_languages()) == before

    def test_load_same_language_twice(self, parser):
        parser.load_language("es")
        parser.load_language("es")
        assert parser.get_loaded_languages().count("es") == 1

    def test_load_unsupported_language(self, parser):
        parser.load_language("xx")
        assert "xx" not in parser.get_loaded_languages()

    def test_keywords_merged(self, parser_es):
        """Spanish keywords should appear in the intent's keyword list."""
        reminder_kw = parser_es.intents["reminder"].keywords
        assert "recordar" in reminder_kw or "recordatorio" in reminder_kw

    def test_original_english_keywords_preserved(self, parser_es):
        """Loading Spanish must not remove English keywords."""
        reminder_kw = parser_es.intents["reminder"].keywords
        assert "remind" in reminder_kw
        assert "reminder" in reminder_kw


# ---------------------------------------------------------------------------
# Spanish command parsing
# ---------------------------------------------------------------------------

class TestSpanishParsing:

    def test_reminder_keyword(self, parser_es):
        result = parser_es.parse("recordatorio llamar a mamá")
        assert result.intent == "reminder"
        assert result.confidence >= 0.8

    def test_weather_keyword(self, parser_es):
        result = parser_es.parse("clima en Madrid")
        assert result.intent == "weather"

    def test_weather_phrase(self, parser_es):
        result = parser_es.parse("cómo está el clima")
        assert result.intent == "weather"

    def test_news_keyword(self, parser_es):
        result = parser_es.parse("noticias tecnología")
        assert result.intent == "news"

    def test_help_keyword(self, parser_es):
        result = parser_es.parse("ayuda")
        assert result.intent == "help"

    def test_email_keyword(self, parser_es):
        result = parser_es.parse("revisar correo")
        assert result.intent == "email"

    def test_calendar_phrase(self, parser_es):
        result = parser_es.parse("qué tengo hoy")
        assert result.intent == "calendar"

    def test_summarize_keyword(self, parser_es):
        result = parser_es.parse("resumir https://example.com")
        assert result.intent == "summarize"

    def test_briefing_phrase(self, parser_es):
        result = parser_es.parse("ponme al día")
        assert result.intent == "briefing"

    def test_smarthome_phrase(self, parser_es):
        result = parser_es.parse("enciende las luces")
        assert result.intent == "smarthome"


# ---------------------------------------------------------------------------
# French command parsing
# ---------------------------------------------------------------------------

class TestFrenchParsing:

    def test_reminder_phrase(self, parser_fr):
        result = parser_fr.parse("rappelle-moi d'appeler maman")
        assert result.intent == "reminder"

    def test_weather_keyword(self, parser_fr):
        result = parser_fr.parse("météo à Paris")
        assert result.intent == "weather"

    def test_weather_phrase(self, parser_fr):
        result = parser_fr.parse("quel temps fait-il")
        assert result.intent == "weather"

    def test_news_keyword(self, parser_fr):
        result = parser_fr.parse("actualités du jour")
        assert result.intent == "news"

    def test_help_keyword(self, parser_fr):
        result = parser_fr.parse("aide")
        assert result.intent == "help"

    def test_email_phrase(self, parser_fr):
        result = parser_fr.parse("vérifier mes emails")
        assert result.intent == "email"

    def test_summarize_keyword(self, parser_fr):
        result = parser_fr.parse("résumer ce texte")
        assert result.intent == "summarize"


# ---------------------------------------------------------------------------
# German command parsing
# ---------------------------------------------------------------------------

class TestGermanParsing:

    def test_reminder_phrase(self, parser_de):
        result = parser_de.parse("erinnere mich an den Termin")
        assert result.intent == "reminder"

    def test_weather_keyword(self, parser_de):
        result = parser_de.parse("wetter in Berlin")
        assert result.intent == "weather"

    def test_weather_phrase(self, parser_de):
        result = parser_de.parse("wie ist das wetter")
        assert result.intent == "weather"

    def test_news_keyword(self, parser_de):
        result = parser_de.parse("nachrichten heute")
        assert result.intent == "news"

    def test_help_keyword(self, parser_de):
        result = parser_de.parse("hilfe")
        assert result.intent == "help"

    def test_calendar_phrase(self, parser_de):
        result = parser_de.parse("was habe ich heute")
        assert result.intent == "calendar"


# ---------------------------------------------------------------------------
# Cross-language equivalence: same command, many languages → same intent
# ---------------------------------------------------------------------------

class TestCrossLanguageEquivalence:
    """The core value proposition: the same command in different languages
    deterministically maps to the same intent."""

    def test_weather_across_languages(self, parser_multi):
        phrases = {
            "en": "weather in London",
            "es": "clima en Londres",
            "fr": "météo à Londres",
            "de": "wetter in London",
            "pt": "clima em Londres",
            "it": "meteo a Londra",
            "nl": "weer in Londen",
            "ru": "погода в Лондоне",
            "zh": "天气 伦敦",
            "ja": "天気 ロンドン",
            "ko": "날씨 런던",
            "ar": "طقس لندن",
            "tr": "hava Londra",
        }
        for lang, phrase in phrases.items():
            result = parser_multi.parse(phrase)
            assert result.intent == "weather", (
                f"[{lang}] '{phrase}' → intent={result.intent}, expected 'weather'"
            )

    def test_help_across_languages(self, parser_multi):
        phrases = {
            "en": "help",
            "es": "ayuda",
            "fr": "aide",
            "de": "hilfe",
            "pt": "ajuda",
            "it": "aiuto",
            "nl": "hulp",
            "ru": "помощь",
            "zh": "帮助",
            "ja": "ヘルプ",
            "ko": "도움말",
            "ar": "مساعدة",
            "tr": "yardım",
        }
        for lang, phrase in phrases.items():
            result = parser_multi.parse(phrase)
            assert result.intent == "help", (
                f"[{lang}] '{phrase}' → intent={result.intent}, expected 'help'"
            )

    def test_news_across_languages(self, parser_multi):
        phrases = {
            "en": "latest news",
            "es": "últimas noticias",
            "fr": "dernières nouvelles",
            "de": "neueste nachrichten",
            "ru": "последние новости",
            "zh": "最新新闻",
            "ja": "最新ニュース",
            "ko": "최신 뉴스",
            "ar": "آخر الأخبار",
            "tr": "son haberler",
        }
        for lang, phrase in phrases.items():
            result = parser_multi.parse(phrase)
            assert result.intent == "news", (
                f"[{lang}] '{phrase}' → intent={result.intent}, expected 'news'"
            )

    def test_reminder_across_languages(self, parser_multi):
        phrases = {
            "en": "remind me to buy milk",
            "es": "recuérdame comprar leche",
            "fr": "rappelle-moi d'acheter du lait",
            "de": "erinnere mich Milch zu kaufen",
            "it": "ricordami di comprare il latte",
            "pt": "lembra-me de comprar leite",
            "ru": "напомни мне купить молоко",
            "zh": "提醒我买牛奶",
            "ja": "牛乳を買うことを思い出させて",
            "ko": "우유 사라고 알려줘",
            "tr": "süt almamı bana hatırlat",
        }
        for lang, phrase in phrases.items():
            result = parser_multi.parse(phrase)
            assert result.intent == "reminder", (
                f"[{lang}] '{phrase}' → intent={result.intent}, expected 'reminder'"
            )


# ---------------------------------------------------------------------------
# English still works after loading languages
# ---------------------------------------------------------------------------

class TestEnglishPreservedAfterMultilingual:

    def test_english_reminder(self, parser_multi):
        result = parser_multi.parse("remind me to call mom tomorrow at 3pm")
        assert result.intent == "reminder"

    def test_english_weather(self, parser_multi):
        result = parser_multi.parse("what's the weather in NYC")
        assert result.intent == "weather"

    def test_english_summarize(self, parser_multi):
        result = parser_multi.parse("summarize https://example.com")
        assert result.intent == "summarize"

    def test_english_help(self, parser_multi):
        result = parser_multi.parse("help")
        assert result.intent == "help"

    def test_english_news(self, parser_multi):
        result = parser_multi.parse("news tech")
        assert result.intent == "news"

    def test_english_email(self, parser_multi):
        result = parser_multi.parse("check my email")
        assert result.intent == "email"

    def test_english_shell(self, parser_multi):
        result = parser_multi.parse("run ls -la")
        assert result.intent == "shell"

    def test_english_phrase_variation(self, parser_multi):
        result = parser_multi.parse("how's the weather")
        assert result.intent == "weather"


# ---------------------------------------------------------------------------
# Unrecognised input still returns no intent
# ---------------------------------------------------------------------------

class TestUnrecognised:

    def test_gibberish(self, parser_multi):
        result = parser_multi.parse("xyzzy plugh")
        assert result.intent is None

    def test_empty(self, parser_multi):
        result = parser_multi.parse("")
        assert result.intent is None
