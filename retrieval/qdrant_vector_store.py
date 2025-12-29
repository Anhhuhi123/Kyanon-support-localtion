from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
import numpy as np
from typing import List, Tuple, Optional
from config.config import Config
import uuid
import time

class QdrantVectorStore:
    """Qdrant-based vector store for similarity search"""
    
    def __init__(self):
        """Initialize Qdrant vector store"""
        self.dimension = Config.VECTOR_DIMENSION
        self.collection_name = Config.QDRANT_COLLECTION_NAME
        self.client = None
        self.texts = []  # Local cache for texts (optional, for compatibility)
        
        # Initialize Qdrant client
        self._initialize_client()
        
    def _initialize_client(self):
        """Initialize Qdrant client and create collection if needed"""
        try:
            print(f"Connecting to Qdrant at {Config.QDRANT_URL}...")
            self.client = QdrantClient(
                url=Config.QDRANT_URL,
                api_key=Config.QDRANT_API_KEY,
                timeout=300  # 5 minutes timeout for large uploads
            )
            
            # Check if collection exists, create if not
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                print(f"Creating collection '{self.collection_name}'...")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.dimension,
                        distance=Distance.COSINE
                    )
                )
                print(f"✓ Collection '{self.collection_name}' created successfully!")
            else:
                print(f"✓ Using existing collection '{self.collection_name}'")
                
        except Exception as e:
            print(f"Error initializing Qdrant client: {e}")
            raise
    
    def create_index(self):
        """Create/recreate collection (for compatibility with FAISS interface)"""
        try:
            # Delete existing collection if exists
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name in collection_names:
                self.client.delete_collection(collection_name=self.collection_name)
                print(f"Deleted existing collection '{self.collection_name}'")
            
            # Create new collection
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.dimension,
                    distance=Distance.COSINE
                )
            )
            print(f"Created new Qdrant collection '{self.collection_name}' with dimension {self.dimension}")
            
        except Exception as e:
            print(f"Error creating collection: {e}")
            raise
    
    def add_embeddings(self, embeddings: np.ndarray, texts: List[str], metadata: Optional[List[dict]] = None, batch_size: int = 50):
        """
        Add embeddings and corresponding texts to Qdrant in batches
        
        Args:
            embeddings: numpy array of embeddings
            texts: list of corresponding text chunks
            metadata: optional list of metadata dicts for each text
            batch_size: number of points to upload per batch (default 50 for stability with large uploads)
        """
        try:
            embeddings = embeddings.astype('float32')
            total_embeddings = len(embeddings)
            
            print(f"Uploading {total_embeddings} embeddings to Qdrant in batches of {batch_size}...")
            
            # Process in batches
            for batch_start in range(0, total_embeddings, batch_size):
                batch_end = min(batch_start + batch_size, total_embeddings)
                batch_embeddings = embeddings[batch_start:batch_end]
                batch_texts = texts[batch_start:batch_end]
                batch_metadata = metadata[batch_start:batch_end] if metadata else None
                
                # Prepare points for this batch
                points = []
                for i, (embedding, text) in enumerate(zip(batch_embeddings, batch_texts)):
                    point_id = str(uuid.uuid4())
                    
                    payload = {
                        "text": text,
                        "index": len(self.texts) + batch_start + i
                    }
                    
                    # Add metadata if provided
                    if batch_metadata and i < len(batch_metadata):
                        payload.update(batch_metadata[i])
                    
                    points.append(
                        PointStruct(
                            id=point_id,
                            vector=embedding.tolist(),
                            payload=payload
                        )
                    )
                
                # Upload this batch to Qdrant with retry logic
                max_retries = 3
                retry_delay = 2  # seconds
                
                for attempt in range(max_retries):
                    try:
                        self.client.upsert(
                            collection_name=self.collection_name,
                            points=points
                        )
                        break  # Success, exit retry loop
                    except Exception as e:
                        if attempt < max_retries - 1:
                            print(f"  ⚠️  Upload failed (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                        else:
                            raise  # Final attempt failed, raise error
                
                # Update local text cache
                self.texts.extend(batch_texts)
                
                batch_num = (batch_start // batch_size) + 1
                total_batches = (total_embeddings + batch_size - 1) // batch_size
                print(f"  ✓ Uploaded batch {batch_num}/{total_batches} ({batch_end}/{total_embeddings} embeddings)")
                
                # Small delay between batches to avoid overwhelming the server
                if batch_end < total_embeddings:
                    time.sleep(0.5)
            
            print(f"✓ Successfully added {total_embeddings} embeddings to Qdrant. Total: {len(self.texts)}")
            
        except Exception as e:
            print(f"Error adding embeddings to Qdrant: {e}")
            raise
    
    def search(self, query_embedding: np.ndarray, k: int = Config.TOP_K_RESULTS) -> Tuple[List[str], List[float]]:
        """
        Search for similar embeddings in Qdrant
        
        Args:
            query_embedding: query embedding vector
            k: number of top results to return
            
        Returns:
            tuple of (similar_texts, similarity_scores)
        """
        try:
            # Get collection info to check if it has data
            collection_info = self.client.get_collection(collection_name=self.collection_name)
            if collection_info.points_count == 0:
                return [], []
            
            # Convert to list for Qdrant
            query_vector = query_embedding.astype('float32').tolist()
            
            # Search in Qdrant
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=k
            )
            
            # Extract texts and scores
            similar_texts = [hit.payload["text"] for hit in search_results]
            similarity_scores = [hit.score for hit in search_results]
            
            return similar_texts, similarity_scores
            
        except Exception as e:
            print(f"Error searching in Qdrant: {e}")
            return [], []
    
    def save_index(self, filepath: str = None):
        """
        Save index (for Qdrant, data is already persisted in cloud)
        This method is kept for compatibility with FAISS interface
        """
        print(f"✓ Data already persisted in Qdrant cloud (collection: {self.collection_name})")
        return True
    
    def load_index(self, filepath: str = None):
        """
        Load index (for Qdrant, connect to existing collection)
        This method is kept for compatibility with FAISS interface
        
        Returns:
            True if collection exists and has data, False otherwise
        """
        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                print(f"Collection '{self.collection_name}' not found in Qdrant")
                return False
            
            # Get collection info
            collection_info = self.client.get_collection(collection_name=self.collection_name)
            points_count = collection_info.points_count
            
            if points_count == 0:
                print(f"Collection '{self.collection_name}' exists but is empty")
                return False
            
            print(f"Connected to Qdrant collection '{self.collection_name}' with {points_count} vectors")
            
            # Skip rebuilding text cache for faster startup
            # Text will be fetched on-demand during search
            print("✓ Index loaded (text cache will be built on-demand for faster startup)")
            
            return True
            
        except Exception as e:
            print(f"Error loading from Qdrant: {e}")
            return False
    
    def _rebuild_text_cache(self):
        """Rebuild local text cache from Qdrant (optional)"""
        try:
            # Scroll through all points to rebuild text cache
            points, _ = self.client.scroll(
                collection_name=self.collection_name,
                limit=10000  # Adjust based on your collection size
            )
            
            self.texts = [point.payload["text"] for point in points]
            print(f"Rebuilt text cache with {len(self.texts)} texts")
            
        except Exception as e:
            print(f"Warning: Could not rebuild text cache: {e}")
            self.texts = []
    
    def get_stats(self):
        """Get statistics about the vector store"""
        try:
            collection_info = self.client.get_collection(collection_name=self.collection_name)
            
            return {
                "total_embeddings": collection_info.points_count,
                "dimension": self.dimension,
                "total_texts": len(self.texts),
                "collection_name": self.collection_name,
                "backend": "Qdrant Cloud"
            }
            
        except Exception as e:
            return {
                "total_embeddings": 0,
                "dimension": self.dimension,
                "total_texts": 0,
                "collection_name": self.collection_name,
                "backend": "Qdrant Cloud",
                "error": str(e)
            }
    
    def delete_collection(self):
        """Delete the collection from Qdrant"""
        try:
            self.client.delete_collection(collection_name=self.collection_name)
            print(f"✓ Deleted collection '{self.collection_name}' from Qdrant")
            self.texts = []
            
        except Exception as e:
            print(f"Error deleting collection: {e}")
            raise
