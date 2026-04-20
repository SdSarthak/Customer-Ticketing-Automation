"""
Voice Input Module
Transcribes audio bytes to text using Groq Whisper API (free tier).
"""

import os
import tempfile
from typing import Optional


def transcribe_audio(audio_bytes: bytes, language: str = "en-US") -> Optional[str]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set in environment.")

    if not audio_bytes:
        return None

    # Extract ISO language code from BCP-47 (e.g. "en-US" -> "en")
    lang = language.split("-")[0] if language else "en"

    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError("groq package not installed. Run: pip install groq")

    client = Groq(api_key=api_key)

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            result = client.audio.transcriptions.create(
                file=("audio.webm", f, "audio/webm"),
                model="whisper-large-v3-turbo",
                language=lang,
                response_format="text",
            )
        text = result.strip() if isinstance(result, str) else (result.text or "").strip()
        return text or None
    except Exception as e:
        raise RuntimeError(f"Groq Whisper transcription failed: {e}") from e
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def get_language_code_for_speech(lang_code: str) -> str:
    mapping = {
        "en": "en-US", "hi": "hi-IN", "fr": "fr-FR", "de": "de-DE",
        "es": "es-ES", "pt": "pt-BR", "ar": "ar-SA", "zh-cn": "zh-CN",
        "ja": "ja-JP", "ko": "ko-KR", "ru": "ru-RU", "it": "it-IT",
        "nl": "nl-NL", "tr": "tr-TR", "bn": "bn-BD", "ta": "ta-IN",
        "te": "te-IN", "mr": "mr-IN", "gu": "gu-IN", "kn": "kn-IN",
        "ml": "ml-IN", "pa": "pa-IN",
    }
    return mapping.get(lang_code, f"{lang_code}-{lang_code.upper()}")
