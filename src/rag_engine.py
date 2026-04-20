"""
RAG Engine Module
Retrieval-Augmented Generation for customer support
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from .embeddings import GeminiEmbeddings
from .vector_store import FAISSVectorStore
from .config import Config


class RAGEngine:
    """Retrieval-Augmented Generation Engine for Customer Support"""

    def __init__(
        self,
        embedder: Optional[GeminiEmbeddings] = None,
        vector_store: Optional[FAISSVectorStore] = None,
    ):
        self.embedder = embedder or GeminiEmbeddings()
        self.vector_store = vector_store or FAISSVectorStore()
        self.is_initialized = False

    # ─── Initialisation ──────────────────────────────────────────────────────

    def initialize_from_documents(
        self, documents: List[Dict], text_field: str = "combined_text"
    ):
        """Embed and index a list of document dicts."""
        print("Initializing RAG Engine...")
        docs_with_embeddings = self.embedder.embed_documents(documents, text_field)
        self.vector_store.create_index()
        self.vector_store.add_documents(docs_with_embeddings)
        self.is_initialized = True
        print("RAG Engine initialized successfully")

    def initialize_from_db(self, db_client):
        """
        Load documents from MongoDB knowledge_base collection and build FAISS index.

        Args:
            db_client: MongoDBClient instance
        """
        print("Loading knowledge base from MongoDB...")
        documents = db_client.get_knowledge_docs()
        if not documents:
            raise ValueError(
                "MongoDB knowledge_base collection is empty. "
                "Please seed it first via seed_knowledge_base()."
            )
        self.initialize_from_documents(documents)

    def load_from_disk(self, vector_store_path: str = None):
        """Load a previously saved FAISS index from disk."""
        self.vector_store.load(vector_store_path)
        self.is_initialized = True
        print("RAG Engine loaded from disk")

    def save_to_disk(self, vector_store_path: str = None):
        """Save the FAISS index to disk."""
        self.vector_store.save(vector_store_path)

    # ─── Retrieval ───────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: int = None,
        threshold: float = None,
    ) -> List[Tuple[Dict, float]]:
        """Return (document, score) tuples for the most similar past tickets."""
        if not self.is_initialized:
            raise RuntimeError(
                "RAG Engine not initialized. Call initialize_from_documents() first."
            )

        top_k = top_k or Config.TOP_K_RESULTS
        threshold = threshold if threshold is not None else Config.SIMILARITY_THRESHOLD

        query_embedding = self.embedder.create_query_embedding(query)
        return self.vector_store.search(query_embedding, top_k, threshold)

    def get_context(
        self, query: str, top_k: int = None, include_scores: bool = False
    ) -> str:
        """Return a formatted context string for the LLM prompt."""
        results = self.retrieve(query, top_k)
        if not results:
            return "No relevant context found."

        parts = []
        for i, (doc, score) in enumerate(results, 1):
            header = f"--- Example {i}" + (f" (Similarity: {score:.2f})" if include_scores else "") + " ---"
            parts.append(
                f"{header}\n"
                f"Category: {doc.get('category', 'General')}\n"
                f"Customer Query: {doc.get('instruction', '')}\n"
                f"Support Response: {doc.get('response', '')}\n"
            )
        return "\n".join(parts)

    def get_similar_tickets(self, query: str, top_k: int = 5) -> List[Dict]:
        """Return a list of similar ticket dicts with similarity scores."""
        results = self.retrieve(query, top_k)
        return [
            {
                "id": doc.get("id", ""),
                "instruction": doc.get("instruction", ""),
                "response": doc.get("response", ""),
                "category": doc.get("category", ""),
                "similarity_score": round(score, 4),
            }
            for doc, score in results
        ]

    def analyze_query(self, query: str) -> Dict:
        """Return retrieval statistics for a query (used in analysis tab)."""
        results = self.retrieve(query, top_k=10)
        if not results:
            return {"has_results": False, "message": "No similar tickets found"}

        scores = [score for _, score in results]
        categories = [doc.get("category", "Unknown") for doc, _ in results]

        category_counts: Dict[str, int] = {}
        for cat in categories:
            category_counts[cat] = category_counts.get(cat, 0) + 1

        suggested_category = max(category_counts, key=lambda x: category_counts[x])

        return {
            "has_results": True,
            "num_results": len(results),
            "avg_similarity": float(np.mean(scores)),
            "max_similarity": float(max(scores)),
            "min_similarity": float(min(scores)),
            "suggested_category": suggested_category,
            "category_distribution": category_counts,
        }
