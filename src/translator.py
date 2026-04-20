"""
Translator Module
Language detection and translation using deep-translator (no API key needed)
"""

from typing import Optional

try:
    from langdetect import detect, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

try:
    from deep_translator import GoogleTranslator
    DEEP_TRANSLATOR_AVAILABLE = True
except ImportError:
    DEEP_TRANSLATOR_AVAILABLE = False


# Human-readable language names for display
LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "ar": "Arabic",
    "zh-cn": "Chinese (Simplified)",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "it": "Italian",
    "nl": "Dutch",
    "tr": "Turkish",
    "pl": "Polish",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "ur": "Urdu",
}


def detect_language(text: str) -> str:
    """
    Detect the language of the given text.

    Args:
        text: Input text

    Returns:
        ISO 639-1 language code (e.g. 'en', 'hi', 'fr').
        Returns 'en' if detection fails or library not available.
    """
    if not LANGDETECT_AVAILABLE or not text or len(text.strip()) < 5:
        return "en"
    try:
        return detect(text)
    except LangDetectException:
        return "en"
    except Exception:
        return "en"


def translate_to_english(text: str, src_lang: Optional[str] = None) -> str:
    """
    Translate text to English.

    Args:
        text: Source text
        src_lang: Source language code. If None, auto-detects.

    Returns:
        English translation, or original text if translation fails.
    """
    if not DEEP_TRANSLATOR_AVAILABLE:
        return text

    src_lang = src_lang or detect_language(text)
    if src_lang == "en":
        return text

    try:
        translator = GoogleTranslator(source=src_lang, target="en")
        return translator.translate(text) or text
    except Exception as e:
        print(f"⚠️ Translation to English failed: {e}")
        return text


def translate_from_english(text: str, target_lang: str) -> str:
    """
    Translate English text to target language.

    Args:
        text: English source text
        target_lang: Target language code (e.g. 'hi', 'fr')

    Returns:
        Translated text, or original if target is English or translation fails.
    """
    if not DEEP_TRANSLATOR_AVAILABLE or target_lang == "en" or not target_lang:
        return text

    try:
        translator = GoogleTranslator(source="en", target=target_lang)
        return translator.translate(text) or text
    except Exception as e:
        print(f"⚠️ Translation to {target_lang} failed: {e}")
        return text


def get_language_name(lang_code: str) -> str:
    """Return a human-readable language name for a language code."""
    return LANGUAGE_NAMES.get(lang_code, lang_code.upper())
