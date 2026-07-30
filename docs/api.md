# API Reference

Base URL: `http://localhost:8000`

All request bodies use `application/json` unless noted as multipart form data. All responses return `application/json`.

---

## Table of Contents

1. [System Status](#system-status)
2. [Self-Help](#self-help)
3. [Tickets](#tickets) — including [GET /tickets/stats](#get-ticketsstats)
4. [Voice](#voice)
5. [Feedback](#feedback)
6. [Analysis](#analysis)
7. [Error Responses](#error-responses)

---

## System Status

### GET /

Serves the user-facing HTML frontend (`index.html`).

**Response:** `text/html`

---

### GET /status

Returns the current health and readiness of all system components. The server
boots even when a subsystem is unavailable, so this endpoint is the way to find
out what is actually working.

**Response:**

```json
{
  "status": "Online · 108 docs",
  "rag_initialized": true,
  "llm_ready": true,
  "documents_indexed": 108,
  "mongodb_connected": true,
  "email_configured": true,
  "groq_configured": true,
  "gemini_configured": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Human-readable summary shown in the frontend chip |
| `rag_initialized` | boolean | Whether the FAISS vector store is loaded |
| `llm_ready` | boolean | Whether the response generator was constructed |
| `documents_indexed` | integer | Number of documents in the vector store |
| `mongodb_connected` | boolean | MongoDB connectivity |
| `email_configured` | boolean | Gmail SMTP credentials present |
| `groq_configured` | boolean | `GROQ_API_KEY` is set |
| `gemini_configured` | boolean | `GOOGLE_API_KEY` is set |

`status` reads `"Online · N docs"` when healthy, otherwise
`"Degraded — LLM not configured"` or `"Degraded — RAG not ready"`.

---

## Self-Help

The self-help flow is the first step before a ticket is created. It uses RAG to retrieve relevant historical support context and generates actionable troubleshooting steps for the user.

### POST /self-help

Generate self-help steps for an issue without creating a ticket.

**Request Body:**

```json
{
  "issue": "My account keeps getting logged out every few minutes",
  "language": "en"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `issue` | string | Yes | The user's problem description |
| `language` | string | No | BCP-47 language code (default: `"en"`) |

**Response:**

```json
{
  "response": "Here are some steps to resolve your issue:\n1. Clear browser cookies...\n2. Check for concurrent sessions...\n3. Update your password...",
  "steps": [
    "Clear browser cookies and cache from your browser settings.",
    "Check if you have any other active sessions under Account > Security.",
    "Update your password and enable two-factor authentication."
  ],
  "language": "en",
  "language_name": "English",
  "english_query": "My account keeps getting logged out every few minutes"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `response` | string | Full formatted self-help response |
| `steps` | array[string] | Parsed numbered steps (2–3 items) |
| `language` | string | Detected or provided language code |
| `language_name` | string | Human-readable language name |
| `english_query` | string | Translated query (if input was not English) |

**Example — Hindi Input:**

```json
// Request
{
  "issue": "मेरा पासवर्ड रीसेट नहीं हो रहा है",
  "language": "hi"
}

// Response
{
  "response": "यहाँ आपकी समस्या को हल करने के चरण हैं...",
  "steps": ["अपना ईमेल चेक करें", "स्पैम फ़ोल्डर देखें", "5 मिनट प्रतीक्षा करें"],
  "language": "hi",
  "language_name": "Hindi",
  "english_query": "My password is not resetting"
}
```

---

## Tickets

Tickets represent support requests that could not be resolved via self-help.

### POST /tickets

Create a new support ticket. The system automatically categorizes, prioritizes, analyzes sentiment, and generates an AI response.

**Request Body (JSON):**

```json
{
  "user_name": "Jane Doe",
  "user_email": "jane@example.com",
  "issue_description": "I was charged twice for my subscription this month",
  "category": "Billing",
  "priority": "high",
  "language": "en",
  "attempt_history": "I already tried contacting billing chat but no response."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_name` | string | Yes | Full name of the customer |
| `user_email` | string | Yes | Customer email for confirmation |
| `issue_description` | string | Yes | Detailed description of the issue |
| `category` | string | No | Overrides AI categorization if provided |
| `priority` | string | No | Overrides AI priority if provided |
| `language` | string | No | BCP-47 language code (auto-detected if omitted) |
| `attempt_history` | string | No | Prior resolution attempts by the customer |

**Valid Categories:**
- `Billing`
- `Technical Support`
- `Account Management`
- `Product Information`
- `Shipping & Delivery`
- `Returns & Refunds`
- `General Inquiry`

**Valid Priority Values:**
- `urgent` — SLA: 2 hours
- `high` — SLA: 8 hours
- `medium` — SLA: 24 hours
- `low` — SLA: 72 hours

**Response:**

```json
{
  "ticket_id": "TKT-20260420-0042",
  "category": "Billing",
  "priority": "high",
  "sentiment": "negative",
  "ai_response": "Thank you for reaching out. We sincerely apologize for the double charge. Our billing team has been alerted and will process a refund within 3-5 business days...",
  "language": "en",
  "email_sent": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `ticket_id` | string | Unique identifier (format: `TKT-YYYYMMDD-NNNN`) |
| `category` | string | AI-classified or provided category |
| `priority` | string | AI-classified or provided priority |
| `sentiment` | string | `"positive"`, `"neutral"`, or `"negative"` |
| `ai_response` | string | Generated support response (in user's language) |
| `language` | string | Detected language code |
| `email_sent` | boolean | Whether confirmation email was dispatched |

---

### POST /tickets/with-screenshot

Same as `POST /tickets` but accepts a screenshot attachment. Uses `multipart/form-data`.

**Form Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_name` | string | Yes | Customer full name |
| `user_email` | string | Yes | Customer email |
| `issue_description` | string | Yes | Issue description |
| `category` | string | No | Optional override |
| `priority` | string | No | Optional override |
| `language` | string | No | Language code |
| `attempt_history` | string | No | Prior attempts |
| `screenshot` | file | No | Image file — `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, max 5 MB |

**Response:** Same as `POST /tickets`, with additional field:

```json
{
  "ticket_id": "TKT-20260420-0043",
  "screenshot_saved": true,
  ...
}
```

**Screenshot handling:** the uploaded filename is never used on disk. Each file
is stored under `uploads/` with a generated random name and its original
extension, so a crafted name such as `../../src/config.py` cannot escape the
upload directory or overwrite project files.

| HTTP Status | Scenario |
|-------------|----------|
| `400 Bad Request` | Extension not in the allowed list |
| `413 Payload Too Large` | File exceeds 5 MB |

---

### GET /tickets

Retrieve all tickets. Intended for admin/agent use.

**Response:**

```json
[
  {
    "ticket_id": "TKT-20260420-0042",
    "user_name": "Jane Doe",
    "user_email": "jane@example.com",
    "issue_description": "...",
    "category": "Billing",
    "priority": "high",
    "sentiment": "negative",
    "summary": "Customer charged twice for subscription",
    "ai_response": "...",
    "status": "open",
    "language": "en",
    "created_at": "2026-04-20T10:30:00Z",
    "updated_at": "2026-04-20T10:30:00Z"
  }
]
```

Results are sorted by `created_at` descending (newest first).

Returns `[]` rather than an error when MongoDB is unavailable.

---

### GET /tickets/stats

Aggregate ticket counts, used by the Streamlit dashboard and any custom admin UI.

Declared before `/tickets/{ticket_id}` so `stats` is never interpreted as a
ticket ID.

**Response:**

```json
{
  "total": 128,
  "by_status": { "open": 40, "in_progress": 18, "resolved": 70 },
  "by_priority": { "urgent": 6, "high": 22, "medium": 71, "low": 29 },
  "by_category": { "Billing": 44, "Technical Support": 51, "General Inquiry": 33 }
}
```

Returns zeroed counters when MongoDB is unavailable.

---

### GET /tickets/by-email/{email}

Retrieve all tickets submitted by a specific customer email.

**Path Parameter:** `email` — URL-encoded email address

**Response:** Array of ticket objects (same schema as GET /tickets items).

**Example:**
```
GET /tickets/by-email/jane%40example.com
```

---

### GET /tickets/{ticket_id}

Retrieve a single ticket by its ID.

**Path Parameter:** `ticket_id` — Ticket ID string (e.g., `TKT-20260420-0042`)

**Response:** Single ticket object.

**404 Response:**
```json
{
  "detail": "Ticket not found"
}
```

---

### PATCH /tickets/{ticket_id}/status

Update the status of a ticket.

**Path Parameter:** `ticket_id` — Ticket ID string

**Request Body:**

```json
{
  "status": "resolved"
}
```

**Valid Status Values:** `open`, `in_progress`, `resolved`

**Response:**

```json
{
  "ticket_id": "TKT-20260420-0042",
  "status": "resolved"
}
```

---

## Voice

### POST /transcribe

Transcribe an audio recording to text using Groq Whisper.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audio` | file | Yes | Audio file (webm, wav, mp3, m4a) |
| `language` | string | No | BCP-47 language code hint (default: `"en-US"`) |

**Response:**

```json
{
  "text": "My order was supposed to arrive yesterday but it hasn't shown up",
  "transcript": "My order was supposed to arrive yesterday but it hasn't shown up",
  "language": "en-US"
}
```

---

### POST /voice-chat

Full voice interaction round-trip: audio input → transcription → RAG self-help → text-to-speech audio output.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audio` | file | Yes | Audio file (webm format preferred) |
| `language` | string | No | BCP-47 language code (default: `"en-US"`) |
| `attempt` | integer | No | Attempt number (for retry tracking) |

**Response:** `audio/wav` stream

**Response Headers:**

| Header | Description |
|--------|-------------|
| `X-Transcript` | URL-encoded transcript of user's audio |
| `X-Response-Text` | URL-encoded text of the generated response |
| `X-Language` | Detected language code |

**Processing Pipeline:**

```
Audio Input
    │
    ▼
Groq Whisper (STT)
    │
    ▼
Language Detection → Translation to English
    │
    ▼
RAG Self-Help Generation
    │
    ▼
Translation back to user's language
    │
    ▼
pyttsx3 Text-to-Speech (offline)
    │
    ▼
WAV Audio Stream Response
```

---

## Feedback

### POST /feedback

Submit feedback on a generated AI response. The system will improve the response using the feedback.

**Request Body:**

```json
{
  "query": "My internet keeps disconnecting",
  "original_response": "Please restart your router and check cable connections.",
  "feedback": "The response was too generic. I have fiber optic and already restarted.",
  "rating": 2
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | The original user question |
| `original_response` | string | Yes | The AI response being rated |
| `feedback` | string | Yes | Textual feedback for improvement |
| `rating` | integer | No | Rating from 1 (poor) to 5 (excellent) |

**Response:**

```json
{
  "improved_response": "I understand you have fiber optic internet and have already tried restarting. Let's dig deeper: check your ONT device lights, verify the fiber cable is properly seated, log into your router admin panel at 192.168.1.1 to check for errors, and contact your ISP's fiber support line for a line test."
}
```

---

### GET /feedback

Retrieve all feedback records.

**Response:**

```json
[
  {
    "query": "My internet keeps disconnecting",
    "original_response": "Please restart your router...",
    "feedback": "Too generic",
    "rating": 2,
    "improved_response": "For fiber optic connections...",
    "created_at": "2026-04-20T11:00:00Z"
  }
]
```

---

## Analysis

### POST /analyze

Perform a deep analysis of a support issue without creating a ticket. Returns categorization, retrieval statistics, and similar historical tickets.

**Request Body:**

```json
{
  "issue": "Application crashes when uploading files larger than 10MB",
  "language": "en"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `issue` | string | Yes | Issue description |
| `language` | string | No | Language code |

**Response:**

```json
{
  "categorization": {
    "category": "Technical Support",
    "priority": "high",
    "sentiment": "negative",
    "summary": "Application crashes on large file uploads"
  },
  "retrieval_analysis": {
    "total_retrieved": 5,
    "avg_similarity": 0.82,
    "category_distribution": {
      "Technical Support": 4,
      "General Inquiry": 1
    }
  },
  "similar_tickets": [
    {
      "id": "42",
      "instruction": "App crashes when I upload images",
      "response": "This is a known issue with files over 8MB...",
      "similarity_score": 0.91
    }
  ],
  "language": "en"
}
```

---

## Error Responses

All errors follow the standard FastAPI error format:

```json
{
  "detail": "Human-readable error message"
}
```

| HTTP Status | Scenario |
|-------------|----------|
| `400 Bad Request` | Missing required fields, invalid email, unsupported file type |
| `404 Not Found` | Ticket ID does not exist |
| `413 Payload Too Large` | Screenshot exceeds the 5 MB limit |
| `422 Unprocessable Entity` | Request body schema validation failure, or audio that could not be transcribed |
| `503 Service Unavailable` | A required subsystem is down — RAG not initialized, LLM not configured, MongoDB unreachable, or speech-to-text failing |
| `500 Internal Server Error` | Unexpected server-side error |

`503` is the normal response when the server booted without valid API keys.
Check `GET /status` to see which subsystem is missing.

---

## Rate Limits & Quotas

| Service | Limit | Notes |
|---------|-------|-------|
| Google Gemini Embeddings | ~60 requests/min | Only used during index build |
| Groq LLM | ~30 req/min (free tier) | Shared across all endpoints |
| Groq Whisper | ~20 req/min (free tier) | Voice endpoints only |
| Gmail SMTP | 500 emails/day | Per Gmail account |
