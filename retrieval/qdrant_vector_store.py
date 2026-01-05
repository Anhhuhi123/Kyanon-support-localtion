from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, Filter, FieldCondition, MatchValue
import numpy as np
from config.config import Config

class QdrantVectorStore:
    """Qdrant-based vector store for similarity search"""
    
    def __init__(self):
        """Initialize Qdrant vector store"""
        self.dimension = Config.VECTOR_DIMENSION
        self.collection_name = Config.QDRANT_COLLECTION_NAME
        self.client = None
        self.collection_points_count = 0  # Cache để tránh get_collection mỗi lần search
        
        # Initialize Qdrant client
        self._initialize_client()
        
    def _initialize_client(self):
        """Initialize Qdrant client and create collection if needed"""
        try:
            print(f"Connecting to Qdrant at {Config.QDRANT_URL}...")
            self.client = QdrantClient(
                url=Config.QDRANT_URL,
                api_key=Config.QDRANT_API_KEY,
                timeout=60
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
                self.collection_points_count = 0
            else:
                print(f"✓ Using existing collection '{self.collection_name}'")
                # Cache points_count để tránh gọi get_collection mỗi lần search
                collection_info = self.client.get_collection(collection_name=self.collection_name)
                self.collection_points_count = collection_info.points_count
                
        except Exception as e:
            print(f"Error initializing Qdrant client: {e}")
            raise

    def search(self, query_embedding: np.ndarray, k: int = Config.TOP_K_RESULTS, query_filter=None):
        """
        Search for similar embeddings in Qdrant
        
        Args:
            query_embedding: query embedding vector
            k: number of top results to return
            query_filter: optional Qdrant filter to apply
            
        Returns:
            list of search results (ScoredPoint objects) with full payload
        """
        try:
            # Check cache thay vì gọi get_collection mỗi lần
            if self.collection_points_count == 0:
                return []
            
            # Convert to list for Qdrant
            query_vector = query_embedding.astype('float32').tolist()
            
            # Search in Qdrant với hoặc không có filter
            if query_filter is not None:
                search_results = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=k
                    # with_payload=False
                ).points
            else:
                search_results = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    limit=k
                    # with_payload=False
                ).points
            
            # 🔍 DEBUG: in cấu trúc kết quả
            if search_results:
                r = search_results[0]
                print("🔎 Qdrant result sample:")
                print(f"  id      : {r.id}")
                print(f"  score   : {r.score}")
                print(f"  payload : {r.payload}")
                print(f"  vector  : {r.vector}")
                
            # Return full results for both cases
            return search_results
            
        except Exception as e:
            print(f"Error searching in Qdrant: {e}")
            if query_filter is not None:
                return []
            return [], []
    
