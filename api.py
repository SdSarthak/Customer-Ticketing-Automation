"""
FastAPI Backend — AI Customer Support System
Serves index.html and all REST endpoints.
Start with: uvicorn api:app --reload --port 8000
Then open:  http://localhost:8000
"""

import asyncio
import os
import re
import json as _json
import tempfile
import uuid
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
    BackgroundTasks,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from src.config import Config
from src.data_loader import DataLoader
from src.rag_engine import RAGEngine
from src.response_generator import ResponseGenerator, FeedbackLoop
from src.db import MongoDBClient
from src.email_service import EmailService
from src.translator import detect_language, translate_to_english, translate_from_english, get_language_name
from src.voice_input import transcribe_audio, get_language_code_for_speech

# ─── Global singletons ───────────────────────────────────────────────────────

rag_engine: Optional[RAGEngine] = None
response_generator: Optional[ResponseGenerator] = None
feedback_loop: Optional[FeedbackLoop] = None
db: Optional[MongoDBClient] = None
email_service: Optional[EmailService] = None


def _startup_sync():
    """
    Build the service singletons.

    Every step is individually guarded: a missing API key or an unreachable
    MongoDB should leave the server running in a degraded mode that /status can
    describe, rather than killing the process on boot.
    """
    global rag_engine, response_generator, feedback_loop, db, email_service

    try:
        Config.validate()
    except ValueError as e:
        print(f"WARNING: {e}")

    # MongoDB
    db = MongoDBClient()
    try:
        db.connect()
        print("MongoDB connected")
    except Exception as e:
        print(f"WARNING: MongoDB not available — {e}")
        try:
            db.close()
        except Exception:
            pass
        db = None

    # Email
    email_service = EmailService()

    # RAG — wrapped so missing API keys don't crash startup
    try:
        rag_engine = RAGEngine()
        faiss_file = os.path.join(Config.VECTOR_STORE_PATH, "faiss_index.bin")

        if os.path.exists(faiss_file):
            rag_engine.load_from_disk(Config.VECTOR_STORE_PATH)
        elif db and db.knowledge_base_count() > 0:
            rag_engine.initialize_from_db(db)
            rag_engine.save_to_disk(Config.VECTOR_STORE_PATH)
        elif os.path.exists(Config.DATA_PATH):
            loader = DataLoader(Config.DATA_PATH)
            loader.load_data()
            docs = loader.create_documents()
            rag_engine.initialize_from_documents(docs)
            rag_engine.save_to_disk(Config.VECTOR_STORE_PATH)
            if db:
                db.save_knowledge_docs(docs)
        else:
            print("WARNING: No data source found. RAG not initialized.")
    except Exception as e:
        print(f"WARNING: RAG init failed — {e}")
        rag_engine = None

    # Response generator + feedback loop — wrapped for same reason
    try:
        response_generator = ResponseGenerator(rag_engine=rag_engine)
        feedback_loop = FeedbackLoop(response_generator, db_client=db)
    except Exception as e:
        print(f"WARNING: ResponseGenerator init failed — {e}")
        response_generator = None
        feedback_loop = None

    print("Server ready. Open http://localhost:8000")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Startup/shutdown hook.

    Uses the lifespan API rather than the removed @app.on_event decorator, and
    runs the (blocking) index load on a thread so the event loop stays free.
    """
    await asyncio.to_thread(_startup_sync)
    yield
    if db:
        try:
            db.close()
        except Exception as e:
            print(f"WARNING: error closing MongoDB — {e}")


# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Customer Support API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Shared guards & helpers ──────────────────────────────────────────────────

UPLOAD_DIR = "uploads"
MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_AUDIO_BYTES = 15 * 1024 * 1024      # 15 MB — well over a minute of webm/opus
ALLOWED_SCREENSHOT_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

# Free-text limits. Without them a single request can push an arbitrary amount
# of text through the LLM, the translator and into MongoDB.
MAX_NAME_CHARS = 200
MAX_ISSUE_CHARS = 20_000
MAX_ATTEMPTS = 20
MAX_ATTEMPT_CHARS = 2_000


async def _read_upload_limited(upload: UploadFile, max_bytes: int, label: str) -> bytes:
    """
    Read an upload into memory, refusing anything over `max_bytes`.

    `await upload.read()` with no argument buffers the entire body first, so a
    single large POST could exhaust the process before any check ran. Reading in
    chunks lets the limit be enforced before the memory is committed.
    """
    chunks: List[bytes] = []
    total = 0
    while chunk := await upload.read(64 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                413,
                f"{label} exceeds the {max_bytes // (1024 * 1024)} MB limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _clean_text(value: Optional[str], field: str, max_chars: int, required: bool) -> str:
    """Trim a free-text field and enforce a length bound, or 400."""
    text = (value or "").strip()
    if required and not text:
        raise HTTPException(400, f"{field} must not be empty")
    if len(text) > max_chars:
        raise HTTPException(
            400, f"{field} is too long ({len(text)} chars, max {max_chars})"
        )
    return text


def _require_generator():
    """
    Every ticket/analysis route needs the LLM. Startup keeps the server alive
    without it (so /status can explain what's wrong), so each route has to say
    'unavailable' rather than blow up with an AttributeError on None.
    """
    if response_generator is None:
        raise HTTPException(
            503, "Response generator not available. Check GROQ_API_KEY and restart."
        )
    return response_generator


def _require_rag():
    if not rag_engine or not rag_engine.is_initialized:
        raise HTTPException(
            503, "RAG engine not ready. Check your API keys and restart."
        )
    return rag_engine


def _validate_email(email: str) -> str:
    email = (email or "").strip()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, f"'{email}' is not a valid email address")
    return email


def _discard_upload(path: Optional[str]) -> None:
    """Delete a half-finished upload, ignoring a file that is already gone."""
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


async def _save_screenshot(screenshot: UploadFile) -> Optional[str]:
    """
    Persist an uploaded screenshot under uploads/ and return its path.

    The client-supplied filename is never trusted: it is reduced to a safe
    extension and given a random stem, so a name like '../../src/config.py'
    cannot escape the upload directory or overwrite project files.

    Reads are chunked and awaited so a 5 MB upload neither lands in memory in
    one piece nor blocks the event loop, and an over-limit upload is removed
    before it is fully written.
    """
    if not screenshot or not screenshot.filename:
        return None

    ext = os.path.splitext(screenshot.filename)[1].lower()
    if ext not in ALLOWED_SCREENSHOT_EXTS:
        raise HTTPException(
            400,
            f"Unsupported screenshot type '{ext or 'unknown'}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_SCREENSHOT_EXTS))}",
        )

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")

    written = 0
    try:
        with open(path, "wb") as f:
            while chunk := await screenshot.read(64 * 1024):
                written += len(chunk)
                if written > MAX_SCREENSHOT_BYTES:
                    raise HTTPException(
                        413,
                        f"Screenshot exceeds the "
                        f"{MAX_SCREENSHOT_BYTES // (1024 * 1024)} MB limit",
                    )
                f.write(chunk)
    except BaseException:
        # Never leave a partial or rejected upload behind on disk.
        _discard_upload(path)
        raise

    if written == 0:
        _discard_upload(path)
        return None

    return path


def _build_ticket(
    user_name: str,
    user_email: str,
    issue_description: str,
    category: Optional[str],
    priority: Optional[str],
    language: Optional[str],
    attempt_history: List[str],
    screenshot_path: Optional[str] = None,
):
    """
    Shared ticket pipeline used by both the JSON and multipart endpoints:
    detect language → translate → categorize → generate → persist.

    Returns (ticket_id, ticket_data, ai_response_en).
    """
    generator = _require_generator()

    issue_description = _clean_text(
        issue_description, "issue_description", MAX_ISSUE_CHARS, required=True
    )
    user_name = _clean_text(user_name, "user_name", MAX_NAME_CHARS, required=True)
    user_email = _validate_email(user_email)

    attempt_history = [
        _clean_text(a, "attempt_history entry", MAX_ATTEMPT_CHARS, required=False)
        for a in (attempt_history or [])[:MAX_ATTEMPTS]
    ]
    attempt_history = [a for a in attempt_history if a]

    lang = language or detect_language(issue_description)
    english_issue = (
        translate_to_english(issue_description, lang)
        if lang != "en"
        else issue_description
    )

    categorization = generator.categorize_ticket(english_issue)
    final_category = category or categorization.get("category", "General Inquiry")
    final_priority = (priority or categorization.get("priority", "medium")).lower()
    if final_priority not in Config.PRIORITY_SLA:
        final_priority = "medium"

    ai_response_en = generator.generate_response(english_issue)
    ai_response = (
        translate_from_english(ai_response_en, lang) if lang != "en" else ai_response_en
    )

    ticket_data = {
        "user_name": user_name,
        "user_email": user_email,
        "issue_description": issue_description,
        "category": final_category,
        "priority": final_priority,
        "sentiment": categorization.get("sentiment", "neutral"),
        "summary": categorization.get("summary", ""),
        "ai_response": ai_response,
        "screenshot_path": screenshot_path,
        "attempt_history": attempt_history,
        "language": lang,
    }

    ticket_id = "TKT-OFFLINE-0001"
    if db:
        try:
            ticket_id = db.save_ticket(ticket_data)
        except Exception as e:
            print(f"WARNING: MongoDB save failed — {e}")

    return ticket_id, ticket_data, ai_response_en


# ─── Serve frontend ───────────────────────────────────────────────────────────

@app.get("/")
def serve_index():
    """Serve the SupportDesk frontend (index.html)"""
    path = os.path.join(os.path.dirname(__file__), "index.html")
    if not os.path.exists(path):
        raise HTTPException(404, "index.html not found")
    return FileResponse(path, media_type="text/html")


# ─── Status ───────────────────────────────────────────────────────────────────

@app.get("/status")
def get_status():
    """
    Returns system status.
    Frontend reads: d.status (string shown in chip), plus d.rag_initialized etc.
    """
    docs_indexed = 0
    if rag_engine and rag_engine.is_initialized:
        try:
            docs_indexed = rag_engine.vector_store.get_stats().get("total_documents", 0)
        except Exception:
            pass

    rag_ok = rag_engine.is_initialized if rag_engine else False
    llm_ok = response_generator is not None
    mongo_ok = db is not None and db._client is not None

    # The frontend shows d.status as the chip text
    if rag_ok and llm_ok:
        status_text = f"Online · {docs_indexed} docs"
    elif not llm_ok:
        status_text = "Degraded — LLM not configured"
    else:
        status_text = "Degraded — RAG not ready"

    return {
        "status": status_text,
        "rag_initialized": rag_ok,
        "llm_ready": llm_ok,
        "documents_indexed": docs_indexed,
        "mongodb_connected": mongo_ok,
        "email_configured": email_service._is_configured() if email_service else False,
        "groq_configured": bool(Config.GROQ_API_KEY),
        "gemini_configured": bool(Config.GOOGLE_API_KEY),
    }


# ─── Self-help (Step 1) ───────────────────────────────────────────────────────

class SelfHelpRequest(BaseModel):
    issue: Optional[str] = None   # frontend sends "issue"
    query: Optional[str] = None   # alias
    language: Optional[str] = None


@app.post("/self-help")
def self_help(req: SelfHelpRequest):
    """
    Returns self-help steps for a customer issue.
    Frontend expects:
      { response: str, steps: list[str], language: str }
    """
    _require_rag()
    generator = _require_generator()

    raw_query = req.issue or req.query or ""
    if not raw_query.strip():
        raise HTTPException(400, "Provide 'issue' in request body")

    lang = req.language or detect_language(raw_query)
    english_query = translate_to_english(raw_query, lang) if lang != "en" else raw_query

    # Generate self-help text
    steps_en = generator.generate_self_help(english_query)

    # Translate back if needed
    steps_text = translate_from_english(steps_en, lang) if lang != "en" else steps_en

    # Parse numbered steps into a list for the frontend's step-list rendering
    lines = [l.strip() for l in steps_text.split("\n") if l.strip()]
    steps = []
    intro_lines = []
    for line in lines:
        # Strip leading "1." "2." "3." etc.
        stripped = line.lstrip("0123456789.-) ").strip()
        if stripped:
            if line[0].isdigit():
                steps.append(stripped)
            else:
                intro_lines.append(stripped)

    response_text = " ".join(intro_lines) if intro_lines else "Here are some steps to try:"
    if not steps:
        # No numbered steps found — return whole text as single step
        steps = [steps_text]
        response_text = "Here are some steps to try:"

    return {
        "response": response_text,
        "steps": steps,
        "language": lang,
        "language_name": get_language_name(lang),
        "english_query": english_query,
    }


# ─── Create ticket (Step 2, JSON) ─────────────────────────────────────────────

class TicketRequest(BaseModel):
    user_name: str
    user_email: str
    issue_description: str
    category: Optional[str] = None
    priority: Optional[str] = None
    language: Optional[str] = None
    attempt_history: Optional[List[str]] = []


@app.post("/tickets")
def create_ticket(req: TicketRequest, background: BackgroundTasks):
    """
    Create a ticket (no screenshot). Frontend expects ticket_id in response.

    Emails are queued as a background task — two SMTP round-trips would
    otherwise add seconds to the response the customer is waiting on.
    """
    ticket_id, ticket_data, ai_response_en = _build_ticket(
        user_name=req.user_name,
        user_email=req.user_email,
        issue_description=req.issue_description,
        category=req.category,
        priority=req.priority,
        language=req.language,
        attempt_history=req.attempt_history or [],
    )

    background.add_task(_send_emails, ticket_id, ticket_data, ai_response_en, None)

    return {
        "ticket_id": ticket_id,
        "category": ticket_data["category"],
        "priority": ticket_data["priority"],
        "sentiment": ticket_data["sentiment"],
        "summary": ticket_data["summary"],
        "ai_response": ticket_data["ai_response"],
        "language": ticket_data["language"],
        "email_sent": email_service._is_configured() if email_service else False,
    }


# ─── Create ticket with screenshot (multipart) ───────────────────────────────

@app.post("/tickets/with-screenshot")
async def create_ticket_with_screenshot(
    background: BackgroundTasks,
    user_name: str = Form(...),
    user_email: str = Form(...),
    issue_description: str = Form(...),
    category: Optional[str] = Form(None),
    priority: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    attempt_history: Optional[str] = Form("[]"),
    screenshot: Optional[UploadFile] = File(None),
):
    """Create a ticket with optional screenshot attachment."""
    # Validate the cheap fields before touching the disk, so a bad email does
    # not leave an orphaned file in uploads/ on every rejected request.
    _clean_text(issue_description, "issue_description", MAX_ISSUE_CHARS, required=True)
    _clean_text(user_name, "user_name", MAX_NAME_CHARS, required=True)
    _validate_email(user_email)

    try:
        history = _json.loads(attempt_history or "[]")
        if not isinstance(history, list):
            history = []
    except (ValueError, TypeError):
        history = []
    history = [str(item) for item in history]

    screenshot_path = await _save_screenshot(screenshot)

    try:
        ticket_id, ticket_data, ai_response_en = _build_ticket(
            user_name=user_name,
            user_email=user_email,
            issue_description=issue_description,
            category=category,
            priority=priority,
            language=language,
            attempt_history=history,
            screenshot_path=screenshot_path,
        )
    except BaseException:
        _discard_upload(screenshot_path)
        raise

    background.add_task(
        _send_emails, ticket_id, ticket_data, ai_response_en, screenshot_path
    )

    return {
        "ticket_id": ticket_id,
        "category": ticket_data["category"],
        "priority": ticket_data["priority"],
        "sentiment": ticket_data["sentiment"],
        "summary": ticket_data["summary"],
        "ai_response": ticket_data["ai_response"],
        "language": ticket_data["language"],
        "email_sent": email_service._is_configured() if email_service else False,
        "screenshot_saved": screenshot_path is not None,
    }


def _send_emails(ticket_id, ticket_data, ai_response_en, screenshot_path):
    """Helper: fire both confirmation emails (swallows errors gracefully)."""
    if not email_service or not email_service._is_configured():
        return
    priority = ticket_data.get("priority", "medium")
    sla = Config.PRIORITY_SLA.get(priority, 24)
    try:
        email_service.send_customer_confirmation(
            to_email=ticket_data["user_email"],
            user_name=ticket_data["user_name"],
            ticket_id=ticket_id,
            category=ticket_data.get("category", "General Inquiry"),
            priority=priority,
            ai_response=ai_response_en,
            sla_hours=sla,
        )
        email_service.send_developer_alert(
            ticket_id=ticket_id,
            user_name=ticket_data["user_name"],
            user_email=ticket_data["user_email"],
            issue_description=ticket_data.get("issue_description", ""),
            category=ticket_data.get("category", "General Inquiry"),
            priority=priority,
            sentiment=ticket_data.get("sentiment", "neutral"),
            ai_response=ai_response_en,
            screenshot_path=screenshot_path,
            attempt_history=ticket_data.get("attempt_history", []),
        )
    except Exception as e:
        print(f"WARNING: Email failed — {e}")


# ─── Voice transcription ──────────────────────────────────────────────────────

@app.post("/transcribe")
async def transcribe_voice(
    audio: UploadFile = File(...),
    language: Optional[str] = Form("en"),
):
    """
    Transcribe audio to text.
    Frontend sends field 'audio', reads d.text from response.
    """
    audio_bytes = await _read_upload_limited(audio, MAX_AUDIO_BYTES, "Audio upload")
    if not audio_bytes:
        raise HTTPException(400, "No audio was uploaded")
    speech_lang = get_language_code_for_speech(language or "en")
    try:
        text = transcribe_audio(audio_bytes, language=speech_lang)
        if not text:
            raise HTTPException(422, "Could not understand audio. Please speak clearly and try again.")
        return {"text": text, "transcript": text, "language": language}
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(503, str(e))


# ─── Voice chat (STT → RAG → TTS round-trip) ─────────────────────────────────

def _clean_for_tts(text: str) -> str:
    """Strip markdown symbols so TTS speaks clean prose."""
    clean = text.replace("<br>", " ").replace("\n", " ")
    for tag in ["**", "*", "__", "_", "`"]:
        clean = clean.replace(tag, "")
    return clean.strip()


def _pick_voice(voices, lang: str):
    """
    Best-effort match of an installed system voice to the reply language.

    pyttsx3 exposes voices per platform with no common naming scheme, so this
    checks the advertised `languages` list and then the voice id/name for the
    language code. Falls back to the second installed voice (a female voice on
    most Windows installs) and finally to whatever the default is.
    """
    if not voices:
        return None

    lang = (lang or "en").split("-")[0].lower()

    for voice in voices:
        langs = getattr(voice, "languages", None) or []
        for entry in langs:
            if isinstance(entry, bytes):
                entry = entry.decode("utf-8", errors="ignore")
            if str(entry).lower().lstrip("\x05").startswith(lang):
                return voice

    for voice in voices:
        haystack = f"{getattr(voice, 'id', '')} {getattr(voice, 'name', '')}".lower()
        if f"-{lang}" in haystack or f"_{lang}" in haystack:
            return voice

    return voices[1] if len(voices) > 1 else voices[0]


def _synthesize_wav(text: str, lang: str) -> bytes:
    """Blocking pyttsx3 synthesis. Runs in a worker thread, never inline."""
    import pyttsx3

    fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        engine.setProperty("volume", 1.0)

        voice = _pick_voice(engine.getProperty("voices"), lang)
        if voice is not None:
            engine.setProperty("voice", voice.id)

        engine.save_to_file(text, tmp_path)
        engine.runAndWait()

        with open(tmp_path, "rb") as f:
            data = f.read()
        if not data:
            raise RuntimeError("TTS produced an empty audio file")
        return data
    except Exception as e:
        raise RuntimeError(f"pyttsx3 TTS failed: {e}") from e
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def _text_to_mp3(text: str, lang: str) -> bytes:
    """
    Convert text to WAV bytes using pyttsx3 (fully offline, no API needed).
    Returns WAV audio — browsers handle it fine via Audio().

    pyttsx3 blocks for a second or more, so it is pushed onto a thread to keep
    the event loop free for other requests.
    """
    clean = _clean_for_tts(text)
    if not clean:
        raise RuntimeError("Empty TTS text")

    return await asyncio.to_thread(_synthesize_wav, clean, lang)


@app.post("/voice-chat")
async def voice_chat(
    audio: UploadFile = File(...),
    language: Optional[str] = Form("en"),
    attempt: Optional[int] = Form(0),
):
    """
    Full voice round-trip:
      1. Groq Whisper STT → transcript
      2. Self-help RAG+Groq response
      3. pyttsx3 TTS → WAV audio response (offline, no API key needed)

    Returns: audio/wav stream with headers:
      X-Transcript: what the user said
      X-Response-Text: what the AI replied
      X-Language: detected language
    """
    _require_rag()
    generator = _require_generator()

    audio_bytes = await _read_upload_limited(audio, MAX_AUDIO_BYTES, "Audio upload")
    if not audio_bytes:
        raise HTTPException(400, "No audio was uploaded")
    lang = language or "en"
    speech_lang = get_language_code_for_speech(lang)

    # Step 1 — STT
    try:
        transcript = transcribe_audio(audio_bytes, language=speech_lang)
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    if not transcript:
        raise HTTPException(422, "Could not understand audio — please try again")

    # Step 2 — detect language from transcript, translate, RAG, translate back
    detected_lang = detect_language(transcript)
    english_query = translate_to_english(transcript, detected_lang) if detected_lang != "en" else transcript
    steps_en = generator.generate_self_help(english_query)
    reply_text = translate_from_english(steps_en, detected_lang) if detected_lang != "en" else steps_en

    # Flatten numbered steps into prose for TTS (numbers sound odd spoken)
    lines = [l.strip().lstrip("0123456789.-) ").strip() for l in reply_text.split("\n") if l.strip()]
    tts_text = " ".join(lines) if lines else reply_text

    # Step 3 — TTS
    try:
        mp3_bytes = await _text_to_mp3(tts_text, detected_lang)
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    def _h(s: str) -> str:
        s = s.replace("\r", " ").replace("\n", " ")
        return s.encode("ascii", errors="ignore").decode("ascii")

    return Response(
        content=mp3_bytes,
        media_type="audio/wav",
        headers={
            "X-Transcript": _h(transcript),
            "X-Response-Text": _h(reply_text[:500]),
            "X-Language": _h(detected_lang),
            "Access-Control-Expose-Headers": "X-Transcript, X-Response-Text, X-Language",
        },
    )


# ─── Ticket queries ───────────────────────────────────────────────────────────

@app.get("/tickets")
def get_all_tickets():
    """Return all tickets for admin view."""
    if not db:
        return []
    try:
        return db.get_all_tickets()
    except Exception as e:
        print(f"WARNING: could not list tickets — {e}")
        return []


@app.get("/tickets/stats")
def get_ticket_stats():
    """
    Aggregate ticket counts for dashboards.
    Declared before /tickets/{ticket_id} so 'stats' is not read as an ID.
    """
    if not db:
        return {"total": 0, "by_status": {}, "by_priority": {}, "by_category": {}}
    try:
        return db.get_ticket_stats()
    except Exception as e:
        print(f"WARNING: could not compute ticket stats — {e}")
        return {"total": 0, "by_status": {}, "by_priority": {}, "by_category": {}}


@app.get("/tickets/by-email/{email}")
def get_tickets_by_email(email: str):
    """Return all tickets for a customer email."""
    if not db:
        return []
    try:
        return db.get_tickets_by_email(email)
    except Exception:
        return []


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    """Get a single ticket by ID."""
    if not db:
        raise HTTPException(503, "Database not available")
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(404, f"Ticket {ticket_id} not found")
    return ticket


class StatusUpdate(BaseModel):
    status: str


@app.patch("/tickets/{ticket_id}/status")
def update_ticket_status(ticket_id: str, body: StatusUpdate):
    """
    Update ticket status.
    Frontend sends PATCH with JSON body { status: "..." }.
    """
    valid = {"open", "in_progress", "resolved"}
    if body.status not in valid:
        raise HTTPException(400, f"Status must be one of: {', '.join(valid)}")
    if not db:
        raise HTTPException(503, "Database not available")
    updated = db.update_ticket_status(ticket_id, body.status)
    if not updated:
        raise HTTPException(404, f"Ticket {ticket_id} not found")
    return {"ticket_id": ticket_id, "status": body.status}


# ─── Feedback ─────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    query: str
    original_response: str
    feedback: str
    rating: Optional[int] = None


@app.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    if not feedback_loop:
        raise HTTPException(503, "Feedback loop not initialized")
    result = feedback_loop.submit_feedback(
        query=req.query,
        original_response=req.original_response,
        feedback=req.feedback,
        rating=req.rating,
    )
    return {"improved_response": result["improved_response"]}


@app.get("/feedback")
def get_feedback():
    if not feedback_loop:
        return []
    return feedback_loop.get_feedback_history()


# ─── Analysis (bonus endpoint) ────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    issue: Optional[str] = None
    query: Optional[str] = None
    language: Optional[str] = None


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    raw = req.issue or req.query or ""
    if not raw.strip():
        raise HTTPException(400, "Provide 'issue' in request body")

    generator = _require_generator()
    ready = bool(rag_engine and rag_engine.is_initialized)

    lang = req.language or detect_language(raw)
    eq = translate_to_english(raw, lang) if lang != "en" else raw
    return {
        "categorization": generator.categorize_ticket(eq),
        "retrieval_analysis": rag_engine.analyze_query(eq) if ready else {},
        "similar_tickets": rag_engine.get_similar_tickets(eq) if ready else [],
        "language": lang,
        "language_name": get_language_name(lang),
        "english_query": eq,
    }
