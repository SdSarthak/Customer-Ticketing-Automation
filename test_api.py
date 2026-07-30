"""
API test suite — covers endpoints and the voice-chat pipeline.
All external services (Groq, MongoDB, pyttsx3) are mocked so tests run offline.
"""

import io
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

# pytest.ini sets asyncio_mode=auto, so async tests are collected automatically.
# A module-level pytest.mark.asyncio would also (wrongly) tag every sync test.


def _make_rag(initialized=True):
    rag = MagicMock()
    rag.is_initialized = initialized
    rag.get_context.return_value = "mock context"
    rag.get_similar_tickets.return_value = []
    rag.analyze_query.return_value = {}
    rag.vector_store.get_stats.return_value = {"total_documents": 42}
    return rag


def _make_rg():
    rg = MagicMock()
    rg.generate_self_help.return_value = "1. Try restarting.\n2. Clear cache.\n3. Contact support."
    rg.generate_response.return_value = "Here is a detailed response."
    rg.categorize_ticket.return_value = {
        "category": "Technical Support",
        "priority": "medium",
        "sentiment": "neutral",
        "summary": "User has a general technical issue.",
    }
    rg.improve_response.return_value = "Improved response text."
    return rg


def _make_db():
    db = MagicMock()
    db._client = MagicMock()
    db.save_ticket.return_value = "TKT-TEST-0001"
    db.get_all_tickets.return_value = []
    db.get_tickets_by_email.return_value = []
    db.get_ticket.return_value = None
    db.update_ticket_status.return_value = True
    db.knowledge_base_count.return_value = 0
    db.get_all_feedback.return_value = []
    return db


def _make_email():
    es = MagicMock()
    es._is_configured.return_value = False
    return es


def _voice(language, voice_id="voice"):
    """Build a stand-in for a pyttsx3 voice object."""
    v = MagicMock()
    v.languages = [language]
    v.id = voice_id
    v.name = voice_id
    return v


@pytest.fixture()
def client():
    rag = _make_rag()
    rg  = _make_rg()
    db  = _make_db()
    es  = _make_email()

    from src.response_generator import FeedbackLoop
    fl = FeedbackLoop(rg, db_client=None)

    import api

    # Skip the real startup (it would hit MongoDB, Gemini and Groq) and inject
    # the doubles instead. The patch has to stay active for the whole client
    # lifetime because lifespan startup runs inside the `with` block.
    with patch("api._startup_sync"):
        api.rag_engine         = rag
        api.response_generator = rg
        api.feedback_loop      = fl
        api.db                 = db
        api.email_service      = es

        with TestClient(api.app) as c:
            api.rag_engine         = rag
            api.response_generator = rg
            api.feedback_loop      = fl
            api.db                 = db
            api.email_service      = es
            yield c


# ── STATUS ────────────────────────────────────────────────────────────────────

class TestStatus:
    def test_returns_200(self, client):
        assert client.get("/status").status_code == 200

    def test_has_required_fields(self, client):
        d = client.get("/status").json()
        for key in ("status", "rag_initialized", "documents_indexed", "mongodb_connected"):
            assert key in d

    def test_rag_online_reflected(self, client):
        d = client.get("/status").json()
        assert d["rag_initialized"] is True
        assert d["documents_indexed"] == 42


# ── SELF-HELP ─────────────────────────────────────────────────────────────────

class TestSelfHelp:
    def test_happy_path(self, client):
        r = client.post("/self-help", json={"issue": "My app keeps crashing"})
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d["steps"], list) and len(d["steps"]) > 0

    def test_missing_issue_returns_400(self, client):
        assert client.post("/self-help", json={}).status_code == 400

    def test_empty_issue_returns_400(self, client):
        assert client.post("/self-help", json={"issue": "   "}).status_code == 400

    def test_response_text_present(self, client):
        d = client.post("/self-help", json={"issue": "login not working"}).json()
        assert d.get("response")

    def test_language_field_returned(self, client):
        d = client.post("/self-help", json={"issue": "password reset", "language": "en"}).json()
        assert "language" in d

    def test_rag_not_ready_returns_503(self, client):
        import api
        orig = api.rag_engine
        api.rag_engine = _make_rag(initialized=False)
        try:
            assert client.post("/self-help", json={"issue": "test"}).status_code == 503
        finally:
            api.rag_engine = orig


