# System Architecture Diagrams

## Fig. 3.1 - Three-Tier System Architecture

### Mermaid Code (Render at https://mermaid.live/)

```mermaid
flowchart TB
    subgraph PL["Presentation Layer"]
        direction LR
        CP["Customer Portal<br/>(HTML5 + Vanilla JS)"]
        AD["Admin Dashboard<br/>(Streamlit)"]
    end

    subgraph AL["Application Layer (FastAPI + Uvicorn)"]
        direction TB

        subgraph API["REST API Endpoints"]
            EP1["/status"]
            EP2["/self-help"]
            EP3["/tickets"]
            EP4["/voice-chat"]
            EP5["/transcribe"]
            EP6["/feedback"]
            EP7["/analyze"]
        end

        subgraph CORE["Core Services"]
            SH["Self-Help<br/>Engine"]
            TE["Ticket<br/>Enrichment"]
            RAG["RAG<br/>Pipeline"]
            ML["Multilingual<br/>Processor"]
            VC["Voice<br/>Controller"]
        end

        subgraph AI["AI Components"]
            LLM["Groq LLM Client<br/>(Llama 3.3 70B)"]
            EMB["Gemini Embeddings<br/>(3072-dim)"]
            VS["FAISS Vector Store<br/>(IndexFlatIP)"]
        end

        subgraph SUPPORT["Support Services"]
            TRANS["Translation Service<br/>(deep-translator)"]
            LANG["Language Detector<br/>(langdetect)"]
            STT["Speech-to-Text<br/>(Groq Whisper)"]
            TTS["Text-to-Speech<br/>(pyttsx3)"]
            EMAIL["Email Service<br/>(SMTP/Gmail)"]
        end
    end

    subgraph DL["Persistence Layer"]
        direction LR
        MONGO[("MongoDB<br/>Tickets, KB, Feedback")]
        FAISS[("FAISS Index<br/>.index + .pkl")]
        FILES[("File Storage<br/>/uploads/")]
    end

    subgraph EXT["External Services"]
        direction LR
        GROQ_API["Groq API"]
        GEMINI_API["Gemini API"]
        GMAIL["Gmail SMTP"]
    end

    %% Connections
    CP --> API
    AD --> API

    API --> CORE
    CORE --> AI
    CORE --> SUPPORT

    AI --> MONGO
    AI --> FAISS
    SUPPORT --> FILES

    LLM -.-> GROQ_API
    EMB -.-> GEMINI_API
    STT -.-> GROQ_API
    EMAIL -.-> GMAIL

    %% Styling
    classDef presentation fill:#E3F2FD,stroke:#1976D2
    classDef application fill:#E8F5E9,stroke:#388E3C
    classDef data fill:#FFF3E0,stroke:#F57C00
    classDef external fill:#FCE4EC,stroke:#C2185B

    class CP,AD presentation
    class API,CORE,AI,SUPPORT application
    class MONGO,FAISS,FILES data
    class GROQ_API,GEMINI_API,GMAIL external
```

---

## Alternative Architecture Diagram (Detailed)

```mermaid
graph TB
    subgraph CLIENT["Client Layer"]
        BROWSER["Web Browser"]
        MIC["Microphone"]
        SPEAKER["Speaker"]
    end

    subgraph FRONTEND["Frontend Applications"]
        PORTAL["Customer Portal<br/>HTML5 + CSS3 + JS"]
        STREAMLIT["Admin Dashboard<br/>Streamlit"]
    end

    subgraph GATEWAY["API Gateway"]
        FASTAPI["FastAPI Server<br/>Uvicorn ASGI"]
    end

    subgraph SERVICES["Microservices"]
        direction TB

        SELFHELP["Self-Help Service"]
        TICKET["Ticket Service"]
        VOICE["Voice Service"]
        FEEDBACK["Feedback Service"]
        ANALYSIS["Analysis Service"]
    end

    subgraph AI_LAYER["AI/ML Layer"]
        direction LR

        subgraph NLU["Natural Language Understanding"]
            GROQ["Groq LLM<br/>Llama 3.3 70B"]
            WHISPER["Groq Whisper<br/>STT"]
        end

        subgraph RETRIEVAL["Retrieval System"]
            GEMINI["Gemini<br/>Embeddings"]
            FAISS_IDX["FAISS<br/>Vector Index"]
        end

        subgraph NLG["Natural Language Generation"]
            RESPONSE["Response<br/>Generator"]
            TTS_ENG["pyttsx3<br/>TTS Engine"]
        end

        subgraph NLP["NLP Utilities"]
            LANGDET["langdetect"]
            TRANS["deep-translator"]
        end
    end

    subgraph DATA["Data Layer"]
        MONGODB[("MongoDB")]
        FAISS_FILE[("FAISS Files")]
        UPLOADS[("File Storage")]
    end

    %% Client to Frontend
    BROWSER --> PORTAL
    BROWSER --> STREAMLIT
    MIC --> PORTAL
    SPEAKER --> PORTAL

    %% Frontend to Gateway
    PORTAL --> FASTAPI
    STREAMLIT --> FASTAPI

    %% Gateway to Services
    FASTAPI --> SELFHELP
    FASTAPI --> TICKET
    FASTAPI --> VOICE
    FASTAPI --> FEEDBACK
    FASTAPI --> ANALYSIS

    %% Services to AI Layer
    SELFHELP --> NLU
    SELFHELP --> RETRIEVAL
    TICKET --> NLU
    TICKET --> NLP
    VOICE --> WHISPER
    VOICE --> TTS_ENG
    ANALYSIS --> RETRIEVAL

    %% AI Layer to Data
    RETRIEVAL --> FAISS_FILE
    GROQ --> MONGODB

    %% Services to Data
    TICKET --> MONGODB
    FEEDBACK --> MONGODB
    VOICE --> UPLOADS
```

---

## Component Interaction Flow

```mermaid
sequenceDiagram
    participant U as User
    participant P as Portal
    participant A as API
    participant L as LLM
    participant V as Vector Store
    participant D as Database

    U->>P: Submit Issue
    P->>A: POST /self-help
    A->>V: Search Similar Cases
    V-->>A: Context Documents
    A->>L: Generate Response
    L-->>A: AI Response
    A-->>P: Troubleshooting Steps
    P-->>U: Display Steps

    alt Issue Not Resolved
        U->>P: Create Ticket
        P->>A: POST /tickets
        A->>L: Categorize + Prioritize
        L-->>A: Metadata
        A->>D: Save Ticket
        D-->>A: Ticket ID
        A-->>P: Confirmation
        P-->>U: Show Ticket ID
    end
```
