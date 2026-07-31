"""
Translator Module
Language detection and translation using deep-translator (no API key needed)
"""

import os
import threading
from typing import Callable, List, Optional

try:
    from langdetect import detect_langs, DetectorFactory, LangDetectException

    # langdetect seeds its sampling from the clock by default, so the same
    # sentence can be reported as different languages on consecutive calls.
    # A fixed seed makes detection reproducible.
    DetectorFactory.seed = 0
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


# A short run of Latin letters carries very little signal — langdetect happily
# calls "cannot log in" Italian, which would then translate an English reply
# into Italian. Demand a longer, confidently-detected string before believing
# anything other than English. Non-Latin scripts are exempt: they are
# unambiguous even in a handful of characters.
MIN_LATIN_CHARS = 20
MIN_CONFIDENCE = 0.90


def _positive_float(name: str, default: float) -> float:
    """Read a positive float from the environment, ignoring junk values."""
    try:
        value = float(os.getenv(name, "") or default)
    except ValueError:
        return default
    return value if value > 0 else default


# deep_translator calls requests.get() with no timeout, so an unreachable or
# slow Google endpoint blocks the calling thread forever. Every translation is
# therefore run on a daemon thread with a deadline: the request degrades to
# untranslated text instead of pinning a FastAPI worker until the socket dies.
TRANSLATION_TIMEOUT = _positive_float("TRANSLATION_TIMEOUT", 8.0)

# GoogleTranslator raises NotValidLength above 5000 characters, which used to
# mean a long ticket was silently never translated at all. Long text is split
# and reassembled instead.
MAX_CHARS_PER_REQUEST = 4500


class TranslationTimeout(RuntimeError):
    """Raised internally when a translation call outlives TRANSLATION_TIMEOUT."""


def _call_with_timeout(fn: Callable[[], str], timeout: float) -> str:
    """
    Run `fn` on a daemon thread and give up after `timeout` seconds.

    The worker cannot be cancelled — a blocked socket read is not interruptible
    — but it is a daemon, so an abandoned call never delays interpreter exit.
    """
    box = {}

    def _run():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            box["error"] = exc

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(timeout)

    if worker.is_alive():
        raise TranslationTimeout(f"translation did not finish within {timeout:g}s")
    if "error" in box:
        raise box["error"]
    return box.get("value", "")


def _split_for_translation(text: str, limit: int = MAX_CHARS_PER_REQUEST) -> List[str]:
    """
    Split text into pieces no longer than `limit`, preferring paragraph, then
    sentence, then whitespace boundaries so the translator sees whole thoughts.
    """
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = max(window.rfind("\n\n"), window.rfind("\n"))
        if cut < limit // 2:
            cut = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
            cut = cut + 1 if cut != -1 else -1
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]

    if remaining:
        chunks.append(remaining)
    return chunks


def _translate(text: str, source: str, target: str) -> str:
    """
    Translate `text`, chunking long input and bounding the whole operation.

    Returns the original text unchanged on any failure — a degraded English
    reply beats no reply at all for a support agent.
    """
    if not text or not text.strip():
        return text

    chunks = _split_for_translation(text)
    # Give the whole message the same wall-clock budget per chunk, so a long
    # description cannot multiply the deadline without bound.
    per_chunk = max(TRANSLATION_TIMEOUT / max(len(chunks), 1), 2.0)

    try:
        translator = GoogleTranslator(source=source, target=target)
        pieces = [
            _call_with_timeout(lambda c=chunk: translator.translate(c) or c, per_chunk)
            for chunk in chunks
        ]
    except TranslationTimeout as e:
        print(f"⚠️ Translation {source}->{target} timed out: {e}")
        return text
    except Exception as e:
        print(f"⚠️ Translation {source}->{target} failed: {e}")
        return text

    return "".join(pieces)


def _has_non_latin(text: str) -> bool:
    """True if the text uses a script other than basic Latin (Devanagari, CJK…)."""
    return any(ord(ch) > 0x024F for ch in text)


def detect_language(text: str) -> str:
    """
    Detect the language of the given text.

    Args:
        text: Input text

    Returns:
        ISO 639-1 language code (e.g. 'en', 'hi', 'fr'). Falls back to 'en'
        when detection is unavailable, unconfident, or returns a language the
        rest of the pipeline cannot translate to.
    """
    if not LANGDETECT_AVAILABLE or not text:
        return "en"

    stripped = text.strip()
    if len(stripped) < 5:
        return "en"

    # Pure-Latin text needs enough characters to be worth trusting
    if not _has_non_latin(stripped) and len(stripped) < MIN_LATIN_CHARS:
        return "en"

    try:
        candidates = detect_langs(stripped)
    except LangDetectException:
        return "en"
    except Exception:
        return "en"

    if not candidates:
        return "en"

    best = candidates[0]
    if best.prob < MIN_CONFIDENCE:
        return "en"

    # Only report languages the translator and voice layers actually support
    if best.lang not in LANGUAGE_NAMES:
        return "en"

    return best.lang


def translate_to_english(text: str, src_lang: Optional[str] = None) -> str:
    """
    Translate text to English.

    Args:
        text: Source text
        src_lang: Source language code. If None, auto-detects.

    Returns:
        English translation, or original text if translation fails.
    """
    if not DEEP_TRANSLATOR_AVAILABLE or not text:
        return text

    src_lang = src_lang or detect_language(text)
    if src_lang == "en":
        return text

    return _translate(text, source=src_lang, target="en")


def translate_from_english(text: str, target_lang: str) -> str:
    """
    Translate English text to target language.

    Args:
        text: English source text
        target_lang: Target language code (e.g. 'hi', 'fr')

    Returns:
        Translated text, or original if target is English or translation fails.
    """
    if not DEEP_TRANSLATOR_AVAILABLE or target_lang == "en" or not target_lang or not text:
        return text

    return _translate(text, source="en", target=target_lang)


def get_language_name(lang_code: str) -> str:
    """Return a human-readable language name for a language code."""
    return LANGUAGE_NAMES.get(lang_code, lang_code.upper())