# ── TICKETS ───────────────────────────────────────────────────────────────────

VALID_TICKET = {
    "user_name": "Jane Doe",
    "user_email": "jane@example.com",
    "issue_description": "I cannot log in to my account.",
    "category": "Technical Support",
    "priority": "medium",
}


class TestTickets:
    def test_create_ticket_happy_path(self, client):
        r = client.post("/tickets", json=VALID_TICKET)
        assert r.status_code == 200
        assert r.json()["ticket_id"].startswith("TKT-")

    def test_create_ticket_has_ai_response(self, client):
        assert "ai_response" in client.post("/tickets", json=VALID_TICKET).json()

    def test_create_ticket_has_priority(self, client):
        d = client.post("/tickets", json=VALID_TICKET).json()
        assert d["priority"] in ("low", "medium", "high", "urgent")

    def test_get_tickets_returns_list(self, client):
        r = client.get("/tickets")
        assert r.status_code == 200 and isinstance(r.json(), list)

    def test_get_by_email_returns_list(self, client):
        r = client.get("/tickets/by-email/jane@example.com")
        assert r.status_code == 200 and isinstance(r.json(), list)

    def test_get_nonexistent_returns_404(self, client):
        assert client.get("/tickets/TKT-DOES-NOT-EXIST").status_code == 404

    def test_patch_status_valid(self, client):
        import api
        api.db.update_ticket_status.return_value = True
        r = client.patch("/tickets/TKT-TEST-0001/status", json={"status": "resolved"})
        assert r.status_code == 200

    def test_patch_status_invalid_returns_400(self, client):
        assert client.patch("/tickets/TKT-TEST-0001/status", json={"status": "nonsense"}).status_code == 400

    def test_create_with_screenshot(self, client):
        data = {"user_name": "Test", "user_email": "t@t.com", "issue_description": "Error on screen"}
        files = {"screenshot": ("screen.png", io.BytesIO(b"fakepng"), "image/png")}
        r = client.post("/tickets/with-screenshot", data=data, files=files)
        assert r.status_code == 200 and "ticket_id" in r.json()

    def test_invalid_email_returns_400(self, client):
        bad = {**VALID_TICKET, "user_email": "not-an-email"}
        assert client.post("/tickets", json=bad).status_code == 400

    def test_empty_description_returns_400(self, client):
        blank = {**VALID_TICKET, "issue_description": "   "}
        assert client.post("/tickets", json=blank).status_code == 400

    def test_unknown_priority_is_normalized(self, client):
        weird = {**VALID_TICKET, "priority": "CATASTROPHIC"}
        assert client.post("/tickets", json=weird).json()["priority"] == "medium"

    def test_generator_unavailable_returns_503(self, client):
        import api
        orig = api.response_generator
        api.response_generator = None
        try:
            assert client.post("/tickets", json=VALID_TICKET).status_code == 503
        finally:
            api.response_generator = orig

    def test_stats_endpoint_not_read_as_ticket_id(self, client):
        import api
        api.db.get_ticket_stats.return_value = {
            "total": 3, "by_status": {"open": 3}, "by_priority": {}, "by_category": {}
        }
        r = client.get("/tickets/stats")
        assert r.status_code == 200 and r.json()["total"] == 3


