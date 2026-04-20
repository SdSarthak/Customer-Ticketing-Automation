"""
MongoDB Database Module
Handles all ticket and knowledge base persistence
"""

import datetime
from typing import Optional, List, Dict
from pymongo import MongoClient, DESCENDING
from pymongo.errors import ConnectionFailure
from .config import Config


from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

uri = "mongodb+srv://sarthakdoshi2310:sarthak2310@cluster0.qgwygus.mongodb.net/?appName=Cluster0"

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)


class MongoDBClient:
    """MongoDB client for ticket and knowledge base management"""

    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        self.uri = uri or Config.MONGODB_URI
        self.db_name = db_name or Config.MONGODB_DB
        self._client = None
        self._db = None

    def connect(self):
        """Establish connection to MongoDB"""
        try:
            self._client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            self._client.admin.command("ping")
            self._db = self._client[self.db_name]
            return True
        except ConnectionFailure as e:
            raise ConnectionError(
                f"Cannot connect to MongoDB at {self.uri}. "
                "Make sure MongoDB is running or check your MONGODB_URI. "
                f"Error: {e}"
            ) from e

    @property
    def db(self):
        if self._db is None:
            self.connect()
        return self._db

    # ─── Ticket operations ───────────────────────────────────────────────────

    def _generate_ticket_id(self) -> str:
        """Generate a sequential ticket ID like TKT-20260415-0042"""
        today = datetime.datetime.utcnow().strftime("%Y%m%d")
        count = self.db["tickets"].count_documents({}) + 1
        return f"TKT-{today}-{count:04d}"

    def save_ticket(self, ticket: Dict) -> str:
        """
        Save a new support ticket to MongoDB.

        Args:
            ticket: Dict with keys: user_name, user_email, issue_description,
                    category, priority, sentiment, summary, ai_response,
                    screenshot_path (optional), attempt_history (optional),
                    language (optional)

        Returns:
            Generated ticket_id string
        """
        ticket_id = self._generate_ticket_id()
        doc = {
            "ticket_id": ticket_id,
            "user_name": ticket.get("user_name", ""),
            "user_email": ticket.get("user_email", ""),
            "issue_description": ticket.get("issue_description", ""),
            "category": ticket.get("category", "General Inquiry"),
            "priority": ticket.get("priority", "medium"),
            "sentiment": ticket.get("sentiment", "neutral"),
            "summary": ticket.get("summary", ""),
            "ai_response": ticket.get("ai_response", ""),
            "screenshot_path": ticket.get("screenshot_path", None),
            "attempt_history": ticket.get("attempt_history", []),
            "language": ticket.get("language", "en"),
            "status": "open",
            "assigned_to": ticket.get("assigned_to", "Support Team"),
            "created_at": datetime.datetime.utcnow(),
            "updated_at": datetime.datetime.utcnow(),
        }
        self.db["tickets"].insert_one(doc)
        return ticket_id

    def get_ticket(self, ticket_id: str) -> Optional[Dict]:
        """Get a ticket by its ID"""
        doc = self.db["tickets"].find_one({"ticket_id": ticket_id}, {"_id": 0})
        return doc

    def get_tickets_by_email(self, email: str) -> List[Dict]:
        """Get all tickets for a user email"""
        return list(
            self.db["tickets"]
            .find({"user_email": email}, {"_id": 0})
            .sort("created_at", DESCENDING)
        )

    def get_all_tickets(self) -> List[Dict]:
        """Get all tickets (admin view)"""
        return list(
            self.db["tickets"].find({}, {"_id": 0}).sort("created_at", DESCENDING)
        )

    def update_ticket_status(self, ticket_id: str, status: str) -> bool:
        """Update ticket status (open / in_progress / resolved)"""
        result = self.db["tickets"].update_one(
            {"ticket_id": ticket_id},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0

    # ─── Knowledge base operations ───────────────────────────────────────────

    def save_knowledge_docs(self, documents: List[Dict]):
        """
        Bulk insert knowledge base documents (support ticket Q&A pairs).
        Clears existing collection first.
        """
        col = self.db["knowledge_base"]
        col.drop()
        if documents:
            col.insert_many(documents)

    def get_knowledge_docs(self) -> List[Dict]:
        """Retrieve all knowledge base documents"""
        return list(self.db["knowledge_base"].find({}, {"_id": 0}))

    def knowledge_base_count(self) -> int:
        return self.db["knowledge_base"].count_documents({})

    # ─── Feedback operations ─────────────────────────────────────────────────

    def save_feedback(self, feedback: Dict) -> str:
        """Save a feedback record"""
        doc = {
            **feedback,
            "created_at": datetime.datetime.utcnow(),
        }
        result = self.db["feedback"].insert_one(doc)
        return str(result.inserted_id)

    def get_all_feedback(self) -> List[Dict]:
        return list(
            self.db["feedback"].find({}, {"_id": 0}).sort("created_at", DESCENDING)
        )

    def close(self):
        if self._client:
            self._client.close()
