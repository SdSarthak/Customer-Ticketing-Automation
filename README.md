# AI-Powered Customer Support Agent System

An intelligent, multilingual customer support platform powered by Retrieval-Augmented Generation (RAG), Large Language Models, and voice interaction capabilities. Built as a capstone project for 8th semester.

---

## Overview

This system automates and augments customer support operations by:

- **Self-resolving issues** before ticket creation using RAG-powered self-help steps
- **Classifying tickets** by category, priority, and sentiment automatically
- **Generating contextual responses** grounded in historical support data
- **Supporting 21+ languages** with automatic detection and translation
- **Enabling voice interactions** with speech-to-text and text-to-speech
- **Notifying stakeholders** via automated Gmail emails with SLA-based urgency

---

## Quick Start

### Prerequisites

- Python 3.9+
- API keys: Google Gemini (embeddings) and Groq (LLM + Whisper)
- MongoDB — optional, for ticket persistence and the admin queue
- Gmail account with an App Password — optional, for email notifications

### Installation

```bash
git clone https://github.com/SdSarthak/Customer-Ticketing-Automation.git
cd Customer-Ticketing-Automation

pip install -r requirements.txt

cp .env.example .env
# Edit .env and fill in GOOGLE_API_KEY and GROQ_API_KEY
```

### Running the System

```bash
# Build the FAISS index from the bundled dataset (first run only)
python main.py --setup

# Start the FastAPI backend — it also serves the web frontend
uvicorn api:app --reload --port 8000
# Visit: http://localhost:8000

# Streamlit dashboard for agents and administrators (optional)
streamlit run app.py
# Visit: http://localhost:8501

# CLI interactive mode
python main.py --interactive
```

The API degrades gracefully: if MongoDB is unreachable or a key is missing, the
server still boots and `GET /status` reports exactly which subsystem is down.

---

## Architecture at a Glance

```
User Request (Text / Voice)
        │
        ▼
  Language Detection & Translation (langdetect + deep-translator)
        │
        ▼
  Self-Help Generation ──► FAISS Vector Search ──► Groq LLM
        │
        ├──► Unhelpful? ──► Feedback Loop ──► Improved Response
        │
        ▼
  Issue Unresolved? ──► Ticket Creation
        │
        ▼
  Categorization + Priority + Sentiment (Groq Llama 3.3 70B)
        │
        ├──► MongoDB (persistence)
        ├──► Gmail (customer + developer notifications, sent in background)
        └──► Response Translation & Delivery
```

---

## Project Structure

```
.
├── main.py                     # CLI entry point
├── api.py                      # FastAPI REST backend (also serves index.html)
├── app.py                      # Streamlit admin dashboard
├── test_api.py                 # Endpoint + voice pipeline tests
├── test_src.py                 # Unit tests for the src/ modules
├── requirements.txt
├── .env.example
├── index.html                  # User-facing web frontend
├── pytest.ini
├── src/
│   ├── config.py               # Global configuration & system prompts
│   ├── data_loader.py          # CSV ingestion & preprocessing
│   ├── embeddings.py           # Google Gemini embeddings (3072-dim)
│   ├── vector_store.py         # FAISS vector database
│   ├── llm_client.py           # Groq LLM wrapper
│   ├── rag_engine.py           # RAG orchestration
│   ├── response_generator.py   # Response generation & feedback loop
│   ├── translator.py           # Multilingual support
│   ├── voice_input.py          # Speech-to-text (Groq Whisper)
│   ├── db.py                   # MongoDB client
│   └── email_service.py        # Gmail SMTP notifications
├── data/
│   └── customer_support_tickets.csv
├── vector_store/               # Persisted FAISS index (auto-generated)
├── uploads/                    # Screenshot attachments
└── docs/
    ├── api.md                  # Full API reference
    ├── features.md             # Feature documentation
    ├── architecture.md         # System architecture
    ├── use-cases.md            # Use case diagrams & scenarios
    ├── tech-stack.md           # Technology decisions & trade-offs
    └── report_docs/            # Academic report + UML/DFD diagrams
```

---

## Key Features

| Feature | Description |
|---------|-------------|
| RAG-Powered Responses | Retrieves similar historical tickets as LLM context |
| Multilingual Support | Auto-detects and translates 21+ languages |
| Voice Interface | Full STT → RAG → TTS round-trip |
| Ticket Intelligence | AI categorization, priority, sentiment, summary |
| Feedback Loop | Users rate an answer and the model rewrites it |
| Email Notifications | HTML emails to customers and the support team |
| Admin Dashboard | Streamlit ticket queue with filters and status updates |
| Screenshot Attachments | Users can upload screenshots with tickets |

