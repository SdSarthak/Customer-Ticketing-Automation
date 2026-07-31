"""
MongoDB Database Module
Handles all ticket and knowledge base persistence
"""

import datetime
import re
from typing import Optional, List, Dict
from pymongo import MongoClient, DESCENDING, ASCENDING, ReturnDocument
from pymongo.errors import ConnectionFailure, DuplicateKeyError, PyMongoError
from .config import Config


def _redact_uri(uri: str) -> str:
    """Strip credentials out of a Mongo URI so it is safe to log."""
    return re.sub(r"://[^/@]+@", "://<credentials>@", uri or "")


# Listing endpoints are paged. Without a cap a single request loads every
# ticket ever filed into memory and serialises it into one JSON response.
DEFAULT_PAGE_SIZE = 200
MAX_PAGE_SIZE = 1000


def _page_size(limit) -> int:
    """Clamp a caller-supplied page size into a sane range."""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_PAGE_SIZE
    if limit < 1:
        return DEFAULT_PAGE_SIZE
    return min(limit, MAX_PAGE_SIZE)


def _utcnow() -> datetime.datetime:
    """Timezone-aware UTC now (datetime.utcnow() is deprecated)."""
    return datetime.datetime.now(datetime.timezone.utc)


class MongoDBClient:
    """MongoDB client for ticket and knowledge base management"""

    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        # Fall back to config only when the argument is omitted (see EmailService)
        self.uri = Config.MONGODB_URI if uri is None else uri
        self.db_name = Config.MONGODB_DB if db_name is None else db_name
        self._client = None
        self._db = None

    def connect(self):
        """
        Establish connection to MongoDB and ensure indexes exist.

        A MongoClient starts background monitor threads and sockets as soon as
        it is constructed, so a failed handshake has to close it explicitly.
        Dropping the reference instead leaked a monitor thread per attempt —
        and `db` retries connect() on every property access, so a Mongo-less
        deployment accumulated them for the life of the process.
        """
        client = None
        try:
            client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            client.admin.command("ping")
            self._client = client
            self._db = client[self.db_name]
            self._ensure_indexes()
            return True
        except Exception as e:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
            self._client = None
            self._db = None
            if isinstance(e, ConnectionFailure):
                raise ConnectionError(
                    f"Cannot connect to MongoDB at {_redact_uri(self.uri)}. "
                    "Make sure MongoDB is running or check your MONGODB_URI. "
                    f"Error: {e}"
                ) from e
            if isinstance(e, PyMongoError):
                raise ConnectionError(
                    f"MongoDB URI {_redact_uri(self.uri)} was rejected: {e}"
                ) from e
            raise

    def _ensure_indexes(self):
        """Create the indexes the ticket queries rely on (idempotent)."""
        try:
            tickets = self._db["tickets"]
            tickets.create_index([("ticket_id", ASCENDING)], unique=True)
            tickets.create_index([("user_email", ASCENDING), ("created_at", DESCENDING)])
            tickets.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
            self._db["feedback"].create_index([("created_at", DESCENDING)])
        except PyMongoError as e:
            print(f"WARNING: could not create MongoDB indexes — {e}")

    @property
    def db(self):
        if self._db is None:
            self.connect()
        return self._db

    # ─── Ticket operations ───────────────────────────────────────────────────

    def _generate_ticket_id(self) -> str:
        """
        Generate a sequential ticket ID like TKT-20260415-0042.

        Uses an atomic findAndModify on a per-day counter document so two
        concurrent requests can never be handed the same number (a plain
        count_documents() would race).
        """
        today = _utcnow().strftime("%Y%m%d")
        counter = self.db["counters"].find_one_and_update(
            {"_id": f"tickets-{today}"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return f"TKT-{today}-{counter['seq']:04d}"

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
        now = _utcnow()
        base_doc = {
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
            "created_at": now,
            "updated_at": now,
        }

        # The unique index on ticket_id is the final guard: if a legacy
        # count-based ID collides with an existing row, take the next one.
        for _ in range(5):
            ticket_id = self._generate_ticket_id()
            try:
                self.db["tickets"].insert_one({"ticket_id": ticket_id, **base_doc})
                return ticket_id
            except DuplicateKeyError:
                continue
        raise RuntimeError("Could not allocate a unique ticket ID after 5 attempts")

    def get_ticket(self, ticket_id: str) -> Optional[Dict]:
        """Get a ticket by its ID"""
        doc = self.db["tickets"].find_one({"ticket_id": ticket_id}, {"_id": 0})
        return doc

    def get_tickets_by_email(self, email: str, limit: int = DEFAULT_PAGE_SIZE) -> List[Dict]:
        """Get a customer's most recent tickets, newest first."""
        return list(
            self.db["tickets"]
            .find({"user_email": email}, {"_id": 0})
            .sort("created_at", DESCENDING)
            .limit(_page_size(limit))
        )

    def get_all_tickets(self, limit: int = DEFAULT_PAGE_SIZE, skip: int = 0) -> List[Dict]:
        """
        Get the most recent tickets (admin view).

        Bounded by default: an unlimited find() materialises the whole
        collection into a list and ships it to the browser in one response,
        which stops working long before the database does.
        """
        return list(
            self.db["tickets"]
            .find({}, {"_id": 0})
            .sort("created_at", DESCENDING)
            .skip(max(int(skip), 0))
            .limit(_page_size(limit))
        )

    def update_ticket_status(self, ticket_id: str, status: str) -> bool:
        """
        Update ticket status (open / in_progress / resolved).

        Returns True when the ticket exists — re-setting the same status is
        still a success, so this checks matched_count rather than
        modified_count (which would report a no-op update as "not found").
        """
        update = {"status": status, "updated_at": _utcnow()}
        if status == "resolved":
            update["resolved_at"] = _utcnow()
        result = self.db["tickets"].update_one({"ticket_id": ticket_id}, {"$set": update})
        return result.matched_count > 0

    def get_ticket_stats(self) -> Dict:
        """
        Aggregate ticket counts for the admin dashboard.

        Returns:
            Dict with total plus by_status / by_priority / by_category maps.
        """
        tickets = self.db["tickets"]

        def _group(field: str) -> Dict[str, int]:
            cursor = tickets.aggregate(
                [{"$group": {"_id": f"${field}", "count": {"$sum": 1}}}]
            )
            return {(row["_id"] or "unknown"): row["count"] for row in cursor}

        return {
            "total": tickets.count_documents({}),
            "by_status": _group("status"),
            "by_priority": _group("priority"),
            "by_category": _group("category"),
        }

    # ─── Knowledge base operations ───────────────────────────────────────────

    def save_knowledge_docs(self, documents: List[Dict]):
        """
        Bulk insert knowledge base documents (support ticket Q&A pairs).
        Clears existing collection first.

        Embedding vectors are stripped before insert — they are numpy arrays
        that BSON cannot encode, and the FAISS index on disk already owns them.
        """
        col = self.db["knowledge_base"]
        col.drop()
        if not documents:
            return
        col.insert_many(
            [{k: v for k, v in doc.items() if k != "embedding"} for doc in documents]
        )

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
            "created_at": _utcnow(),
        }
        result = self.db["feedback"].insert_one(doc)
        return str(result.inserted_id)

    def get_all_feedback(self, limit: int = DEFAULT_PAGE_SIZE) -> List[Dict]:
        return list(
            self.db["feedback"]
            .find({}, {"_id": 0})
            .sort("created_at", DESCENDING)
            .limit(_page_size(limit))
        )

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
