"""
FastAPI Backend — AI Customer Support System
Serves index.html and all REST endpoints.
Start with: uvicorn api:app --reload --port 8000
Then open:  http://localhost:8000
"""

import os
import shutil
import json as _json
import tempfile
import asyncio
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, Response
from pydantic import BaseModel

from src.config import Config
from src.data_loader import DataLoader
from src.rag_engine import RAGEngine
from src.response_generator import ResponseGenerator, FeedbackLoop
from src.db import MongoDBClient
from src.email_service import EmailService
from src.translator import detect_language, translate_to_english, translate_from_english, get_language_name
from src.voice_input import transcribe_audio, get_language_code_for_speech

# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="AI Customer Support API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Global singletons ───────────────────────────────────────────────────────

rag_engine: Optional[RAGEngine] = None
response_generator: Optional[ResponseGenerator] = None
feedback_loop: Optional[FeedbackLoop] = None
db: Optional[MongoDBClient] = None
email_service: Optional[EmailService] = None


@app.on_event("startup")
async def startup():
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
    mongo_ok = db is not None and db._client is not None

    # The frontend shows d.status as the chip text
    if rag_ok:
        status_text = f"Online · {docs_indexed} docs"
    else:
        status_text = "Degraded — RAG not ready"

    return {
        "status": status_text,
        "rag_initialized": rag_ok,
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
    if not rag_engine or not rag_engine.is_initialized:
        raise HTTPException(503, "RAG engine not ready. Check your API keys and restart.")

    raw_query = req.issue or req.query or ""
    if not raw_query.strip():
        raise HTTPException(400, "Provide 'issue' in request body")

    lang = req.language or detect_language(raw_query)
    english_query = translate_to_english(raw_query, lang) if lang != "en" else raw_query

    # Generate self-help text
    steps_en = response_generator.generate_self_help(english_query)

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
def create_ticket(req: TicketRequest):
    """
    Create a ticket (no screenshot). Frontend expects ticket_id in response.
    """
    lang = req.language or detect_language(req.issue_description)
    english_issue = (
        translate_to_english(req.issue_description, lang)
        if lang != "en"
        else req.issue_description
    )

    categorization = response_generator.categorize_ticket(english_issue)
    # Allow frontend-supplied category/priority to override LLM if provided
    category = req.category or categorization.get("category", "General Inquiry")
    priority = (req.priority or categorization.get("priority", "medium")).lower()

    ai_response_en = response_generator.generate_response(english_issue)
    ai_response = translate_from_english(ai_response_en, lang) if lang != "en" else ai_response_en

    ticket_data = {
        "user_name": req.user_name,
        "user_email": req.user_email,
        "issue_description": req.issue_description,
        "category": category,
        "priority": priority,
        "sentiment": categorization.get("sentiment", "neutral"),
        "summary": categorization.get("summary", ""),
        "ai_response": ai_response,
        "attempt_history": req.attempt_history or [],
        "language": lang,
    }

    ticket_id = "TKT-OFFLINE-0001"
    if db:
        try:
            ticket_id = db.save_ticket(ticket_data)
        except Exception as e:
            print(f"WARNING: MongoDB save failed — {e}")

    _send_emails(ticket_id, ticket_data, ai_response_en, screenshot_path=None)

    return {
        "ticket_id": ticket_id,
        "category": category,
        "priority": priority,
        "sentiment": categorization.get("sentiment", "neutral"),
        "ai_response": ai_response,
        "language": lang,
        "email_sent": email_service._is_configured() if email_service else False,
    }


# ─── Create ticket with screenshot (multipart) ───────────────────────────────

@app.post("/tickets/with-screenshot")
async def create_ticket_with_screenshot(
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
    screenshot_path = None
    if screenshot and screenshot.filename:
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)
        screenshot_path = os.path.join(upload_dir, screenshot.filename)
        with open(screenshot_path, "wb") as f:
            shutil.copyfileobj(screenshot.file, f)

    try:
        history = _json.loads(attempt_history)
    except Exception:
        history = []

    lang = language or detect_language(issue_description)
    english_issue = translate_to_english(issue_description, lang) if lang != "en" else issue_description

    categorization = response_generator.categorize_ticket(english_issue)
    final_category = category or categorization.get("category", "General Inquiry")
    final_priority = (priority or categorization.get("priority", "medium")).lower()

    ai_response_en = response_generator.generate_response(english_issue)
    ai_response = translate_from_english(ai_response_en, lang) if lang != "en" else ai_response_en

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
        "attempt_history": history,
        "language": lang,
    }

    ticket_id = "TKT-OFFLINE-0001"
    if db:
        try:
            ticket_id = db.save_ticket(ticket_data)
        except Exception as e:
            print(f"WARNING: MongoDB save failed — {e}")

    _send_emails(ticket_id, ticket_data, ai_response_en, screenshot_path)

    return {
        "ticket_id": ticket_id,
        "category": final_category,
        "priority": final_priority,
        "sentiment": categorization.get("sentiment", "neutral"),
        "ai_response": ai_response,
        "language": lang,
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
    audio_bytes = await audio.read()
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


async def _text_to_mp3(text: str, lang: str) -> bytes:
    """Convert text to WAV bytes using pyttsx3 (fully offline, no API needed).
    Returns WAV audio — browsers handle it fine via Audio()."""
    import pyttsx3
    import tempfile
    import os

    clean = _clean_for_tts(text)
    if not clean:
        raise RuntimeError("Empty TTS text")

    tmp_path = tempfile.mktemp(suffix=".wav")
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        engine.setProperty("volume", 1.0)
        # Pick female voice (index 1 = Zira on Windows) if available
        voices = engine.getProperty("voices")
        if len(voices) > 1:
            engine.setProperty("voice", voices[1].id)
        engine.save_to_file(clean, tmp_path)
        engine.runAndWait()
        with open(tmp_path, "rb") as f:
            return f.read()
    except Exception as e:
        raise RuntimeError(f"pyttsx3 TTS failed: {e}") from e
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


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
    if not rag_engine or not rag_engine.is_initialized:
        raise HTTPException(503, "RAG engine not ready")

    audio_bytes = await audio.read()
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
    steps_en = response_generator.generate_self_help(english_query)
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
    except Exception:
        return []


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
    if not raw:
        raise HTTPException(400, "Provide 'issue' in request body")
    lang = req.language or detect_language(raw)
    eq = translate_to_english(raw, lang) if lang != "en" else raw
    return {
        "categorization": response_generator.categorize_ticket(eq),
        "retrieval_analysis": rag_engine.analyze_query(eq) if rag_engine else {},
        "similar_tickets": rag_engine.get_similar_tickets(eq) if rag_engine else [],
        "language": lang,
    }
