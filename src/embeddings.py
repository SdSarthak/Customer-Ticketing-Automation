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


class GeminiEmbeddings:
    """Class to handle text embeddings using Google Gemini"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.GOOGLE_API_KEY
        if not self.api_key:
            raise ValueError("Google API key is required")

        self.client = genai.Client(api_key=self.api_key)
        self.model = Config.EMBEDDING_MODEL
        self.embedding_dimension = 3072  # gemini-embedding-001 dimension

    def create_embedding(self, text: str) -> np.ndarray:
        if not text or not text.strip():
            return np.zeros(self.embedding_dimension)

        try:
            result = self.client.models.embed_content(
                model=self.model,
                contents=text,
                config=types.EmbedContentConfig(task_type="retrieval_document")
            )
            return np.array(result.embeddings[0].values, dtype=np.float32)
        except Exception as e:
            print(f"⚠️ Error creating embedding: {e}")
            return np.zeros(self.embedding_dimension)

    def create_query_embedding(self, text: str) -> np.ndarray:
        if not text or not text.strip():
            return np.zeros(self.embedding_dimension)

        try:
            result = self.client.models.embed_content(
                model=self.model,
                contents=text,
                config=types.EmbedContentConfig(task_type="retrieval_query")
            )
            return np.array(result.embeddings[0].values, dtype=np.float32)
        except Exception as e:
            print(f"⚠️ Error creating query embedding: {e}")
            return np.zeros(self.embedding_dimension)
    
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
        
        iterator = range(0, len(texts), batch_size)
        if show_progress:
            iterator = tqdm(iterator, desc="Creating embeddings")
        
        for i in iterator:
            batch = texts[i:i + batch_size]
            
            for text in batch:
                embedding = self.create_embedding(text)
                all_embeddings.append(embedding)
                
            # Rate limiting
            time.sleep(0.1)
        
        return np.array(all_embeddings, dtype=np.float32)
    
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
        
        for doc in tqdm(documents, desc="Embedding documents"):
            text = doc.get(text_field, "")
            doc["embedding"] = self.create_embedding(text)
            time.sleep(0.05)  # Rate limiting
        
        print(f"✅ Embeddings created for all documents")
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