---

## Environment Variables

A blank value (`MONGODB_URI=`) is treated as unset and falls back to the default.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_API_KEY` | Yes | — | Google Gemini API (embeddings) |
| `GROQ_API_KEY` | Yes | — | Groq API (LLM + Whisper STT) |
| `MONGODB_URI` | No | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DB` | No | `customer_support` | Database name |
| `GMAIL_ADDRESS` | No | — | Gmail address for sending notifications |
| `GMAIL_APP_PASSWORD` | No | — | Gmail App Password (not the account password) |
| `DEVELOPER_EMAIL` | No | — | Support team email for ticket alerts |
| `DATA_PATH` | No | `data/customer_support_tickets.csv` | Source dataset |
| `VECTOR_STORE_PATH` | No | `vector_store` | Where the FAISS index is persisted |

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | Serves the web frontend |
| `GET` | `/status` | Subsystem health (RAG, LLM, MongoDB, email) |
| `POST` | `/self-help` | Self-help steps for an issue |
| `POST` | `/tickets` | Create a ticket (JSON) |
| `POST` | `/tickets/with-screenshot` | Create a ticket with an attachment |
| `GET` | `/tickets` | List all tickets |
| `GET` | `/tickets/stats` | Aggregate counts by status/priority/category |
| `GET` | `/tickets/by-email/{email}` | Tickets for one customer |
| `GET` | `/tickets/{ticket_id}` | Single ticket |
| `PATCH` | `/tickets/{ticket_id}/status` | Move a ticket through its lifecycle |
| `POST` | `/transcribe` | Audio → text |
| `POST` | `/voice-chat` | Full STT → RAG → TTS round-trip |
| `POST` | `/feedback` | Rate a response and get an improved one |
| `GET` | `/feedback` | Feedback history |
| `POST` | `/analyze` | Categorization + retrieval analysis |

Full request/response schemas are in [docs/api.md](docs/api.md). Interactive
docs are served at `/docs` while the server is running.

---

## Documentation

- [API Reference](docs/api.md) — All REST endpoints with request/response schemas
- [Features](docs/features.md) — Detailed feature descriptions and usage
- [Architecture](docs/architecture.md) — System design and component interactions
- [Use Cases](docs/use-cases.md) — User scenarios and flow diagrams
- [Tech Stack](docs/tech-stack.md) — Technology choices and rationale
- [Project Report](docs/report_docs/) — Academic write-up with UML, DFD and ER diagrams

---

## Testing

The suite runs fully offline — Groq, Gemini, MongoDB and pyttsx3 are all mocked.

```bash
# Run everything
pytest -q

# Endpoints only
pytest test_api.py -v

# A single class
pytest test_api.py::TestTickets -v

# With coverage
pytest --cov=src --cov-report=html
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `numpy.core.multiarray failed to import` | `faiss-cpu` 1.7.x is built against numpy 1.x. `pip install -U "faiss-cpu>=1.9.0"` |
| `Router.__init__() got an unexpected keyword argument 'on_startup'` | `fastapi` and `starlette` versions are mismatched. `pip install -U fastapi` |
| `'charmap' codec can't encode character` | Legacy Windows code page. Handled automatically on `import src`; run inside a UTF-8 terminal if it persists |
| `Empty host (or extra comma in host list)` | `MONGODB_URI=` is blank in `.env`. Remove the line or give it a real URI |
| `/status` shows `Degraded — RAG not ready` | No FAISS index yet. Run `python main.py --setup` |
| `401 Invalid API Key` in a response | `GROQ_API_KEY` or `GOOGLE_API_KEY` is expired — regenerate it |
| `--setup` aborts with `consecutive embedding calls failed` | `GOOGLE_API_KEY` is invalid or out of quota. Setup stops early and saves nothing rather than persisting an index of empty vectors that would match nothing — fix the key and re-run |
| Answers never cite similar tickets | The index built while embeddings were failing. Rebuild with `python main.py --setup --force-rebuild` |

---

## Performance Benchmarks

| Operation | Time |
|-----------|------|
| FAISS index search | < 5ms |
| Groq LLM inference | 1–3s |
| Groq Whisper transcription | 2–5s |
| pyttsx3 TTS generation | 1–2s |
| Gemini embedding (single) | 100–200ms |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Authors

- Sarthak Doshi — Major Project, 8th Semester