class TestScreenshotUpload:
    BASE = {"user_name": "Test", "user_email": "t@t.com", "issue_description": "Broken"}

    def _post(self, client, filename, content=b"fakepng", ctype="image/png"):
        return client.post(
            "/tickets/with-screenshot",
            data=self.BASE,
            files={"screenshot": (filename, io.BytesIO(content), ctype)},
        )

    def test_traversal_filename_cannot_escape_uploads(self, client, tmp_path, monkeypatch):
        import api, os
        monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path / "uploads"))
        r = self._post(client, "../../src/config.py")
        # Rejected outright: .py is not an allowed screenshot type
        assert r.status_code == 400
        assert not (tmp_path.parent / "config.py").exists()

    def test_traversal_with_image_extension_is_contained(self, client, tmp_path, monkeypatch):
        import api, os
        upload_dir = tmp_path / "uploads"
        monkeypatch.setattr(api, "UPLOAD_DIR", str(upload_dir))
        r = self._post(client, "../../../evil.png")
        assert r.status_code == 200
        written = list(upload_dir.iterdir())
        assert len(written) == 1
        # Original name discarded, file stays inside the upload directory
        assert written[0].name != "evil.png"
        assert written[0].parent == upload_dir

    def test_disallowed_extension_returns_400(self, client, tmp_path, monkeypatch):
        import api
        monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path / "uploads"))
        assert self._post(client, "payload.exe").status_code == 400

    def test_oversized_screenshot_returns_413(self, client, tmp_path, monkeypatch):
        import api
        monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path / "uploads"))
        monkeypatch.setattr(api, "MAX_SCREENSHOT_BYTES", 1024)
        r = self._post(client, "big.png", content=b"x" * 5000)
        assert r.status_code == 413
        assert list((tmp_path / "uploads").iterdir()) == []

    def test_ticket_without_screenshot_still_works(self, client):
        r = client.post("/tickets/with-screenshot", data=self.BASE)
        assert r.status_code == 200
        assert r.json()["screenshot_saved"] is False


# ── TRANSCRIBE ────────────────────────────────────────────────────────────────

class TestTranscribe:
    def test_returns_text(self, client):
        with patch("api.transcribe_audio", return_value="hello world"):
            r = client.post("/transcribe",
                files={"audio": ("s.webm", io.BytesIO(b"x"), "audio/webm")},
                data={"language": "en"})
        assert r.status_code == 200 and r.json()["text"] == "hello world"

    def test_empty_returns_422(self, client):
        with patch("api.transcribe_audio", return_value=None):
            r = client.post("/transcribe",
                files={"audio": ("s.webm", io.BytesIO(b""), "audio/webm")},
                data={"language": "en"})
        assert r.status_code == 422

    def test_service_down_returns_503(self, client):
        with patch("api.transcribe_audio", side_effect=RuntimeError("down")):
            r = client.post("/transcribe",
                files={"audio": ("s.webm", io.BytesIO(b"x"), "audio/webm")},
                data={"language": "en"})
        assert r.status_code == 503


# ── VOICE CHAT ────────────────────────────────────────────────────────────────

class TestVoiceChat:
    FAKE_WAV = b"RIFF" + b"\x00" * 124

    def _post(self, client):
        return client.post("/voice-chat",
            files={"audio": ("s.webm", io.BytesIO(b"x"), "audio/webm")},
            data={"language": "en", "attempt": "0"})

    def _mocked(self, client, transcript="test issue"):
        with patch("api.transcribe_audio", return_value=transcript), \
             patch("api.detect_language", return_value="en"), \
             patch("api.translate_to_english", side_effect=lambda t, l: t), \
             patch("api.translate_from_english", side_effect=lambda t, l: t), \
             patch("api._text_to_mp3", new=AsyncMock(return_value=self.FAKE_WAV)):
            return self._post(client)

    def test_returns_audio(self, client):
        r = self._mocked(client)
        assert r.status_code == 200
        assert "audio/wav" in r.headers["content-type"]

    def test_transcript_header(self, client):
        r = self._mocked(client, "billing problem")
        assert r.headers.get("x-transcript") == "billing problem"

    def test_response_text_header(self, client):
        r = self._mocked(client)
        assert r.headers.get("x-response-text")

    def test_audio_bytes_returned(self, client):
        r = self._mocked(client)
        assert len(r.content) == len(self.FAKE_WAV)

    def test_empty_transcript_returns_422(self, client):
        with patch("api.transcribe_audio", return_value=None):
            assert self._post(client).status_code == 422

    def test_stt_error_returns_503(self, client):
        with patch("api.transcribe_audio", side_effect=RuntimeError("down")):
            assert self._post(client).status_code == 503

    def test_tts_error_returns_503(self, client):
        with patch("api.transcribe_audio", return_value="issue"), \
             patch("api.detect_language", return_value="en"), \
             patch("api.translate_to_english", side_effect=lambda t, l: t), \
             patch("api.translate_from_english", side_effect=lambda t, l: t), \
             patch("api._text_to_mp3", new=AsyncMock(side_effect=RuntimeError("tts down"))):
            assert self._post(client).status_code == 503

    def test_rag_not_ready_returns_503(self, client):
        import api
        orig = api.rag_engine
        api.rag_engine = _make_rag(initialized=False)
        try:
            assert self._post(client).status_code == 503
        finally:
            api.rag_engine = orig


