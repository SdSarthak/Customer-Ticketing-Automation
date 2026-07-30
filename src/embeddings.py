"""
Embeddings Module
Handles text embedding generation using Google Gemini
"""

from google import genai
from google.genai import types
import numpy as np
from typing import List, Dict, Optional, Union
from tqdm import tqdm
import time

from .config import Config


class EmbeddingError(RuntimeError):
    """
    Raised when the embedding API rejects a request or cannot be reached.

    Only the index-building path lets this surface. The query path keeps
    returning a zero vector so a single bad lookup degrades to "no similar
    tickets found" instead of a 500.
    """


class GeminiEmbeddings:
    """Class to handle text embeddings using Google Gemini"""

    # Consecutive API failures tolerated while embedding a corpus before we
    # conclude the credentials/quota are broken rather than one document.
    FAIL_FAST_THRESHOLD = 3

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.GOOGLE_API_KEY
        if not self.api_key:
            raise ValueError("Google API key is required")

        self.client = genai.Client(api_key=self.api_key)
        self.model = Config.EMBEDDING_MODEL
        self.embedding_dimension = 3072  # gemini-embedding-001 dimension
        self._reset_failure_tracking()

    def _reset_failure_tracking(self):
        """Clear per-corpus failure counters before a fresh embedding run."""
        self._consecutive_failures = 0
        self._failed_total = 0

    def _embed(self, text: str, task_type: str) -> np.ndarray:
        """
        Call the Gemini embedding API, raising EmbeddingError on any failure.

        Blank text is not an error — it has no meaningful embedding, so it maps
        to a zero vector that the vector store knows to skip.
        """
        if not text or not text.strip():
            return np.zeros(self.embedding_dimension, dtype=np.float32)

        try:
            result = self.client.models.embed_content(
                model=self.model,
                contents=text,
                config=types.EmbedContentConfig(task_type=task_type),
            )
            return np.array(result.embeddings[0].values, dtype=np.float32)
        except Exception as e:
            raise EmbeddingError(f"Gemini embedding request failed: {e}") from e

    def create_embedding(self, text: str) -> np.ndarray:
        """Embed a document, returning a zero vector if the API call fails."""
        try:
            return self._embed(text, "retrieval_document")
        except EmbeddingError as e:
            print(f"⚠️ Error creating embedding: {e}")
            return np.zeros(self.embedding_dimension, dtype=np.float32)

    def create_query_embedding(self, text: str) -> np.ndarray:
        """Embed a query, returning a zero vector if the API call fails."""
        try:
            return self._embed(text, "retrieval_query")
        except EmbeddingError as e:
            print(f"⚠️ Error creating query embedding: {e}")
            return np.zeros(self.embedding_dimension, dtype=np.float32)


    def create_embeddings_batch(self, texts: List[str], 
                                batch_size: int = 100,
                                show_progress: bool = True) -> np.ndarray:
        """
        Create embeddings for a batch of texts
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts to process in each batch
            show_progress: Whether to show progress bar
            
        Returns:
            Numpy array of embeddings (shape: n_texts x embedding_dim)
        """
        all_embeddings = []
        self._reset_failure_tracking()

        iterator = range(0, len(texts), batch_size)
        if show_progress:
            iterator = tqdm(iterator, desc="Creating embeddings")

        for i in iterator:
            batch = texts[i:i + batch_size]

            for offset, text in enumerate(batch):
                all_embeddings.append(self._embed_or_fail(text, i + offset, len(texts)))

            # Rate limiting
            time.sleep(0.1)

        return np.array(all_embeddings, dtype=np.float32)

    def _embed_or_fail(self, text: str, position: int, total: int) -> np.ndarray:
        """
        Embed one corpus document, tracking failures across the whole run.

        An expired key or exhausted quota fails on every call. Swallowing that
        would build an index of zero vectors that saves cleanly and then matches
        nothing forever, so give up once FAIL_FAST_THRESHOLD calls in a row fail
        rather than burning the rest of the corpus on doomed requests.
        """
        try:
            embedding = self._embed(text, "retrieval_document")
        except EmbeddingError as e:
            self._consecutive_failures += 1
            self._failed_total += 1
            if self._consecutive_failures >= self.FAIL_FAST_THRESHOLD:
                raise EmbeddingError(
                    f"{self._consecutive_failures} consecutive embedding calls failed "
                    f"at document {position + 1}/{total}. Aborting so a corpus of "
                    f"zero vectors is not indexed — check GOOGLE_API_KEY and quota. "
                    f"Last error: {e}"
                ) from e
            print(f"⚠️ Skipping document {position + 1}/{total}: {e}")
            return np.zeros(self.embedding_dimension, dtype=np.float32)

        self._consecutive_failures = 0
        return embedding

    def embed_documents(self, documents: List[Dict],
                       text_field: str = "combined_text") -> List[Dict]:
        """
        Add embeddings to document dictionaries
        
        Args:
            documents: List of document dictionaries
            text_field: Field containing text to embed
            
        Returns:
            Documents with added 'embedding' field
        """
        print(f"🔄 Creating embeddings for {len(documents)} documents...")

        total = len(documents)
        self._reset_failure_tracking()

        for position, doc in enumerate(tqdm(documents, desc="Embedding documents")):
            text = doc.get(text_field, "")
            doc["embedding"] = self._embed_or_fail(text, position, total)
            time.sleep(0.05)  # Rate limiting

        if self._failed_total:
            print(
                f"⚠️ {self._failed_total}/{total} documents could not be embedded "
                f"and will be left out of the index."
            )
        else:
            print("✅ Embeddings created for all documents")
        return documents


    @staticmethod
    def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two vectors
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Cosine similarity score
        """
        if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
            return 0.0
        
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))


def create_embeddings_from_documents(documents: List[Dict], 
                                     api_key: Optional[str] = None) -> List[Dict]:
    """
    Convenience function to create embeddings from documents
    
    Args:
        documents: List of document dictionaries
        api_key: Optional Google API key
        
    Returns:
        Documents with embeddings
    """
    embedder = GeminiEmbeddings(api_key)
    return embedder.embed_documents(documents)


if __name__ == "__main__":
    # Test embeddings
    embedder = GeminiEmbeddings()
    
    test_texts = [
        "How do I reset my password?",
        "I want to cancel my subscription",
        "When will my order arrive?"
    ]
    
    print("Testing Gemini Embeddings...")
    for text in test_texts:
        embedding = embedder.create_embedding(text)
        print(f"Text: '{text[:30]}...' -> Embedding shape: {embedding.shape}")
