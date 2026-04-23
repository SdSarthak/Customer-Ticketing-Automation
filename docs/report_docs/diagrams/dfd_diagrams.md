# Data Flow Diagrams (DFD)

## Fig. 3.6 - Level 0 DFD (Context Diagram)

### Mermaid Code

```mermaid
flowchart LR
    subgraph EXTERNAL_ENTITIES
        C((Customer))
        A((Support Agent))
        D((Developer))
    end

    subgraph EXTERNAL_SYSTEMS
        GROQ[/"Groq API"/]
        GEMINI[/"Gemini API"/]
        GMAIL[/"Gmail SMTP"/]
    end

    SYSTEM[["AI Customer Support<br/>Agent System"]]

    %% Customer Interactions
    C -->|Issue Description| SYSTEM
    C -->|Voice Input| SYSTEM
    C -->|Ticket Details| SYSTEM
    C -->|Feedback| SYSTEM
    SYSTEM -->|Troubleshooting Steps| C
    SYSTEM -->|Voice Response| C
    SYSTEM -->|Ticket Confirmation| C
    SYSTEM -->|Email Notification| C

    %% Agent Interactions
    A -->|Login Credentials| SYSTEM
    A -->|Status Updates| SYSTEM
    A -->|Response Selection| SYSTEM
    SYSTEM -->|Ticket Queue| A
    SYSTEM -->|AI Analysis| A
    SYSTEM -->|Response Samples| A

    %% Developer Interactions
    D -->|System Commands| SYSTEM
    SYSTEM -->|System Health| D
    SYSTEM -->|Alert Emails| D

    %% External System Interactions
    SYSTEM <-->|LLM Requests/Responses| GROQ
    SYSTEM <-->|Embedding Requests/Vectors| GEMINI
    SYSTEM -->|Email Messages| GMAIL
```

---

## Fig. 3.7 - Level 1 DFD (Detailed Data Flow)

```mermaid
flowchart TB
    %% External Entities
    C((Customer))
    A((Agent))

    %% Data Stores
    D1[(D1: Tickets)]
    D2[(D2: Knowledge Base)]
    D3[(D3: FAISS Index)]
    D4[(D4: Feedback)]
    D5[(D5: File Storage)]

    %% Processes
    P1[["1.0<br/>Process<br/>Self-Help"]]
    P2[["2.0<br/>Create<br/>Ticket"]]
    P3[["3.0<br/>Process<br/>Voice"]]
    P4[["4.0<br/>Manage<br/>Tickets"]]
    P5[["5.0<br/>Generate<br/>Responses"]]
    P6[["6.0<br/>Process<br/>Feedback"]]

    %% Customer to Process flows
    C -->|Issue Description| P1
    C -->|Ticket Form Data| P2
    C -->|Audio Recording| P3
    C -->|Rating & Comments| P6

    %% Process to Customer flows
    P1 -->|Troubleshooting Steps| C
    P2 -->|Ticket Confirmation| C
    P3 -->|Audio Response| C

    %% Agent flows
    A -->|Filter Criteria| P4
    A -->|Sample Request| P5
    A -->|Status Update| P4
    P4 -->|Ticket List| A
    P5 -->|Response Options| A

    %% Internal Process flows
    P1 -->|Query| D3
    D3 -->|Similar Docs| P1
    P1 -->|Context| D2

    P2 -->|New Ticket| D1
    P2 -->|Screenshot| D5
    P2 -->|Query| D3
    D3 -->|Context| P2

    P3 -->|Transcribed Text| P1

    P4 -->|Read/Write| D1

    P5 -->|Query| D3
    P5 -->|Context| D2

    P6 -->|Store| D4
    D4 -->|Feedback Data| P5
```

---

## Level 1 DFD - Process Decomposition

### Process 1.0: Self-Help Resolution

```mermaid
flowchart LR
    subgraph "1.0 Process Self-Help"
        P1_1["1.1<br/>Detect<br/>Language"]
        P1_2["1.2<br/>Translate<br/>to English"]
        P1_3["1.3<br/>Generate<br/>Embedding"]
        P1_4["1.4<br/>Search<br/>Similar Cases"]
        P1_5["1.5<br/>Generate<br/>Response"]
        P1_6["1.6<br/>Translate<br/>Response"]
    end

    IN[/Issue Description/]
    OUT[/Troubleshooting Steps/]
    D3[(FAISS Index)]
    GROQ[/Groq LLM/]
    GEMINI[/Gemini API/]

    IN --> P1_1
    P1_1 -->|Language Code| P1_2
    P1_2 -->|English Text| P1_3
    P1_3 --> GEMINI
    GEMINI -->|Embedding| P1_4
    P1_4 <--> D3
    P1_4 -->|Context Docs| P1_5
    P1_5 --> GROQ
    GROQ -->|Generated Text| P1_6
    P1_6 --> OUT
```

### Process 2.0: Create Ticket

```mermaid
flowchart TB
    subgraph "2.0 Create Ticket"
        P2_1["2.1<br/>Validate<br/>Input"]
        P2_2["2.2<br/>Save<br/>Screenshot"]
        P2_3["2.3<br/>AI<br/>Enrichment"]
        P2_4["2.4<br/>Generate<br/>Ticket ID"]
        P2_5["2.5<br/>Save<br/>Ticket"]
        P2_6["2.6<br/>Send<br/>Notifications"]
    end

    IN[/Ticket Form/]
    FILE[/Screenshot/]
    OUT[/Confirmation/]
    D1[(Tickets DB)]
    D5[(File Storage)]
    EMAIL[/Email Service/]
    GROQ[/Groq LLM/]

    IN --> P2_1
    FILE --> P2_2
    P2_1 --> P2_3
    P2_2 --> D5
    P2_3 --> GROQ
    GROQ -->|Category, Priority,<br/>Sentiment, Summary| P2_4
    P2_4 --> P2_5
    P2_5 --> D1
    P2_5 --> P2_6
    P2_6 --> EMAIL
    P2_6 --> OUT
```

### Process 3.0: Voice Processing

```mermaid
flowchart LR
    subgraph "3.0 Process Voice"
        P3_1["3.1<br/>Validate<br/>Audio"]
        P3_2["3.2<br/>Transcribe<br/>(Whisper)"]
        P3_3["3.3<br/>Process<br/>Self-Help"]
        P3_4["3.4<br/>Synthesize<br/>Speech"]
    end

    IN[/Audio File/]
    OUT[/Audio Response/]
    WHISPER[/Groq Whisper/]
    TTS[/pyttsx3/]

    IN --> P3_1
    P3_1 --> P3_2
    P3_2 --> WHISPER
    WHISPER -->|Transcription| P3_3
    P3_3 -->|Text Response| P3_4
    P3_4 --> TTS
    TTS --> OUT
```

---

## Data Dictionary

| Data Flow | Description | Composition |
|-----------|-------------|-------------|
| Issue Description | Customer's problem statement | Text (1-2000 chars), Language (auto-detected) |
| Ticket Form | Complete ticket submission | Email, Name, Issue, Screenshot (optional) |
| Audio Recording | Voice input from customer | WAV/MP3/WebM file, max 10MB |
| Troubleshooting Steps | AI-generated resolution steps | 2-3 numbered steps, translated if needed |
| Ticket Confirmation | Created ticket details | Ticket ID, Category, Priority, SLA, Status |
| Response Samples | Multiple AI response options | 3 responses at temps 0.3, 0.7, 1.0 |
| Context Docs | Retrieved similar cases | Top-k documents from FAISS search |
| Embedding | Vector representation | 3072-dimensional float array |
