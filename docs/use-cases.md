# Use Cases & User Scenarios

This document describes the primary use cases of the AI Customer Support Agent System, including actors, flows, preconditions, and ASCII flow diagrams.

---

## Table of Contents

1. [Actors](#1-actors)
2. [Use Case Overview Diagram](#2-use-case-overview-diagram)
3. [UC-01: Customer Self-Help Resolution](#uc-01-customer-self-help-resolution)
4. [UC-02: Customer Ticket Submission](#uc-02-customer-ticket-submission)
5. [UC-03: Voice-Based Support Interaction](#uc-03-voice-based-support-interaction)
6. [UC-04: Multilingual Support Request](#uc-04-multilingual-support-request)
7. [UC-05: Ticket with Screenshot Attachment](#uc-05-ticket-with-screenshot-attachment)
8. [UC-06: Agent Reviews and Responds to Ticket](#uc-06-agent-reviews-and-responds-to-ticket)
9. [UC-07: Customer Provides Feedback](#uc-07-customer-provides-feedback)
10. [UC-08: Admin Analyzes Support Issue](#uc-08-admin-analyzes-support-issue)
11. [UC-09: System Initialization by Developer](#uc-09-system-initialization-by-developer)
12. [UC-10: Agent Compares Response Candidates](#uc-10-agent-compares-response-candidates)
13. [UC-11: Admin Updates Ticket Status](#uc-11-admin-updates-ticket-status)
14. [UC-12: Customer Tracks Existing Ticket](#uc-12-customer-tracks-existing-ticket)
15. [Edge Cases & Alternate Flows](#15-edge-cases--alternate-flows)

---

## 1. Actors

| Actor | Role | Interface |
|-------|------|-----------|
| **Customer** | End user with a support issue | `index.html` (web browser) |
| **Support Agent** | Company employee handling tickets | Streamlit dashboard (`app.py`) |
| **Admin** | Manages system configuration and ticket oversight | Streamlit dashboard (`app.py`) |
| **Developer** | Deploys and maintains the system | CLI (`main.py`) |
| **AI System** | Automated processing pipeline | Internal |
| **External Services** | Groq, Gemini, Gmail, MongoDB | External APIs |

---

## 2. Use Case Overview Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    AI Customer Support System                     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Customer Actions                      │    │
│  │                                                         │    │
│  │  (Customer) ──── UC-01: Self-Help Resolution            │    │
│  │       │                                                 │    │
│  │       ├────────── UC-02: Ticket Submission              │    │
│  │       │                                                 │    │
│  │       ├────────── UC-03: Voice Support                  │    │
│  │       │                                                 │    │
│  │       ├────────── UC-04: Multilingual Request           │    │
│  │       │                                                 │    │
│  │       ├────────── UC-05: Screenshot Attachment          │    │
│  │       │                                                 │    │
│  │       └────────── UC-07: Feedback Submission            │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Agent / Admin Actions                   │    │
│  │                                                         │    │
│  │  (Agent) ─────── UC-06: Review & Respond to Ticket      │    │
│  │       │                                                 │    │
│  │       ├────────── UC-10: Compare Response Candidates    │    │
│  │       │                                                 │    │
│  │       └────────── UC-11: Update Ticket Status           │    │
│  │                                                         │    │
│  │  (Admin) ─────── UC-08: Analyze Support Issues         │    │
│  │                                                         │    │
│  │  (Customer) ─── UC-12: Track Existing Ticket           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   Developer Actions                      │    │
│  │  (Developer) ─── UC-09: System Initialization           │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

---

## UC-01: Customer Self-Help Resolution

**Actor:** Customer  
**Goal:** Resolve an issue without creating a ticket  
**Preconditions:** Vector store is initialized; Groq API is available  
**Trigger:** Customer describes a problem on the web frontend

### Main Success Scenario

```
Customer                  Frontend               FastAPI              AI Pipeline
    │                        │                      │                      │
    │── Describes issue ─────►│                      │                      │
    │                        │── POST /self-help ───►│                      │
    │                        │                      │── detect language ───►│
    │                        │                      │                      │── translate to EN
    │                        │                      │                      │── RAG retrieve top-3
    │                        │                      │                      │── Groq generate steps
    │                        │                      │                      │── translate back
    │                        │                      │◄─ { steps[], lang } ──│
    │                        │◄─ Display 2-3 steps ─│                      │
    │◄── Reads steps ─────────│                      │                      │
    │                        │                      │                      │
    [Issue resolved? YES]     │                      │                      │
    │── "This helped" ───────►│                      │                      │
    │                         END                                           │
    │                                                                       │
    [Issue resolved? NO]                                                    │
    │── Proceeds to UC-02 (Ticket Submission)                               │
```

### Alternate Flow: Low Confidence RAG Results

```
RAG retrieve top-3 → all similarity scores < 0.5
    │
    ▼
LLM generates steps without RAG context
    │
    ▼
Generic troubleshooting steps returned
    │
    ▼
System prompts customer to submit a ticket for personalized help
```

**Postconditions:** Customer receives 2–3 actionable steps in their language.

---

## UC-02: Customer Ticket Submission

**Actor:** Customer  
**Goal:** Submit a formal support ticket when self-help fails  
**Preconditions:** Customer has attempted self-help (UC-01)  
**Trigger:** Customer clicks "Submit Ticket" on the web frontend

### Main Success Scenario

```
Customer         Frontend           FastAPI           AI Services        External
    │                │                  │                  │                 │
    │─ Fill form ───►│                  │                  │                 │
    │  (name,email,  │                  │                  │                 │
    │   description) │                  │                  │                 │
    │                │─ POST /tickets ─►│                  │                 │
    │                │                  │─ detect lang ───►│                 │
    │                │                  │─ translate EN ──►│                 │
    │                │                  │                  │                 │
    │                │                  │─ categorize ────►│                 │
    │                │                  │  (cat,prio,sent) │                 │
    │                │                  │                  │                 │
    │                │                  │─ RAG retrieve ──►│                 │
    │                │                  │─ gen response ──►│                 │
    │                │                  │─ translate back ►│                 │
    │                │                  │                  │                 │
    │                │                  │─────────────────────── save ticket►│ MongoDB
    │                │                  │─────────────────────── email cust ►│ Gmail
    │                │                  │─────────────────────── email dev ──►│ Gmail
    │                │                  │                  │                 │
    │                │◄─ ticket_id ─────│                  │                 │
    │                │   + ai_response  │                  │                 │
    │◄─ Show ticket  │                  │                  │                 │
    │   confirmation │                  │                  │                 │
    │   + response   │                  │                  │                 │
```

### Postconditions

- Ticket saved in MongoDB with status `open`
- Customer receives confirmation email with ticket ID and AI response
- Support agent receives alert email with full ticket details

---

## UC-03: Voice-Based Support Interaction

**Actor:** Customer  
**Goal:** Get support using voice without typing  
**Preconditions:** Browser has microphone access; Groq API available; pyttsx3 installed  
**Trigger:** Customer clicks "Record" button on voice interface

### Main Success Scenario

```
Customer       Browser           FastAPI          Groq Whisper     pyttsx3
    │              │                 │                  │               │
    │─ Speaks ────►│                 │                  │               │
    │              │─ Record webm ──►│                 │               │
    │              │  POST /voice-chat                  │               │
    │              │                 │─ transcribe ────►│               │
    │              │                 │                  │─ STT process  │
    │              │                 │◄─ transcript ────│               │
    │              │                 │                  │               │
    │              │                 │─ detect lang                     │
    │              │                 │─ translate EN                    │
    │              │                 │─ RAG + generate                  │
    │              │                 │─ translate back                  │
    │              │                 │─ strip markdown                  │
    │              │                 │                                  │
    │              │                 │─ TTS generate ──────────────────►│
    │              │                 │◄─ WAV bytes ─────────────────────│
    │              │◄─ audio/wav ────│                                  │
    │◄─ Hears res  │  (+ X-Transcript header)                          │
```

### Alternate Flow: Transcription Fails

```
Groq Whisper → error (network issue, invalid audio format)
    │
    ▼
Return 500 with error message
Customer sees error: "Audio processing failed. Please try typing your issue."
```

**Postconditions:** Customer hears AI-generated support response in their language.

---

## UC-04: Multilingual Support Request

**Actor:** Customer (non-English speaker)  
**Goal:** Get support in their native language  
**Preconditions:** langdetect and deep-translator libraries available  
**Trigger:** Customer writes issue in a non-English language

### Main Success Scenario (Hindi Example)

```
Customer writes: "मेरा पासवर्ड रीसेट नहीं हो रहा है"
    │
    ▼
langdetect.detect() → 'hi' (Hindi)
    │
    ▼
GoogleTranslator('hi' → 'en').translate()
→ "My password is not resetting"
    │
    ▼
[Full English pipeline: RAG + categorize + respond]
→ English response generated
    │
    ▼
GoogleTranslator('en' → 'hi').translate()
→ "आपके पासवर्ड रीसेट के लिए, कृपया निम्न चरणों का पालन करें..."
    │
    ▼
Customer reads response in Hindi
```

### Language Detection Flow

```
Input: "Mein Konto ist gesperrt"
    │
    ▼
langdetect → 'de' (German, confidence: 0.94)
    │
    ├── confidence > 0.8 → proceed with 'de'
    │
    └── confidence < 0.8 → check second candidate
        │
        └── fallback to 'en' if ambiguous
```

**Postconditions:** Customer receives response in their original language. All ticket metadata stored in English.

---

## UC-05: Ticket with Screenshot Attachment

**Actor:** Customer  
**Goal:** Provide visual evidence of the issue  
**Preconditions:** Customer has a screenshot file; issue is complex enough for visual context  
**Trigger:** Customer clicks "Attach Screenshot" and selects a file

### Flow

```
Customer attaches screenshot.png
    │
    ▼
POST /tickets/with-screenshot (multipart/form-data)
    │
    ▼
File saved to uploads/{timestamp}_screenshot.png
    │
    ├──► Ticket saved with screenshot_path field
    │
    └──► Developer alert email
             │
             └──► Screenshot attached as MIME attachment
```

### File Validation

```
Accepted: PNG, JPG, JPEG, GIF, WebP
Max recommended size: 10MB (no hard limit enforced currently)
Storage: Local filesystem uploads/ directory
```

**Postconditions:** Screenshot is saved locally; developer email includes file as attachment.

---

## UC-06: Agent Reviews and Responds to Ticket

**Actor:** Support Agent  
**Goal:** Review incoming tickets and provide human responses  
**Preconditions:** Agent logged into Streamlit dashboard  
**Trigger:** Agent receives developer alert email or checks dashboard

### Flow

```
Agent            Streamlit App         FastAPI          MongoDB
   │                   │                  │                 │
   │─ Open dashboard ─►│                  │                 │
   │                   │─ GET /tickets ──►│                 │
   │                   │                  │─ query all ────►│
   │                   │◄─ ticket list ───│◄─ results ──────│
   │◄─ See all tickets ─│                  │                 │
   │                   │                  │                 │
   │─ Select ticket ──►│                  │                 │
   │                   │─ GET /tickets/id►│                 │
   │◄─ Full details ───│                  │                 │
   │                   │                  │                 │
   │─ Review AI resp ─►│                  │                 │
   │  (approve or edit)│                  │                 │
   │                   │                  │                 │
   │─ Mark resolved ──►│─ PATCH status ──►│                 │
   │                   │                  │─ update ───────►│
   │◄─ Status updated ─│                  │                 │
```

**Postconditions:** Ticket status updated to `resolved`; agent has reviewed AI response.

---

## UC-07: Customer Provides Feedback

**Actor:** Customer  
**Goal:** Improve the AI response quality  
**Preconditions:** Customer has received an AI-generated response  
**Trigger:** Customer rates a response and writes feedback

### Flow

```
Customer              Frontend              FastAPI           Groq LLM
    │                    │                     │                  │
    │─ Rates response ──►│                     │                  │
    │  (e.g., 2/5)       │                     │                  │
    │─ Writes feedback ──►│                    │                  │
    │  "Too generic"      │                     │                  │
    │                     │─ POST /feedback ──►│                  │
    │                     │                     │─ improve_resp ─►│
    │                     │                     │  (original +    │
    │                     │                     │   feedback)     │
    │                     │                     │◄─ improved ─────│
    │                     │                     │─ save to DB     │
    │                     │◄─ improved_response ─│                  │
    │◄─ See improved ─────│                     │                  │
    │   response          │                     │                  │
```

**Postconditions:** Improved response returned to customer; feedback and improvement saved to MongoDB.

---

## UC-08: Admin Analyzes Support Issue

**Actor:** Admin  
**Goal:** Understand the nature and severity of an issue before assigning  
**Preconditions:** Admin has access to Streamlit dashboard  
**Trigger:** New ticket received that needs assessment

### Flow

```
Admin                Streamlit             FastAPI            AI Services
   │                    │                     │                    │
   │─ Enter issue text ►│                     │                    │
   │                    │─ POST /analyze ────►│                    │
   │                    │                     │─ categorize ──────►│
   │                    │                     │─ RAG analyze ─────►│
   │                    │                     │─ similar tickets ──►│
   │                    │◄─ full analysis ────│                    │
   │◄─ See:             │                     │                    │
   │   • Category       │                     │                    │
   │   • Priority       │                     │                    │
   │   • Sentiment      │                     │                    │
   │   • Avg similarity │                     │                    │
   │   • Similar cases  │                     │                    │
```

**Postconditions:** Admin has full context to assign ticket to appropriate team and estimate effort.

---

## UC-09: System Initialization by Developer

**Actor:** Developer  
**Goal:** Set up the system for first use or rebuild the knowledge base  
**Preconditions:** Python environment set up; `.env` configured with API keys  
**Trigger:** First deployment or new data file available

### Flow

```
Developer           CLI (main.py)         Data Pipeline           Disk
    │                    │                     │                    │
    │─ python main.py ──►│                     │                    │
    │   --setup          │                     │                    │
    │                    │─ validate env vars  │                    │
    │                    │─ load CSV ─────────►│                    │
    │                    │                     │─ preprocess data   │
    │                    │                     │─ create documents  │
    │                    │                     │                    │
    │                    │─ embed documents ──►│                    │
    │                    │  (Gemini API,        │                    │
    │                    │   ~30-60s for 2500) │                    │
    │                    │                     │                    │
    │                    │─ build FAISS index ►│                    │
    │                    │                     │─ save to disk ────►│
    │                    │                     │  (faiss_index.bin) │
    │◄─ "Setup complete" ─│                     │                    │
```

### Force Rebuild

```
python main.py --force-rebuild --data new_tickets.csv
    │
    ▼
Skip disk check → rerun full pipeline → overwrite vector_store/
```

**Postconditions:** `vector_store/` directory populated; system ready for queries.

---

## UC-10: Agent Compares Response Candidates

**Actor:** Support Agent  
**Goal:** Select the best-suited AI response for a customer  
**Preconditions:** Issue has been submitted to the system  
**Trigger:** Agent wants to customize the response style

### Flow

```
Agent selects "Response Sampling" in Streamlit dashboard
    │
    ▼
System calls generate_multiple_responses(query, num_candidates=3)
    │
    ├──► Candidate 1: temp=0.3 (Conservative — precise, factual)
    ├──► Candidate 2: temp=0.7 (Balanced — natural, context-aware)
    └──► Candidate 3: temp=1.0 (Creative — empathetic, verbose)
    │
    ▼
Agent reads all three side by side
    │
    ▼
Agent selects or edits preferred response
    │
    ▼
Response sent to customer (manual action by agent)
```

**Postconditions:** Agent has reviewed stylistic variations and chosen the most appropriate response.

---

## UC-11: Admin Updates Ticket Status

**Actor:** Support Agent / Admin  
**Goal:** Track ticket resolution progress  
**Preconditions:** Ticket exists in MongoDB  
**Trigger:** Support agent acts on a ticket

### Status Transitions

```
         open
          │
          ▼
      in_progress
          │
          ▼
       resolved
```

### Flow

```
PATCH /tickets/{ticket_id}/status
Body: { "status": "resolved" }

    │
    ▼
MongoDB: db.tickets.update_one(
    { "ticket_id": ticket_id },
    { "$set": { "status": "resolved", "updated_at": now() } }
)
    │
    ▼
Response: { "ticket_id": "TKT-...", "status": "resolved" }
```

**Postconditions:** Ticket status updated; `updated_at` timestamp refreshed.

---

## UC-12: Customer Tracks Existing Ticket

**Actor:** Customer  
**Goal:** Check the status of a previously submitted ticket  
**Preconditions:** Customer has their email address or ticket ID  
**Trigger:** Customer wants an update on their issue

### Flow

```
GET /tickets/by-email/{email}
    │
    ▼
MongoDB: find all tickets where user_email = email
    │
    ▼
Return: list of tickets with status, category, ai_response
    │
    ▼
Customer sees: TKT-20260420-0042 → Status: in_progress
```

**Postconditions:** Customer has visibility into ticket resolution status.

---

## 15. Edge Cases & Alternate Flows

### EC-01: LLM Rate Limit Hit

```
Groq API → 429 Too Many Requests
    │
    ▼
FastAPI endpoint → HTTP 500
Body: { "detail": "LLM service temporarily unavailable. Please try again." }
    │
    ▼
Ticket NOT created (no partial writes)
Customer sees error message with retry guidance
```

### EC-02: MongoDB Unavailable

```
MongoDBClient.__init__() → ConnectionFailure
    │
    ▼
db = None (assigned in startup)
    │
    ▼
Ticket creation proceeds:
  - categorization: OK (in-memory)
  - response generation: OK (in-memory)
  - ticket save: skipped (no persistence)
  - email: attempted (may still work)
    │
    ▼
Response returned to customer with ticket_id (not persisted)
Warning logged server-side
```

### EC-03: Very Short or Ambiguous Query

```
User submits: "help"
    │
    ▼
RAG retrieves 5 docs (all low similarity ~0.3)
    │
    ▼
LLM prompt includes context but query lacks specificity
    │
    ▼
LLM asks for clarification:
"Could you please describe your issue in more detail? 
For example: What product are you using? What error did you see?"
```

### EC-04: Unsupported Language

```
User writes in Swahili (not in supported language list)
    │
    ▼
langdetect → 'sw'
    │
    ▼
deep-translator: translation may still succeed (Google supports 100+ languages)
    │
    ├── success → normal pipeline
    └── failure → original text passed to LLM
                     │
                     ▼
                 Llama 3.3 has multilingual training data
                 May respond in Swahili natively
```

### EC-05: Empty Audio File

```
POST /transcribe with 0-byte audio
    │
    ▼
Groq Whisper → error
    │
    ▼
transcribe_audio() → returns None
    │
    ▼
Endpoint returns 400: { "detail": "No speech detected in audio" }
```

### EC-06: Duplicate Ticket (Same Issue Same Customer)

```
Customer submits same issue twice
    │
    ▼
No deduplication in current implementation
Two separate ticket records created with different ticket IDs
    │
    ▼
Agent sees both tickets during review
Recommended: agents merge or link duplicates manually
```
