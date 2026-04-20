# System Architecture

This document describes the architecture of the AI Customer Support Agent System — its layers, components, data flows, and design decisions.

---

## Table of Contents

1. [High-Level Overview](#1-high-level-overview)
2. [Layer Architecture](#2-layer-architecture)
3. [Component Breakdown](#3-component-breakdown)
4. [Data Flow Diagrams](#4-data-flow-diagrams)
5. [Storage Architecture](#5-storage-architecture)
6. [RAG Pipeline Deep Dive](#6-rag-pipeline-deep-dive)
7. [Multilingual Pipeline](#7-multilingual-pipeline)
8. [Voice Processing Pipeline](#8-voice-processing-pipeline)
9. [Email Notification Architecture](#9-email-notification-architecture)
10. [Startup & Initialization Flow](#10-startup--initialization-flow)
11. [Error Handling Strategy](#11-error-handling-strategy)
12. [Design Decisions & Trade-offs](#12-design-decisions--trade-offs)

---

## 1. High-Level Overview

The system is a **three-tier web application** with an AI processing layer embedded in the backend:

```
┌─────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                    │
│                                                         │
│   index.html (Customer)      app.py (Agent/Admin)       │
│   Vanilla JS + HTML          Streamlit                  │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP (REST)
┌──────────────────────▼──────────────────────────────────┐
│                    APPLICATION LAYER                     │
│                                                         │
│              api.py (FastAPI + Uvicorn)                 │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ RAG Engine  │  │  Response    │  │  Translator   │  │
│  │  + FAISS    │  │  Generator   │  │  + LangDetect │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  LLM Client │  │  Embeddings  │  │  Voice Input  │  │
│  │  (Groq)     │  │  (Gemini)    │  │  (Whisper)    │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
└──────────┬──────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────┐
│                    PERSISTENCE LAYER                     │
│                                                         │
│   MongoDB             FAISS (disk)       uploads/       │
│   (tickets,           (faiss_index.bin,  (screenshots)  │
│    feedback,          metadata.pkl)                     │
│    knowledge_base)                                      │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Layer Architecture

### Presentation Layer

Two independent UIs serve different audiences:

| Interface | File | Technology | Audience |
|-----------|------|-----------|----------|
| Customer Portal | `index.html` | HTML + Vanilla JS | End customers |
| Admin Dashboard | `app.py` | Python + Streamlit | Support agents, admins |

Both communicate exclusively through the REST API — neither has direct database or AI access.

### Application Layer

`api.py` is the single application server. It:
- Serves the HTML frontend statically
- Exposes all REST endpoints
- Owns all business logic routing
- Manages singleton instances of all AI components

All AI components are initialized once at startup and shared across requests (thread-safe for read operations):

```python
# api.py — global singletons
rag_engine: RAGEngine
response_generator: ResponseGenerator
feedback_loop: FeedbackLoop
db: MongoDBClient | None
email_service: EmailService | None
```

### Persistence Layer

Three storage systems, each with a distinct role:

| Storage | Technology | Data |
|---------|-----------|------|
| Document Store | MongoDB | Tickets, feedback, knowledge base |
| Vector Index | FAISS (file) | Embeddings for semantic search |
| File Store | Local filesystem | Screenshot uploads |

MongoDB and file storage are optional — the system degrades gracefully when unavailable.

---

## 3. Component Breakdown

### src/config.py — Central Configuration

Single source of truth for all constants, model names, thresholds, and system prompts. Loaded once at import time from environment variables.

```
.env → Config class → all other modules
```

Key configuration groups:
- API keys and model names
- Vector store settings (dimensions, chunk size, threshold)
- Ticket categories and priority SLAs
- System prompts for each LLM call type

### src/embeddings.py — Embedding Engine

Wraps the Google Gemini Embedding API (`models/gemini-embedding-001`):

- Produces 3072-dimensional float vectors
- Uses task-type hints: `retrieval_document` for indexing, `retrieval_query` for search
- Adds 50–100ms rate limiting between batch calls to respect quota

### src/vector_store.py — FAISS Index

FAISS (`IndexFlatIP` wrapped with `IndexIDMap`):

- `IndexFlatIP` = exact inner product search (equivalent to cosine similarity on normalized vectors)
- All vectors are L2-normalized before insertion and before search
- `IndexIDMap` maps FAISS integer IDs to document string IDs
- Persisted as two files: binary index + Python pickle metadata

### src/rag_engine.py — RAG Orchestration

Coordinates embeddings → vector store → retrieval:

```python
class RAGEngine:
    embeddings: GeminiEmbeddings
    vector_store: FAISSVectorStore

    def retrieve(query) → [(doc, score)]
    def get_context(query) → str  # for LLM prompt injection
    def analyze_query(query) → stats dict
```

Three initialization paths:
1. From document list (fresh build)
2. From MongoDB knowledge_base collection
3. From disk (warm start, fastest)

### src/llm_client.py — LLM Abstraction

Thin wrapper over the Groq Python SDK:

```python
class GroqClient:
    def generate(prompt) → str
    def generate_with_system(system_prompt, user_message) → str
```

Separates LLM provider from business logic. Could swap Groq for OpenAI/Anthropic by replacing this module only.

### src/response_generator.py — Business Logic Hub

The most complex module. Orchestrates multiple AI calls into coherent output:

```
categorize_ticket()         → Groq (temp=0.1, deterministic)
generate_self_help()        → RAG context + Groq (temp=0.7)
generate_response()         → RAG context + Groq (temp=0.7)
generate_multiple_responses() → 3× Groq calls (temp=0.3, 0.7, 1.0)
improve_response()          → Groq with feedback prompt (temp=0.7)
generate_with_analysis()    → Full pipeline: lang→translate→categorize→RAG→respond→translate
```

### src/translator.py — Language Layer

Stateless translation utilities:

```
langdetect → detect language code
deep-translator (Google Translate) → translate without API key
```

All translation is transparent — callers pass text in any language, receive text back in the same language.

### src/voice_input.py — STT

Wraps Groq Whisper API:
- Input: raw audio bytes (webm)
- Output: transcribed string
- Supports BCP-47 language codes for improved accuracy

### src/db.py — MongoDB Abstraction

Three collections with defined schemas:

```
tickets → { ticket_id, user_name, user_email, issue_description,
            category, priority, sentiment, summary, ai_response,
            screenshot_path, attempt_history, language, status,
            created_at, updated_at }

knowledge_base → { id, instruction, response, category, combined_text }

feedback → { query, original_response, feedback, rating,
             improved_response, created_at }
```

Ticket IDs use date-based sequential format: `TKT-20260420-0042`

### src/email_service.py — SMTP Layer

HTML email generation using Python's `smtplib` and `email.mime`:

```
Customer email: confirmation + AI response + SLA
Developer email: full ticket details + optional screenshot attachment
```

Both templates are hardcoded HTML with inline CSS (email clients don't support external stylesheets).

---

## 4. Data Flow Diagrams

### Self-Help Request

```
Browser → POST /self-help
              │
              ▼
         detect_language(issue)
              │
              ▼
         translate_to_english(issue)
              │
              ▼
         rag_engine.get_context(english_issue, top_k=3)
              │
              ▼
         groq.generate_with_system(
             system=Config.SYSTEM_PROMPTS["self_help"],
             user=context + english_issue
         )
              │
              ▼
         parse numbered steps (regex: "^\\d+\\.")
              │
              ▼
         translate_from_english(response, original_lang)
              │
              ▼
         Return JSON { response, steps[], language }
```

### Ticket Creation

```
Browser → POST /tickets
              │
              ▼
         detect_language(issue_description)
              │
              ▼
         translate_to_english(issue_description)
              │
              ▼
         ┌───────────┬──────────────────────┐
         │           │                      │
         ▼           ▼                      ▼
   categorize   generate_response      (parallel)
   _ticket()    with RAG context
         │           │
         └─────┬─────┘
               │
               ▼
         translate_from_english(ai_response)
               │
               ▼
         db.save_ticket(ticket_dict)
               │
               ├──► email_service.send_customer_confirmation()
               └──► email_service.send_developer_alert()
               │
               ▼
         Return JSON { ticket_id, category, priority, ai_response }
```

### Voice Chat

```
Browser → POST /voice-chat (audio bytes)
              │
              ▼
         transcribe_audio(audio_bytes)  [Groq Whisper]
              │
              ▼
         detect_language(transcript)
              │
              ▼
         translate_to_english(transcript)
              │
              ▼
         generate_self_help(english_text)  [RAG + Groq]
              │
              ▼
         translate_from_english(response, original_lang)
              │
              ▼
         strip_markdown(response_text)
              │
              ▼
         pyttsx3.say(clean_text) → WAV bytes
              │
              ▼
         StreamingResponse(wav_bytes, media_type="audio/wav")
         Headers: X-Transcript, X-Response-Text, X-Language
```

---

## 5. Storage Architecture

### MongoDB Collections

```
customer_support (database)
├── tickets (collection)
│   ├── Sequential ticket IDs: TKT-YYYYMMDD-NNNN
│   ├── Full ticket metadata + AI outputs
│   └── Index on: ticket_id, user_email, created_at
│
├── knowledge_base (collection)
│   ├── Historical support Q&A pairs
│   ├── Loaded from CSV or manual import
│   └── Cleared and rebuilt on --force-rebuild
│
└── feedback (collection)
    ├── Query + response + user feedback + improved response
    └── Append-only, never modified
```

### FAISS Index Files

```
vector_store/
├── faiss_index.bin   (binary, ~40MB for 2500 docs × 3072 dims × 4 bytes)
└── metadata.pkl      (Python pickle: list of document dicts + config)
```

The metadata pickle stores:
- All document dicts (for retrieval results)
- Embedding dimensions (for validation on load)
- Document count

### File Uploads

```
uploads/
└── {timestamp}_{original_filename}   (e.g., 1713600000_error_screenshot.png)
```

Files are never deleted automatically. A cleanup cron job or manual purge is recommended for production.

---

## 6. RAG Pipeline Deep Dive

### Embedding Model Choice

**Google Gemini `models/gemini-embedding-001`** was chosen for:
- 3072 dimensions (highest semantic density of tested models)
- Separate task-type hints for query vs. document embedding
- Free tier with reasonable quota for initial builds
- Strong multilingual coverage

### Indexing Strategy

```python
# Normalization before FAISS insertion
embedding = embedding / np.linalg.norm(embedding)
faiss_index.add(normalized_embedding)
```

Normalization converts dot product (IndexFlatIP) to cosine similarity. This is equivalent to `IndexFlatL2` on normalized vectors but uses fewer operations.

### Retrieval Scoring

```python
scores, ids = index.search(query_embedding, top_k)
# Filter by similarity threshold
results = [(doc, score) for doc, score in zip(docs, scores) if score >= threshold]
```

Default threshold: `0.5` (50% cosine similarity). Below this, results are considered too dissimilar to be useful context.

### Context Formatting

Retrieved documents are formatted into a single context string:

```
Relevant Case 1 (Similarity: 0.91):
Customer Query: App crashes on upload
Support Response: This is a known issue...

Relevant Case 2 (Similarity: 0.84):
Customer Query: File upload error appears
Support Response: Please ensure file size...
```

This context is prepended to the LLM system prompt before generating a response.

---

## 7. Multilingual Pipeline

```
Input text (unknown language)
    │
    ▼
langdetect.detect() → ISO 639-1 code
    │
    ├── 'en' → skip translation (pass-through)
    │
    └── other → GoogleTranslator(source=lang, target='en').translate(text)
                    │
                    ▼
              [English processing]
                    │
                    ▼
              GoogleTranslator(source='en', target=original_lang).translate(response)
```

The `deep-translator` library uses the Google Translate web API without requiring an API key. It has a soft limit of ~5000 chars per request; longer texts are split automatically.

---

## 8. Voice Processing Pipeline

### STT (Speech-to-Text)

```python
# src/voice_input.py
groq_client.audio.transcriptions.create(
    file=("audio.webm", audio_bytes, "audio/webm"),
    model="whisper-large-v3-turbo",
    language=bcp47_code,  # e.g., "en-US"
    response_format="text"
)
```

Groq Whisper runs on dedicated hardware; latency is typically 2–5 seconds regardless of audio length.

### TTS (Text-to-Speech)

```python
# api.py — voice-chat endpoint
engine = pyttsx3.init()
engine.setProperty('rate', 150)      # words per minute
engine.setProperty('volume', 0.9)
engine.save_to_file(clean_text, temp_wav_path)
engine.runAndWait()
```

pyttsx3 uses Windows SAPI (on Windows) or espeak (on Linux). This is fully offline — no API call, no network dependency, no latency from inference.

The output is WAV format. Browsers play this natively via `<audio>` elements.

---

## 9. Email Notification Architecture

### SMTP Configuration

```python
# src/email_service.py
with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
    server.login(gmail_address, app_password)
    server.send_message(msg)
```

Port 465 with SSL (not STARTTLS) is used for reliability. Gmail App Passwords are required because regular password auth is disabled for Gmail accounts with 2FA.

### Email Template Structure

**Customer email:**
```
[Blue header: "Support Request Received"]
Ticket ID: TKT-YYYYMMDD-NNNN
Category: Billing
Priority: HIGH (Expected resolution: 8 hours)

Our initial response:
[AI-generated response text]

Our team will follow up if needed.
```

**Developer email:**
```
[Red header: "New Support Ticket - Action Required"]
Ticket: TKT-YYYYMMDD-NNNN | Priority: HIGH | Sentiment: NEGATIVE
Customer: Jane Doe <jane@example.com>
Category: Billing
Issue: [Full issue description]
Prior attempts: [Attempt history if provided]
AI Response: [For review/modification]
[Screenshot attachment if provided]
```

---

## 10. Startup & Initialization Flow

### api.py Startup

```python
@app.on_event("startup")
async def startup_event():
    # 1. Validate API keys
    config = Config()

    # 2. Initialize embeddings + vector store
    rag_engine = RAGEngine()

    # 3. Try to load from disk (fast path)
    if vector_store_path exists:
        rag_engine.load_from_disk(vector_store_path)
    else:
        # Load CSV → preprocess → embed → index → save
        df, documents = load_and_prepare_data(data_path)
        rag_engine.initialize_from_documents(documents)
        rag_engine.save_to_disk(vector_store_path)

    # 4. Initialize response generator
    response_generator = ResponseGenerator(rag_engine)
    feedback_loop = FeedbackLoop(response_generator)

    # 5. Optional services (non-blocking)
    try:
        db = MongoDBClient()
    except:
        db = None  # graceful degradation

    try:
        email_service = EmailService()
    except:
        email_service = None
```

Total cold start: 30–90 seconds (dominated by Gemini embedding API calls)
Warm start: < 2 seconds

---

## 11. Error Handling Strategy

### Principle: Graceful Degradation

Services fail independently without bringing down the whole system:

| Failure | Impact | Behavior |
|---------|--------|----------|
| MongoDB unavailable | Tickets not persisted | Returns success; `email_sent=false` |
| Gmail not configured | No emails sent | Returns success; `email_sent=false` |
| Translation failure | Non-English response | Returns original text |
| Language detection failure | Defaults to English | Proceeds with English pipeline |
| Groq rate limit | LLM call fails | Returns 500 with error message |
| FAISS load failure | No RAG context | LLM responds without context |

### Feedback Fallback

If MongoDB is unavailable, feedback is stored in an in-memory list:

```python
# src/response_generator.py — FeedbackLoop
self.feedback_history: list[dict] = []  # fallback when db is None
```

### Ticket ID Fallback

If MongoDB is unavailable and sequential IDs can't be fetched, the system generates a UUID-based fallback:

```python
ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"
```

---

## 12. Design Decisions & Trade-offs

### Why Groq instead of OpenAI?

- Groq's free tier is significantly more generous
- Llama 3.3 70B via Groq outperforms GPT-3.5 on instruction following
- Lower latency due to LPU (Language Processing Unit) hardware
- No vendor lock-in: model can be swapped in `llm_client.py`

### Why FAISS instead of a vector database (Pinecone, Weaviate)?

- Zero infrastructure — no external service, no account needed
- Sub-5ms retrieval for datasets up to ~1M vectors
- Disk-persisted — survives server restarts
- For datasets > 100K docs, a managed vector DB would be preferred

### Why pyttsx3 instead of a cloud TTS (ElevenLabs, Google TTS)?

- Fully offline — no API key, no quota, no cost
- Acceptable for support use cases (clarity over voice quality)
- Cloud TTS would add latency and API dependency to every voice request

### Why deep-translator instead of Google Cloud Translation API?

- No API key required (uses the web interface)
- Identical translation quality for the languages tested
- Cloud API preferred for production due to reliability guarantees and SLA

### Why MongoDB instead of PostgreSQL?

- Flexible schema — ticket metadata fields may vary over time
- Native JSON storage — no ORM overhead
- GridFS available for large file storage if needed
- Easier horizontal scaling for write-heavy workloads

### Why Streamlit for the admin dashboard?

- Rapid development for data-heavy interfaces
- Built-in support for charts, tables, audio recording
- Python-native — no context switching between frontend/backend code
- Not suitable for high-concurrent production (session state is per-user)
