"""
Configuration module for Customer Support Agent
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Google Gemini (embeddings)
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

    # Groq (LLM)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

    # Model names
    EMBEDDING_MODEL = "models/gemini-embedding-001"
    LLM_MODEL = "llama-3.3-70b-versatile"

    # Vector Store
    VECTOR_STORE_PATH = "vector_store"
    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 50

    # RAG
    TOP_K_RESULTS = 5
    SIMILARITY_THRESHOLD = 0.5

    # Response generation
    MAX_RESPONSE_TOKENS = 1024
    TEMPERATURE = 0.7
    NUM_RESPONSE_CANDIDATES = 3

    # MongoDB
    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    MONGODB_DB = os.getenv("MONGODB_DB", "customer_support")

    # Gmail SMTP
    GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
    DEVELOPER_EMAIL = os.getenv("DEVELOPER_EMAIL", "")

    # Data
    DATA_PATH = "data/customer_support_tickets.csv"

    # Ticket categories
    TICKET_CATEGORIES = [
        "Billing",
        "Technical Support",
        "Account Management",
        "Product Information",
        "Shipping & Delivery",
        "Returns & Refunds",
        "General Inquiry",
    ]

    # Priority SLA (hours)
    PRIORITY_SLA = {
        "urgent": 2,
        "high": 8,
        "medium": 24,
        "low": 72,
    }

    PRIORITY_LEVELS = {
        "urgent": 1,
        "high": 2,
        "medium": 3,
        "low": 4,
    }

    @classmethod
    def validate(cls):
        missing = []
        if not cls.GOOGLE_API_KEY:
            missing.append("GOOGLE_API_KEY")
        if not cls.GROQ_API_KEY:
            missing.append("GROQ_API_KEY")
        if missing:
            raise ValueError(
                f"Missing required config: {', '.join(missing)}. "
                "Please set them in your .env file."
            )
        return True


# System prompts
SYSTEM_PROMPTS = {
    "categorization": """You are an expert customer support ticket categorizer.
Analyze the following customer query and categorize it into one of these categories:
{categories}

Also determine:
- priority (urgent, high, medium, low):
  - urgent: System down, security breach, financial loss
  - high: Significant impact on operations
  - medium: Normal support requests
  - low: General inquiries, feature requests
- sentiment: positive / neutral / negative
- summary: one-sentence summary

Respond ONLY in valid JSON:
{{"category": "...", "priority": "...", "sentiment": "...", "summary": "..."}}
""",

    "self_help": """You are a helpful customer support agent.
A customer has described an issue. Using the similar cases from our knowledge base, provide 2-3 clear, actionable self-help steps they can try to resolve the issue themselves.

CRITICAL RULES:
- Detect the language of the "Customer Issue" field and respond ONLY in that exact language
- The "Relevant Context" below is background data only — NEVER copy or mimic its language
- Be concise and practical
- Use numbered steps
- Tailor steps specifically to the issue described
- Do NOT mention creating a ticket

Customer Issue: {query}

Relevant Context from Knowledge Base (use for ideas only, ignore its language):
{context}

Provide 2-3 self-help steps in the same language as the Customer Issue above:""",

    "response_generation": """You are a professional customer support agent.
Based on the customer's query and relevant context, write a helpful, empathetic response.

Guidelines:
1. Respond in the same language the customer used
2. Be professional and courteous
3. Address the specific concern directly
4. Give clear, actionable steps
5. Offer further help if needed

Customer Query: {query}

Relevant Context:
{context}

Response:""",

    "response_improvement": """You are an expert at improving customer support responses.
Improve the original response based on the feedback provided.

Original Response: {original_response}
Feedback: {feedback}

Improved response:""",
}