# ── FEEDBACK ──────────────────────────────────────────────────────────────────

class TestFeedback:
    def test_submit_returns_improved(self, client):
        r = client.post("/feedback", json={
            "query": "login issue",
            "original_response": "Try resetting.",
            "feedback": "Too vague",
            "rating": 2,
        })
        assert r.status_code == 200 and "improved_response" in r.json()

    def test_get_returns_list(self, client):
        r = client.get("/feedback")
        assert r.status_code == 200 and isinstance(r.json(), list)


# ── ANALYZE ───────────────────────────────────────────────────────────────────

class TestAnalyze:
    def test_happy_path(self, client):
        r = client.post("/analyze", json={"issue": "billing problem"})
        assert r.status_code == 200 and "categorization" in r.json()

    def test_empty_returns_400(self, client):
        assert client.post("/analyze", json={}).status_code == 400


# ── VOICE INPUT MODULE ────────────────────────────────────────────────────────

class TestVoiceInputModule:
    def test_known_lang_codes(self):
        from src.voice_input import get_language_code_for_speech
        assert get_language_code_for_speech("hi") == "hi-IN"
        assert get_language_code_for_speech("en") == "en-US"

    def test_unknown_lang_fallback(self):
        from src.voice_input import get_language_code_for_speech
        assert get_language_code_for_speech("xx") == "xx-XX"

    def test_no_key_raises(self):
        import os
        from src.voice_input import transcribe_audio
        orig = os.environ.pop("GROQ_API_KEY", None)
        try:
            with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
                transcribe_audio(b"audio")
        finally:
            if orig:
                os.environ["GROQ_API_KEY"] = orig


# ── TTS UNIT ──────────────────────────────────────────────────────────────────

class TestTTS:
    async def test_clean_strips_markdown(self):
        from api import _clean_for_tts
        result = _clean_for_tts("**bold** and *italic* and `code`")
        assert "**" not in result and "`" not in result

    async def test_tts_returns_wav(self, tmp_path):
        import os
        fake_wav = b"RIFF" + b"\x00" * 100
        wav_file = tmp_path / "out.wav"
        wav_file.write_bytes(fake_wav)

        mock_engine = MagicMock()
        mock_engine.getProperty.side_effect = lambda k: (
            [_voice("en-US"), _voice("hi-IN")] if k == "voices" else 160
        )

        fd = os.open(str(tmp_path / "unused.tmp"), os.O_CREAT | os.O_RDWR)
        with patch("pyttsx3.init", return_value=mock_engine), \
             patch("api.tempfile.mkstemp", return_value=(fd, str(wav_file))):
            from api import _text_to_mp3
            result = await _text_to_mp3("Hello world", "en")

        assert result == fake_wav

    async def test_empty_text_raises(self):
        from api import _text_to_mp3
        with pytest.raises(RuntimeError):
            await _text_to_mp3("   ", "en")


class TestVoiceSelection:
    def test_matches_language_tag(self):
        from api import _pick_voice
        voices = [_voice("en-US"), _voice("hi-IN")]
        assert _pick_voice(voices, "hi") is voices[1]

    def test_matches_bytes_language_tag(self):
        from api import _pick_voice
        voices = [_voice(b"\x05en-US"), _voice(b"\x05fr-FR")]
        assert _pick_voice(voices, "fr") is voices[1]

    def test_falls_back_when_no_match(self):
        from api import _pick_voice
        voices = [_voice("en-US"), _voice("en-GB")]
        assert _pick_voice(voices, "ja") is voices[1]

    def test_empty_voice_list_returns_none(self):
        from api import _pick_voice
        assert _pick_voice([], "en") is None
