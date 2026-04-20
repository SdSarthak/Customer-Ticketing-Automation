# Features Documentation

This document describes every major feature of the AI Customer Support Agent System — how it works, why it exists, and how to use it.

---

## Table of Contents

1. [Self-Help Resolution](#1-self-help-resolution)
2. [Intelligent Ticket Creation](#2-intelligent-ticket-creation)
3. [RAG-Powered Contextual Responses](#3-rag-powered-contextual-responses)
4. [Multilingual Support](#4-multilingual-support)
5. [Voice Interface](#5-voice-interface)
6. [Ticket Categorization & Prioritization](#6-ticket-categorization--prioritization)
7. [Sentiment Analysis](#7-sentiment-analysis)
8. [Email Notifications](#8-email-notifications)
9. [Screenshot Attachments](#9-screenshot-attachments)
10. [Feedback Loop & Response Improvement](#10-feedback-loop--response-improvement)
11. [Response Sampling (Multi-Candidate)](#11-response-sampling-multi-candidate)
12. [Admin Dashboard (Streamlit)](#12-admin-dashboard-streamlit)
13. [Vector Store Persistence](#13-vector-store-persistence)
14. [CLI Mode](#14-cli-mode)

---

## 1. Self-Help Resolution

### What It Does

Before a formal ticket is created, the system attempts to resolve the customer's issue automatically. It generates 2–3 specific, actionable troubleshooting steps tailored to the exact problem description.

### How It Works

1. The user submits their issue description via the web frontend.
2. The system detects the language and translates to English if needed.
3. The RAG engine retrieves the 3 most similar historical support cases from the FAISS vector store.
4. The retrieved context is injected into a structured prompt sent to the Groq LLM (Llama 3.3 70B).
5. The model generates 2–3 numbered self-help steps.
6. Steps are parsed and returned individually, plus as a full response block.
7. The response is translated back to the user's language.

### Why It Matters

Reduces ticket volume by resolving common issues automatically. This is the first line of defense in the support funnel — issues that can be self-resolved never become tickets, freeing agents for complex cases.

### Configuration

```python
# src/config.py
TOP_K_RESULTS = 5           # Retrieval pool size
NUM_RESPONSE_CANDIDATES = 3 # Candidates for sampling
SIMILARITY_THRESHOLD = 0.5  # Minimum cosine similarity to include result
```

System prompt:
```python
Config.SYSTEM_PROMPTS["self_help"]
# → "Generate 2-3 specific, actionable self-help steps..."
```

---

## 2. Intelligent Ticket Creation

### What It Does

When self-help is insufficient, the user submits a formal ticket. The system enriches the ticket with AI-generated metadata and a full response, then persists it to MongoDB and dispatches email notifications.

### Ticket Lifecycle

```
Submitted → open → in_progress → resolved
```

### What Gets Stored

| Field | Source |
|-------|--------|
| `ticket_id` | Auto-generated: `TKT-YYYYMMDD-NNNN` |
| `category` | AI classification or manual override |
| `priority` | AI classification or manual override |
| `sentiment` | AI sentiment analysis |
| `summary` | AI-generated one-line summary |
| `ai_response` | RAG + LLM generated response |
| `screenshot_path` | File upload path (optional) |
| `attempt_history` | Customer's prior resolution attempts |
| `language` | Auto-detected language code |
| `status` | `open` (default), `in_progress`, `resolved` |
| `created_at` / `updated_at` | ISO 8601 timestamps |

### Priority SLAs

| Priority | Expected Response Time |
|----------|----------------------|
| urgent | 2 hours |
| high | 8 hours |
| medium | 24 hours |
| low | 72 hours |

---

## 3. RAG-Powered Contextual Responses

### What It Does

All response generation is grounded in real historical support data. The system retrieves the most semantically similar past support interactions and uses them as context when prompting the LLM.

### Pipeline

```
User Query
    │
    ▼
GeminiEmbeddings.create_query_embedding()
    │  (3072-dimensional vector)
    ▼
FAISSVectorStore.search()
    │  (cosine similarity via IndexFlatIP)
    ▼
Top-K Documents (k=5, threshold=0.5)
    │
    ▼
Format context string
    │  "Relevant case 1: ...\nRelevant case 2: ..."
    ▼
Groq LLM prompt injection
    │
    ▼
Grounded response
```

### Why RAG Over Fine-Tuning

- **No retraining needed** — knowledge base updates instantly when new tickets are added
- **Source transparency** — every response can be traced back to retrieved documents
- **Cost-effective** — uses free Groq API instead of hosting a fine-tuned model
- **Recency** — new support resolutions are immediately available for retrieval

### Document Format

Each indexed document contains:

```python
{
    "id": "42",
    "instruction": "Customer query text",
    "response": "Support response text",
    "category": "Technical Support",
    "combined_text": "Customer Query: ...\nSupport Response: ..."
}
```

The `combined_text` field is what gets embedded — combining both query and response gives richer semantic representation.

---

## 4. Multilingual Support

### What It Does

The system automatically detects the language of any incoming text and operates entirely in that language. Customers receive responses in the same language they used, without any manual configuration.

### Supported Languages

| Code | Language | Code | Language |
|------|----------|------|----------|
| `en` | English | `hi` | Hindi |
| `fr` | French | `de` | German |
| `es` | Spanish | `pt` | Portuguese |
| `ar` | Arabic | `zh-cn` | Chinese (Simplified) |
| `ja` | Japanese | `ko` | Korean |
| `ru` | Russian | `it` | Italian |
| `nl` | Dutch | `tr` | Turkish |
| `pl` | Polish | `bn` | Bengali |
| `ta` | Tamil | `te` | Telugu |
| `mr` | Marathi | `gu` | Gujarati |
| `kn` | Kannada | `ml` | Malayalam |
| `pa` | Punjabi | `ur` | Urdu |

### How It Works

```
Input text (any language)
    │
    ▼
langdetect → ISO language code
    │
    ▼
deep-translator → English
    │
    ▼
[All processing in English: RAG, LLM, categorization]
    │
    ▼
deep-translator → Original language
    │
    ▼
Response delivered in user's language
```

### Voice Language Mapping

The translator module maps ISO-639-1 codes to BCP-47 for Whisper:

```python
'hi' → 'hi-IN'   # Hindi (India)
'zh-cn' → 'zh'   # Chinese
'en' → 'en-US'   # English (US)
```

### Fallback Behavior

- If language detection fails → defaults to `'en'`
- If translation fails → returns original text unchanged
- If unsupported language → processes as-is (LLM handles many languages natively)

---

## 5. Voice Interface

### What It Does

Customers can speak their issue instead of typing. The system transcribes audio to text, processes it through the full RAG pipeline, and returns a spoken audio response.

### Components

| Component | Technology | Notes |
|-----------|-----------|-------|
| Speech-to-Text | Groq Whisper (large-v3-turbo) | Free, no quota, 30+ languages |
| Text-to-Speech | pyttsx3 | Offline, Windows SAPI voices, no API key |
| Audio Format | Input: webm; Output: WAV | Converted internally |

### Voice Chat Flow

```
User speaks into browser microphone
    │
    ▼
Audio recorded as webm blob (audio-recorder-streamlit)
    │
    ▼
POST /voice-chat (multipart/form-data)
    │
    ▼
Groq Whisper API → transcript text
    │
    ▼
Language detection on transcript
    │
    ▼
translate_to_english() → generate_self_help() → translate_back()
    │
    ▼
pyttsx3 TTS → WAV bytes
    │
    ▼
Response: audio/wav stream
Headers: X-Transcript, X-Response-Text, X-Language
```

### Transcription-Only Mode

For cases where only transcription is needed (without TTS response):

```
POST /transcribe
Input:  audio file
Output: { "text": "...", "transcript": "...", "language": "en-US" }
```

### TTS Preprocessing

Before TTS generation, the response text is cleaned:
- Markdown characters stripped (`**`, `*`, `#`, `` ` ``, `_`)
- Bullet points replaced with natural pauses
- Ensures natural spoken audio without reading markdown syntax aloud

---

## 6. Ticket Categorization & Prioritization

### What It Does

Every ticket is automatically classified by category and priority using AI inference. This eliminates manual triage and ensures tickets reach the right team immediately.

### Categories

- **Billing** — Payment issues, charges, refunds, invoices
- **Technical Support** — Software bugs, crashes, connectivity issues
- **Account Management** — Login, password, account settings
- **Product Information** — Features, compatibility, specifications
- **Shipping & Delivery** — Order tracking, delays, missing packages
- **Returns & Refunds** — Return requests, refund status
- **General Inquiry** — Anything that doesn't fit above

### Priority Levels

| Priority | Criteria | SLA |
|----------|----------|-----|
| `urgent` | System down, data loss, security breach | 2 hours |
| `high` | Core functionality broken, significant financial impact | 8 hours |
| `medium` | Partial functionality issue, workaround available | 24 hours |
| `low` | Minor issue, cosmetic, general question | 72 hours |

### Categorization Prompt

The system uses a low-temperature prompt (0.1) for deterministic classification:

```python
Config.SYSTEM_PROMPTS["categorization"]
# Returns JSON: { "category": "...", "priority": "...", "sentiment": "...", "summary": "..." }
```

Temperature is set to `0.1` (nearly deterministic) to ensure consistent, reliable classification.

### Manual Override

Callers can override AI classification by providing `category` and/or `priority` in the request body. Overrides take precedence over AI predictions.

---

## 7. Sentiment Analysis

### What It Does

Every ticket is analyzed for customer sentiment. This helps support agents prioritize emotional responses and triggers escalation flags.

### Sentiment Values

- `positive` — Customer is calm, polite, satisfied with prior interaction
- `neutral` — Matter-of-fact tone, no strong emotion
- `negative` — Frustrated, angry, or dissatisfied

### How It's Used

- Included in developer alert emails (enables agents to prepare emotionally)
- Stored on tickets for CRM analysis
- Available via `GET /analyze` for pre-ticket assessment

---

## 8. Email Notifications

### What It Does

When a ticket is created, two emails are automatically dispatched:

1. **Customer Confirmation** — Acknowledges receipt, provides ticket ID, expected resolution time, and the initial AI response
2. **Developer/Agent Alert** — Detailed ticket info for the support team, including all metadata and optional screenshot

### Customer Confirmation Email

- **To:** Customer's provided email
- **Subject:** `[Ticket #TKT-...] Your support request has been received`
- **Content:**
  - Ticket ID and reference number
  - Category badge
  - Priority level with SLA hours
  - Initial AI-generated response
  - Blue header design for professionalism

### Developer Alert Email

- **To:** `DEVELOPER_EMAIL` from environment config
- **Subject:** `[PRIORITY] New Support Ticket: TKT-...`
- **Content:**
  - All ticket metadata (category, priority, sentiment)
  - Full customer contact info
  - Customer's prior attempt history
  - Full issue description
  - AI response (for review/modification)
  - Optional screenshot attachment
  - Red header to convey urgency

### Configuration Requirements

```env
GMAIL_ADDRESS=your_gmail@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx  # NOT your Gmail password
DEVELOPER_EMAIL=support@yourcompany.com
```

A Gmail App Password requires:
1. Google Account 2-Factor Authentication enabled
2. App Password generated under Security settings

### Graceful Degradation

If email credentials are not configured, ticket creation still succeeds. The `email_sent` field in the response will be `false`. The system never fails a ticket creation due to email issues.

---

## 9. Screenshot Attachments

### What It Does

Customers can attach screenshots to their support tickets via the `POST /tickets/with-screenshot` endpoint.

### File Handling

- Accepted formats: PNG, JPG, JPEG, GIF, WebP
- Files are saved to `uploads/` directory with a timestamp prefix
- Screenshot path is stored on the ticket record
- Screenshots are attached to developer alert emails (inline attachment)

### Usage

```http
POST /tickets/with-screenshot
Content-Type: multipart/form-data

user_name=Jane Doe
user_email=jane@example.com
issue_description=App shows this error on upload
screenshot=<file>
```

---

## 10. Feedback Loop & Response Improvement

### What It Does

Users can rate AI responses and provide written feedback. The system uses this feedback to generate an improved response in real-time, which is also stored for analysis.

### Feedback Submission Flow

```
User rates response (1-5 stars) + writes feedback
    │
    ▼
POST /feedback
    │
    ▼
ResponseGenerator.improve_response(original, feedback)
    │ Uses "response_improvement" system prompt
    ▼
Improved response returned + saved to MongoDB
```

### Improvement Prompt

The improvement uses a dedicated system prompt that asks the LLM to:
- Address the specific shortcomings mentioned in the feedback
- Preserve accurate parts of the original response
- Maintain professional, empathetic tone

### Feedback Storage

Each feedback record stores:
- Original query
- Original AI response
- User's feedback text
- Numeric rating (1–5)
- Improved response
- Timestamp

### Fallback

If MongoDB is unavailable, feedback is stored in-memory and accessible during the session. Records are lost on server restart unless persisted.

---

## 11. Response Sampling (Multi-Candidate)

### What It Does

Generates multiple response candidates at different LLM temperature settings, allowing agents to compare and select the best option.

### Candidate Profiles

| Candidate | Temperature | Style |
|-----------|------------|-------|
| 1 | 0.3 | Conservative — precise, factual, minimal embellishment |
| 2 | 0.7 | Balanced — natural tone, context-aware |
| 3 | 1.0 | Creative — empathetic, verbose, personalized |

### Usage

Called internally by the Streamlit admin dashboard's "Response Sampling" feature. Agents can compare all three and select the most appropriate one for the situation.

```python
ResponseGenerator.generate_multiple_responses(query, num_candidates=3)
# Returns: [{"id": 1, "text": "...", "temperature": 0.3, "style": "conservative"}, ...]
```

---

## 12. Admin Dashboard (Streamlit)

### What It Does

A rich web interface for support agents and administrators, separate from the customer-facing frontend.

### Features

| Panel | Description |
|-------|-------------|
| Chat Interface | Real-time support chat with RAG-grounded responses |
| Ticket Analysis | Classify and analyze any issue without creating a ticket |
| Similar Tickets | View historically similar support cases |
| Response Sampling | Compare conservative/balanced/creative response candidates |
| Feedback History | View and export all feedback records |
| System Status | Monitor RAG readiness, document count, service health |

### Access

```bash
streamlit run app.py
# Visit http://localhost:8501
```

### When to Use vs. Customer Frontend

| Dashboard | Audience | URL |
|-----------|----------|-----|
| `index.html` (FastAPI) | Customers | `http://localhost:8000` |
| Streamlit | Support agents, admins | `http://localhost:8501` |

---

## 13. Vector Store Persistence

### What It Does

The FAISS vector index is persisted to disk so the system does not need to re-embed all documents on every startup. Rebuilding is triggered explicitly when the knowledge base changes.

### Persisted Files

```
vector_store/
├── faiss_index.bin     # Binary FAISS index
└── metadata.pkl        # Document metadata (Python pickle)
```

### Build vs. Load Logic

```python
# main.py
if os.path.exists(vector_store_path) and not force_rebuild:
    rag_engine.load_from_disk(vector_store_path)
else:
    rag_engine.initialize_from_documents(documents)
    rag_engine.save_to_disk(vector_store_path)
```

### Forcing a Rebuild

```bash
python main.py --force-rebuild
# or
python main.py --data new_data.csv --force-rebuild
```

### Performance Impact

- Cold start (full rebuild): ~30–60s for 2,500 documents (limited by Gemini API rate)
- Warm start (load from disk): < 1 second

---

## 14. CLI Mode

### What It Does

A command-line interface for system management and interactive support chat without a browser.

### Commands

```bash
# Initialize system, validate API keys, build vector store
python main.py --setup

# Start interactive chat REPL
python main.py --interactive

# Use a different data file
python main.py --data /path/to/tickets.csv

# Force rebuild the vector store
python main.py --force-rebuild

# Launch the Streamlit UI
python main.py --streamlit
```

### Interactive Mode Commands

Within `--interactive` mode:

| Command | Description |
|---------|-------------|
| `help` | Show available commands |
| `status` | Display system and index stats |
| `analyze <query>` | Deep-analyze a query |
| `similar <query>` | Find similar historical tickets |
| `quit` / `exit` | Exit interactive mode |
| Any other text | Generate a support response |
