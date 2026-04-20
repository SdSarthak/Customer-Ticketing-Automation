"""
Vector Store Module
Handles FAISS vector database operations for efficient similarity search
"""

import faiss
import numpy as np
import pickle
import os
from typing import List, Dict, Optional, Tuple
from .config import Config


class FAISSVectorStore:
    """Class to handle FAISS vector database operations"""
    
    def __init__(self, embedding_dimension: int = 3072):
        """
        Initialize FAISS Vector Store

        Args:
            embedding_dimension: Dimension of embeddings (3072 for gemini-embedding-001)
        """
        self.embedding_dimension = embedding_dimension
        self.index = None
        self.documents = []
        self.id_to_doc = {}
        
    def create_index(self, use_gpu: bool = False):
        """
        Create a new FAISS index
        
        Args:
            use_gpu: Whether to use GPU acceleration (requires faiss-gpu)
        """
        # Using IndexFlatIP for inner product (cosine similarity with normalized vectors)
        self.index = faiss.IndexFlatIP(self.embedding_dimension)
        
        # Optionally wrap with IDMap to track document IDs
        self.index = faiss.IndexIDMap(self.index)
        
        print(f"✅ Created FAISS index with dimension {self.embedding_dimension}")
        
    def add_documents(self, documents: List[Dict]):
        """
        Add documents with embeddings to the vector store
        
        Args:
            documents: List of document dictionaries with 'embedding' field
        """
        if self.index is None:
            self.create_index()
        
        embeddings = []
        ids = []
        
        for i, doc in enumerate(documents):
            if "embedding" not in doc:
                raise ValueError(f"Document {i} missing 'embedding' field")
            
            embedding = doc["embedding"]
            
            # Normalize for cosine similarity
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            
            embeddings.append(embedding)
            ids.append(i)
            
            # Store document mapping
            self.id_to_doc[i] = doc
            self.documents.append(doc)
        
        # Convert to numpy arrays
        embeddings_array = np.array(embeddings, dtype=np.float32)
        ids_array = np.array(ids, dtype=np.int64)
        
        # Add to index
        self.index.add_with_ids(embeddings_array, ids_array)
        
        print(f"✅ Added {len(documents)} documents to vector store")
        print(f"📊 Total documents in store: {self.index.ntotal}")
        
    def search(self, query_embedding: np.ndarray, 
               top_k: int = 5,
               threshold: float = 0.0) -> List[Tuple[Dict, float]]:
        """
        Search for similar documents
        
        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            threshold: Minimum similarity score threshold
            
        Returns:
            List of (document, score) tuples
        """
        if self.index is None or self.index.ntotal == 0:
            print("⚠️ Vector store is empty")
            return []
        
        # Normalize query embedding
        norm = np.linalg.norm(query_embedding)
        if norm > 0:
            query_embedding = query_embedding / norm
        
        # Reshape for FAISS
        query_embedding = query_embedding.reshape(1, -1).astype(np.float32)
        
        # Search
        scores, indices = self.index.search(query_embedding, top_k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:  # FAISS returns -1 for not found
                continue
            if score < threshold:
                continue
            
            doc = self.id_to_doc.get(idx, {})
            results.append((doc, float(score)))
        
        return results
    
    def save(self, path: str = None):
        """
        Save the vector store to disk
        
        Args:
            path: Directory path to save the store
        """
        path = path or Config.VECTOR_STORE_PATH
        os.makedirs(path, exist_ok=True)
        
        # Save FAISS index
        index_path = os.path.join(path, "faiss_index.bin")
        faiss.write_index(self.index, index_path)
        
        # Save documents and mappings
        metadata_path = os.path.join(path, "metadata.pkl")
        metadata = {
            "documents": self.documents,
            "id_to_doc": self.id_to_doc,
            "embedding_dimension": self.embedding_dimension
        }
        with open(metadata_path, "wb") as f:
            pickle.dump(metadata, f)
        
        print(f"✅ Vector store saved to {path}")
        
    def load(self, path: str = None):
        """
        Load the vector store from disk
        
        Args:
            path: Directory path to load the store from
        """
        path = path or Config.VECTOR_STORE_PATH
        
        # Load FAISS index
        index_path = os.path.join(path, "faiss_index.bin")
        if not os.path.exists(index_path):
            raise FileNotFoundError(f"Index file not found: {index_path}")
        
        self.index = faiss.read_index(index_path)
        
        # Load documents and mappings
        metadata_path = os.path.join(path, "metadata.pkl")
        with open(metadata_path, "rb") as f:
            metadata = pickle.load(f)
        
        self.documents = metadata["documents"]
        self.id_to_doc = metadata["id_to_doc"]
        self.embedding_dimension = metadata["embedding_dimension"]
        
        print(f"✅ Vector store loaded from {path}")
        print(f"📊 Total documents: {self.index.ntotal}")
        
    def clear(self):
        """Clear the vector store"""
        self.create_index()
        self.documents = []
        self.id_to_doc = {}
        print("✅ Vector store cleared")
        
    def get_stats(self) -> Dict:
        """
        Get statistics about the vector store
        
        Returns:
            Dictionary with store statistics
        """
        return {
            "total_documents": self.index.ntotal if self.index else 0,
            "embedding_dimension": self.embedding_dimension,
            "index_type": type(self.index).__name__ if self.index else None
        }


def create_vector_store_from_documents(documents: List[Dict], 
                                       save_path: Optional[str] = None) -> FAISSVectorStore:
    """
    Convenience function to create and optionally save a vector store
    
    Args:
        documents: List of documents with embeddings
        save_path: Optional path to save the store
        
    Returns:
        Configured FAISSVectorStore instance
    """
    store = FAISSVectorStore()
    store.create_index()
    store.add_documents(documents)
    
    if save_path:
        store.save(save_path)
    
    return store


if __name__ == "__main__":
    # Test vector store
    print("Testing FAISS Vector Store...")
    
    # Create dummy documents with embeddings
    test_docs = [
        {"id": "1", "text": "Test document 1", "embedding": np.random.rand(768).astype(np.float32)},
        {"id": "2", "text": "Test document 2", "embedding": np.random.rand(768).astype(np.float32)},
        {"id": "3", "text": "Test document 3", "embedding": np.random.rand(768).astype(np.float32)},
    ]
    
    store = FAISSVectorStore()
    store.create_index()
    store.add_documents(test_docs)
    
    # Test search
    query = np.random.rand(768).astype(np.float32)
    results = store.search(query, top_k=2)
    
    print(f"\nSearch results:")
    for doc, score in results:
        print(f"  Doc ID: {doc.get('id')}, Score: {score:.4f}")
    
    # Test stats
    stats = store.get_stats()
    print(f"\nStore stats: {stats}")
