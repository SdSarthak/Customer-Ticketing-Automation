# Tech Stack

This document covers every technology used in the AI Customer Support Agent System — what it is, why it was chosen, how it's used, and what trade-offs were considered.

---

## Table of Contents

1. [Stack Summary](#1-stack-summary)
2. [AI & Machine Learning](#2-ai--machine-learning)
3. [Backend Framework](#3-backend-framework)
4. [Frontend](#4-frontend)
5. [Vector Database](#5-vector-database)
6. [Database & Persistence](#6-database--persistence)
7. [Email & Notifications](#7-email--notifications)
8. [Voice & Audio](#8-voice--audio)
9. [Multilingual & NLP](#9-multilingual--nlp)
10. [Data Processing](#10-data-processing)
11. [Testing](#11-testing)
12. [Configuration & Environment](#12-configuration--environment)
13. [Dependency Summary](#13-dependency-summary)
14. [Infrastructure & Deployment](#14-infrastructure--deployment)

---

## 1. Stack Summary

```
┌──────────────────────────────────────────────────────────┐
│                        AI LAYER                          │
│                                                          │
│  Groq (Llama 3.3 70B)    Google Gemini Embeddings        │
│  Groq Whisper STT        pyttsx3 TTS                     │
└──────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────┐
│                     BACKEND LAYER                        │
│                                                          │
│  FastAPI + Uvicorn       Python 3.9+                     │
│  FAISS (vector search)   MongoDB (persistence)           │
└──────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────┐
│                    FRONTEND LAYER                        │
│                                                          │
│  HTML + Vanilla JS        Streamlit (admin)              │
│  (customer portal)        (agent dashboard)              │
└──────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────┐
│                 LANGUAGE & TRANSLATION                   │
│                                                          │
│  langdetect              deep-translator (Google)        │
└──────────────────────────────────────────────────────────┘
```

---

## 2. AI & Machine Learning

### Google Gemini — Embedding Model

**Package:** `google-generativeai==0.3.2`  
**Model:** `models/gemini-embedding-001`  
**Version used:** API v1

**What it does:** Converts text into 3072-dimensional dense floating-point vectors that encode semantic meaning. Similar texts produce vectors close together in vector space.

**Why Gemini:**
- 3072-dimensional output — highest density of tested free-tier embedding models
- Task-type API parameter allows separate optimization for indexing (`retrieval_document`) vs. search (`retrieval_query`)
- Strong multilingual support — single model handles 100+ languages
- Free tier sufficient for building and rebuilding the index
- Outperforms `text-embedding-ada-002` (1536-dim) and `text-embedding-3-small` (1536-dim) on semantic retrieval benchmarks

**Alternatives considered:**

| Model | Dimensions | Notes |
|-------|-----------|-------|
| OpenAI ada-002 | 1536 | Paid, good quality |
| OpenAI text-embedding-3-large | 3072 | Paid, similar quality |
| Sentence-Transformers all-MiniLM-L6 | 384 | Free, local, lower quality |
| Cohere embed-v3 | 1024 | Paid |

**Trade-offs:**
- Requires network call per document during index build (rate-limited to ~0.05s between calls)
- Not suitable for real-time re-indexing of individual documents

---

### Groq — Large Language Model

**Package:** `groq==0.9.0`  
**Model:** `llama-3.3-70b-versatile`  
**API:** Groq Cloud (free tier)

**What it does:** Powers all text generation: self-help steps, ticket categorization, response generation, and feedback improvement.

**Why Groq:**
- **Speed:** Groq's LPU (Language Processing Unit) achieves 100–200 tokens/second vs. ~30–50 on GPU-based APIs
- **Free tier:** Generous request quota on free plan, sufficient for development and moderate production load
- **Model quality:** Llama 3.3 70B matches GPT-4-class performance on instruction-following tasks
- **No vendor lock-in:** The LLM client module can swap Groq for any OpenAI-compatible API

**Model configuration:**

| Use case | Temperature | Tokens |
|----------|------------|--------|
| Ticket categorization | 0.1 | 512 |
| Self-help generation | 0.7 | 1024 |
| Response generation | 0.7 | 1024 |
| Conservative candidate | 0.3 | 1024 |
| Creative candidate | 1.0 | 1024 |
| Feedback improvement | 0.7 | 1024 |

**Temperature rationale:**
- `0.1` for classification — near-deterministic output needed for JSON parsing reliability
- `0.7` for generation — balance between coherence and naturalness
- `1.0` for creative candidate — more verbose, empathetic, personalized

**Alternatives considered:**

| Provider | Model | Notes |
|----------|-------|-------|
| OpenAI | GPT-4o | Paid, high quality, higher latency |
| Anthropic | Claude 3 Haiku | Paid, good instruction following |
| Google | Gemini 1.5 Flash | Free tier available, tested but slower |
| Ollama | llama3.2 | Local, no cost, requires GPU |

---

### Groq Whisper — Speech-to-Text

**Via Groq SDK**  
**Model:** `whisper-large-v3-turbo`

**What it does:** Transcribes audio files to text. Used in the `/transcribe` and `/voice-chat` endpoints.

**Why Groq Whisper:**
- Same API key as the LLM (single credential)
- Significantly faster than OpenAI's Whisper API (Groq LPU acceleration)
- No quota issues on free tier for development
- Supports 30+ languages with BCP-47 language hints

**Input format:** webm audio (from browser MediaRecorder API), also supports wav, mp3, m4a

**Alternatives considered:**

| Option | Notes |
|--------|-------|
| OpenAI Whisper API | Paid, good quality, slower |
| local whisper (openai-whisper) | Free, requires ~1.5GB GPU VRAM |
| Google Speech-to-Text | Paid, best accuracy |
| SpeechRecognition (Google Web) | Free, limited accuracy, no file upload |

---

### pyttsx3 — Text-to-Speech

**Package:** `pyttsx3` (pinned to latest compatible)

**What it does:** Converts AI-generated response text to spoken WAV audio.

**Why pyttsx3:**
- Fully offline — no API key, no network call, no quota
- Windows SAPI integration for natural-sounding voices
- Zero-latency overhead beyond compute time
- Acceptable voice quality for support context

**Voice settings:**
```python
engine.setProperty('rate', 150)    # 150 words per minute
engine.setProperty('volume', 0.9)  # 90% volume
```

**Preprocessing applied:** Markdown stripped before TTS to avoid reading `**bold**` or `### headers` literally.

**Alternatives considered:**

| Option | Notes |
|--------|-------|
| edge-tts (Microsoft) | Better voice quality, requires internet |
| Google Cloud TTS | Highest quality, paid, API key required |
| ElevenLabs | Best quality, paid, expensive at scale |
| gTTS | Free, requires internet, slow |

---

## 3. Backend Framework

### FastAPI

**Package:** `fastapi==0.109.0`  
**Server:** `uvicorn==0.27.0`

**What it does:** Provides all REST API endpoints. Serves the static HTML frontend. Manages startup lifecycle (initializing AI components).

**Why FastAPI:**
- **Performance:** ASGI-based, async-native — handles concurrent requests without blocking
- **Auto-docs:** Swagger UI available at `/docs`, ReDoc at `/redoc` — no manual API documentation maintenance
- **Pydantic validation:** Request/response schemas validated automatically
- **Python ecosystem:** Direct imports of all AI/ML libraries without serialization layer
- **Background tasks:** Built-in `BackgroundTasks` for async email sending

**ASGI server — Uvicorn:**
- Production-grade ASGI server
- `--reload` flag for development hot-reload
- Single worker sufficient for development; use `--workers 4` for production

**Alternatives considered:**

| Framework | Notes |
|-----------|-------|
| Flask | Synchronous, lower performance, no auto-docs |
| Django | Heavy, overkill for this scope |
| Tornado | Lower-level, more boilerplate |
| Starlette | FastAPI is built on Starlette; FastAPI adds validation layer |

---

### Streamlit

**Package:** `streamlit==1.29.0`

**What it does:** Powers the admin dashboard for support agents. Provides interactive UI with minimal frontend code.

**Why Streamlit:**
- Python-native — no JavaScript, no HTML templates
- Built-in components: chat interface, file uploader, audio recorder, tables
- Session state management for multi-step interactions
- Fast to build and iterate
- Free to deploy on Streamlit Cloud

**Limitations:**
- Session state is per-user, per-browser tab (not suitable for multi-agent coordination)
- Not suitable for high-traffic customer-facing use
- Single-threaded execution model limits concurrent users

---

## 4. Frontend

### HTML + Vanilla JavaScript (index.html)

**No framework used** — plain HTML5 with CSS and JavaScript.

**Why no framework (React/Vue/Angular):**
- No build pipeline needed
- Single file deployable as a static asset
- Served directly by FastAPI's `StaticFiles`
- Sufficient complexity for the customer portal's scope

**Browser APIs used:**
- `fetch` API for REST calls
- `MediaRecorder` API for audio recording
- `AudioContext` for WAV playback
- `FormData` for multipart file uploads

---

## 5. Vector Database

### FAISS (Facebook AI Similarity Search)

**Package:** `faiss-cpu==1.7.3`

**What it does:** Stores 3072-dimensional embeddings in a flat index and answers approximate (or exact) nearest-neighbor queries in milliseconds.

**Index type:** `IndexFlatIP` (Inner Product) with `IndexIDMap` wrapper

**Why IndexFlatIP:**
- Exact search — no approximation error (important for correctness in support context)
- Inner product on normalized vectors = cosine similarity
- For datasets < 1M vectors, `IndexFlatIP` is fast enough (<5ms per query)

**Why not HNSW or IVF:**
- Approximate indexes trade accuracy for speed — not needed at this scale
- `IndexFlatIP` is exact and still sub-millisecond for 2500 docs

**Persistence:**
```
vector_store/
├── faiss_index.bin     (~40MB for 2500 × 3072 float32 vectors)
└── metadata.pkl        (document metadata + config)
```

**Why not a managed vector database:**

| Option | Notes |
|--------|-------|
| Pinecone | Managed, paid, serverless |
| Weaviate | Self-hosted or cloud, more features |
| Qdrant | Self-hosted, production-grade |
| ChromaDB | Embedded, easier than FAISS but slower |
| pgvector | PostgreSQL extension |

FAISS was chosen for zero infrastructure, zero cost, and sufficient performance at this scale. A managed vector DB would be preferred for multi-tenant production deployments.

---

## 6. Database & Persistence

### MongoDB

**Package:** `pymongo==4.6.1`  
**Default URI:** `mongodb://localhost:27017`  
**Database:** `customer_support`

**Collections:**

| Collection | Purpose | Schema |
|-----------|---------|--------|
| `tickets` | Support ticket records | See [architecture.md](architecture.md) |
| `knowledge_base` | RAG source documents | id, instruction, response, combined_text |
| `feedback` | User feedback + improvements | query, original, feedback, improved |

**Why MongoDB:**
- Flexible document schema — ticket fields vary (optional screenshot, language, attempt history)
- JSON-native storage — direct dict → document mapping with no ORM
- Easy horizontal scaling (sharding) for write-heavy workloads
- Atlas cloud tier available for zero-ops deployment

**Alternatives considered:**

| Option | Notes |
|--------|-------|
| PostgreSQL | Strong consistency, ACID, requires ORM for complex queries |
| SQLite | Zero-config, not suitable for concurrent writes |
| Redis | In-memory, good for caching but not primary storage |
| DynamoDB | AWS-native, managed, pay-per-use |

---

## 7. Email & Notifications

### Gmail SMTP

**Library:** Python built-in `smtplib` + `email.mime`  
**Port:** 465 (SSL)  
**Authentication:** App Password (not account password)

**Why Gmail SMTP:**
- No additional service needed — uses existing Gmail account
- App Passwords enable programmatic access without OAuth complexity
- HTML email support for rich ticket notifications
- Free tier: 500 emails/day

**Gmail App Password requirements:**
1. Google Account 2-Factor Authentication enabled
2. App Password generated: Google Account → Security → App Passwords

**Email features used:**
- `MIMEMultipart('alternative')` — HTML + plain text fallback
- `MIMEBase` + `encoders.encode_base64()` — screenshot attachment
- SSL context for secure transmission

**Alternatives considered:**

| Option | Notes |
|--------|-------|
| SendGrid | Paid (free tier limited), better deliverability |
| Mailgun | Paid, reliable API |
| Amazon SES | Cheap at scale, AWS dependency |
| SMTP Relay (Postfix) | Self-hosted, complex setup |

---

## 8. Voice & Audio

### Audio Recording (Browser)

**API:** `MediaRecorder` (native browser API)  
**Format:** WebM with Opus codec  
**Streamlit component:** `audio-recorder-streamlit==0.0.8` (admin dashboard)

### Groq Whisper (see Section 2)

### pyttsx3 (see Section 2)

### Audio Format Flow

```
Browser: MediaRecorder → WebM (Opus codec)
    │
    ▼
FastAPI: receives as UploadFile bytes
    │
    ▼
Groq Whisper: processes webm natively
    │
    ▼
pyttsx3: generates WAV output
    │
    ▼
Browser: AudioContext.decodeAudioData() → plays WAV
```

---

## 9. Multilingual & NLP

### langdetect

**Package:** `langdetect==1.0.9`  
**Source:** Port of Google's language-detection library

**What it does:** Identifies the language of input text with a confidence score. Returns ISO 639-1 language codes (`'en'`, `'hi'`, `'fr'`, etc.).

**Accuracy:** 99%+ for texts > 50 characters; less reliable for short inputs (< 20 characters).

**Why langdetect:**
- No API key required (fully offline)
- Fast (< 10ms per call)
- 55+ language support
- Probabilistic model with confidence scores

### deep-translator

**Package:** `deep-translator==1.11.4`  
**Backend used:** `GoogleTranslator`

**What it does:** Translates text between any two of 100+ supported languages using Google Translate's web interface (no API key).

**Why deep-translator:**
- No API key required
- Same translation quality as Google Cloud Translation API
- Automatic text chunking for long strings
- Multiple backend support (DeepL, Microsoft, Libre, etc.) if Google is unavailable

**Rate limiting:** Soft limit ~5000 chars/request; library handles chunking internally. No enforced quota but requests may be throttled on heavy use.

**Alternatives considered:**

| Option | Notes |
|--------|-------|
| Google Cloud Translation API | Official, paid, reliable |
| DeepL API | Better for European languages, paid |
| Helsinki-NLP MarianMT | Local, free, requires GPU for quality |
| googletrans | Unofficial, deprecated |

---

## 10. Data Processing

### pandas

**Package:** `pandas==2.1.4`

**Used for:**
- Loading the customer support CSV (`data/customer_support_tickets.csv`)
- Data cleaning: deduplication, null handling, text normalization
- Statistical analysis: record counts, missing values, category distributions

### numpy

**Package:** `numpy==1.26.2`

**Used for:**
- Embedding vector operations (L2 normalization, cosine similarity)
- FAISS array interfaces (requires float32 numpy arrays)
- Batch embedding concatenation

### tqdm

**Package:** `tqdm==4.66.1`

**Used for:** Progress bars during batch embedding operations. Users can monitor index build progress when processing thousands of documents.

---

## 11. Testing

### pytest

**Package:** `pytest` (via `pytest.ini`)  
**Test file:** `test_api.py`

**What it does:** Unit and integration testing for all FastAPI endpoints.

### FastAPI TestClient

**Via:** `fastapi.testclient.TestClient`

**What it does:** Simulates HTTP requests to the FastAPI app without starting a real server. Returns standard `requests.Response` objects.

### unittest.mock

**Via:** Python stdlib `unittest.mock`

**What it does:** Patches external dependencies (Groq, Gemini, MongoDB, Gmail) so tests run without real API keys or infrastructure.

**Mocked services:**
- `RAGEngine` — mocked with predefined retrieval results
- `ResponseGenerator` — mocked categorization and response generation
- `MongoDBClient` — mocked save/get operations
- `EmailService` — disabled entirely in tests
- Groq Whisper — mocked transcription output

**Test structure:**

| Class | Endpoints Covered |
|-------|------------------|
| `TestStatus` | `GET /status` |
| `TestSelfHelp` | `POST /self-help` |
| `TestTickets` | All `/tickets` routes |
| `TestTranscribe` | `POST /transcribe` |
| `TestVoiceChat` | `POST /voice-chat` |
| `TestFeedback` | `/feedback` routes |
| `TestAnalyze` | `POST /analyze` |
| `TestVoiceInputModule` | Language code mapping |
| `TestTTS` | Text preprocessing + audio generation |

**pytest.ini configuration:**

```ini
[pytest]
testpaths = .
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

---

## 12. Configuration & Environment

### python-dotenv

**Package:** `python-dotenv==1.0.0`

**What it does:** Loads `.env` file variables into `os.environ` at startup.

**Usage:**
```python
from dotenv import load_dotenv
load_dotenv()
```

Called once in `src/config.py` before any `os.getenv()` calls.

### python-multipart

**Package:** `python-multipart==0.0.9`

**What it does:** Required by FastAPI for `multipart/form-data` parsing (file uploads). Not directly imported — FastAPI uses it internally.

### aiofiles

**Package:** `aiofiles==23.2.1`

**What it does:** Async file I/O for saving uploaded screenshots without blocking the event loop.

---

## 13. Dependency Summary

| Package | Version | Category | Required |
|---------|---------|----------|----------|
| `streamlit` | 1.29.0 | Frontend | No (admin only) |
| `fastapi` | 0.109.0 | Backend | Yes |
| `uvicorn` | 0.27.0 | Backend | Yes |
| `google-generativeai` | 0.3.2 | AI — Embeddings | Yes |
| `groq` | 0.9.0 | AI — LLM + STT | Yes |
| `faiss-cpu` | 1.7.3 | Vector DB | Yes |
| `pandas` | 2.1.4 | Data | Yes |
| `numpy` | 1.26.2 | Data | Yes |
| `langdetect` | 1.0.9 | NLP | Yes |
| `deep-translator` | 1.11.4 | NLP | Yes |
| `SpeechRecognition` | 3.10.0 | Voice | No |
| `audio-recorder-streamlit` | 0.0.8 | Voice | No (admin only) |
| `edge-tts` | 6.1.12 | Voice | No |
| `pyttsx3` | latest | Voice | Yes (voice-chat) |
| `pymongo` | 4.6.1 | Database | No |
| `python-dotenv` | 1.0.0 | Config | Yes |
| `python-multipart` | 0.0.9 | Backend | Yes |
| `aiofiles` | 23.2.1 | Backend | Yes |
| `tqdm` | 4.66.1 | Utilities | No |
| `pytest` | latest | Testing | Dev only |

---

## 14. Infrastructure & Deployment

### Development Setup

```
Local machine
├── Python 3.9+ virtual environment
├── MongoDB (local instance or Docker)
├── FastAPI server: uvicorn api:app --reload --port 8000
└── Streamlit server: streamlit run app.py (optional)
```

### Production Recommendations

| Component | Development | Production |
|-----------|-------------|------------|
| ASGI server | `uvicorn --reload` | `uvicorn --workers 4` or `gunicorn -k uvicorn.workers.UvicornWorker` |
| MongoDB | Local MongoDB | MongoDB Atlas (M0 free tier or M10+) |
| Vector store | Local filesystem | Shared filesystem (EFS/NFS) or migrate to Qdrant |
| TLS | None | Nginx reverse proxy with Let's Encrypt |
| Secrets | `.env` file | AWS Secrets Manager / HashiCorp Vault |
| File uploads | Local `uploads/` | AWS S3 or Azure Blob Storage |
| Monitoring | Console logs | Prometheus + Grafana or DataDog |

### Containerization (suggested)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Environment Variables in Production

Never commit `.env` to version control. Use:
- Docker secrets
- Kubernetes Secrets
- AWS Secrets Manager
- Azure Key Vault

The `.env.example` file (committed) documents all required variables without values.
