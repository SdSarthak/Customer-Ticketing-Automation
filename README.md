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
- MongoDB (local or Atlas)
- API Keys: Google Gemini, Groq
- Gmail account with App Password (2FA required)

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd "Major 8th sem"

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Running the System

```bash
# Initialize the system (first run)
python main.py --setup

# Start FastAPI backend (primary interface)
uvicorn api:app --reload --port 8000
# Visit: http://localhost:8000

# Start Streamlit admin dashboard (optional)
streamlit run app.py
# Visit: http://localhost:8501

# CLI interactive mode
python main.py --interactive
```

---

## Architecture at a Glance

```
User Request (Text / Voice)
        │
        ▼
  Language Detection & Translation (langdetect + Google Translate)
        │
        ▼
  Self-Help Generation ──► FAISS Vector Search ──► Groq LLM
        │
        ▼
  Issue Unresolved? ──► Ticket Creation
        │
        ▼
  Categorization + Priority + Sentiment (Groq Llama 3.3 70B)
        │
        ├──► MongoDB (persistence)
        ├──► Gmail (customer + developer notifications)
        └──► Response Translation & Delivery
```

---

## Project Structure

```
Major 8th sem/
├── main.py                     # CLI entry point
├── api.py                      # FastAPI REST backend
├── app.py                      # Streamlit admin dashboard
├── test_api.py                 # Pytest test suite (40+ tests)
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
    └── tech-stack.md           # Technology decisions & trade-offs
```

---

## Key Features

| Feature | Description |
|---------|-------------|
| RAG-Powered Responses | Retrieves similar historical tickets as LLM context |
| Multilingual Support | Auto-detects and translates 21+ languages |
| Voice Interface | Full STT → RAG → TTS round-trip |
| Ticket Intelligence | AI categorization, priority, sentiment, summary |
| Feedback Loop | Users can rate and improve AI responses |
| Email Notifications | HTML emails to customers and support team |
| Admin Dashboard | Streamlit UI for agents and administrators |
| Screenshot Attachments | Users can upload screenshots with tickets |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes | Google Gemini API (embeddings) |
| `GROQ_API_KEY` | Yes | Groq API (LLM + Whisper STT) |
| `MONGODB_URI` | No | MongoDB connection string (default: localhost) |
| `MONGODB_DB` | No | Database name (default: customer_support) |
| `GMAIL_ADDRESS` | No | Gmail address for sending notifications |
| `GMAIL_APP_PASSWORD` | No | Gmail App Password (not account password) |
| `DEVELOPER_EMAIL` | No | Support team email for ticket alerts |

---

## Documentation

- [API Reference](docs/api.md) — All REST endpoints with request/response schemas
- [Features](docs/features.md) — Detailed feature descriptions and usage
- [Architecture](docs/architecture.md) — System design and component interactions
- [Use Cases](docs/use-cases.md) — User scenarios and flow diagrams
- [Tech Stack](docs/tech-stack.md) — Technology choices and rationale

---

## Testing

```bash
# Run all tests
pytest test_api.py -v

# Run specific test class
pytest test_api.py::TestTickets -v

# Run with coverage
pytest test_api.py --cov=src --cov-report=html
```

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
