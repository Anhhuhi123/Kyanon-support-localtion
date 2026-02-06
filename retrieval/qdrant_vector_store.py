import uuid
import time
import numpy as np
import asyncpg
from config.config import Config
from qdrant_client import AsyncQdrantClient
from typing import List, Tuple, Optional, Dict, Any
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, HasIdCondition

class QdrantVectorStore:
    """Qdrant-based vector store for similarity search (Async)"""
    
    def __init__(self, client: Optional[AsyncQdrantClient] = None, db_pool: Optional[asyncpg.Pool] = None, embedder=None):
        """Initialize Qdrant vector store with async client
        
        Args:
            client: AsyncQdrantClient instance (required for async operations)
            db_pool: AsyncPG connection pool (for ingest operations)
            embedder: EmbeddingGenerator instance (for ingest operations)
        """
        self.dimension = Config.VECTOR_DIMENSION
        self.collection_name = Config.QDRANT_COLLECTION_NAME
        self.collection_name_test = Config.QDRANT_COLLECTION_NAME_TEST
        self.client = client  # Expect AsyncQdrantClient injected
        self.collection_points_count = 0
        self.texts = []
        self.db_pool = db_pool
        self.embedder = embedder
        self.batch_size = 100
        
    async def initialize_async(self):
        """Initialize collection and check if it exists (async)"""
        try:
            if self.client is None:
                print("⚠️ AsyncQdrantClient not injected, creating new instance...")
                self.client = AsyncQdrantClient(
                    url=Config.QDRANT_URL,
                    api_key=Config.QDRANT_API_KEY if Config.QDRANT_API_KEY else None,
                    timeout=60
                )
            
            print(f"Connecting to Qdrant at {Config.QDRANT_URL}...")
            
            # Check if collection exists, create if not
            collections = await self.client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if self.collection_name not in collection_names:
                print(f"Creating collection '{self.collection_name}'...")
                await self.client.create_collection(
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
                collection_info = await self.client.get_collection(collection_name=self.collection_name)
                self.collection_points_count = collection_info.points_count
                
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
    

    async def search(self, query_embedding: np.ndarray, k: int = Config.TOP_K_RESULTS, query_filter=None):
        """
        Search for similar embeddings in Qdrant (Async, Light RAG optimized)
        
        Args:
            query_embedding: query embedding vector
            k: number of top results to return
            query_filter: optional Qdrant filter to apply
            
        Returns:
            list of search results (ScoredPoint objects)
        """
        try:
            # Check cache thay vì gọi get_collection mỗi lần
            if self.collection_points_count == 0:
                return []
            
            # Convert to list for Qdrant
            query_vector = query_embedding.astype('float32').tolist()
                        
            # Search in Qdrant với hoặc không có filter (async)
            search_results = await self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=k,
                query_filter=query_filter
            )
            
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
            return []
    
    async def search_by_ids(self, query_embedding: np.ndarray, point_ids: List[str], k: int = Config.TOP_K_RESULTS, 
                      with_payload: bool = False, hnsw_ef: int = 32):
        """
        Search for similar embeddings trong danh sách point IDs cụ thể (Async, Light RAG optimized)
        
        Args:
            query_embedding: query embedding vector
            point_ids: danh sách point.id cần filter
            k: number of top results to return
            with_payload: False = chỉ lấy id+score (nhanh hơn), True = lấy cả payload
            hnsw_ef: HNSW search param (16-64: nhanh, 128-256: chính xác)
            
        Returns:
            list of search results (ScoredPoint objects)
        """
        try:
            if not point_ids:
                return []
            
            # Convert to list for Qdrant
            query_vector = query_embedding.astype('float32').tolist()
            
            # Tạo filter theo point.id (sử dụng HasIdCondition)
            id_filter = Filter(
                must=[
                    HasIdCondition(has_id=point_ids)
                ]
            )
            
            # Async search với filter
            search_results = await self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=id_filter,
                limit=k,
                with_payload=with_payload,
                search_params={"hnsw_ef": hnsw_ef}  # Giảm ef = tăng tốc
            )

            
            return search_results
            
        except Exception as e:
            print(f"Error searching by IDs in Qdrant: {e}")
            return []
    

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
    
    # ====================================INGEST POI TO QDRANT====================================== #
    
    async def fetch_all_poi_data(self) -> List[tuple]:
        """
        Lấy toàn bộ id và poi_type_clean từ PoiClean
        
        Returns:
            List[Tuple]: [(id, poi_type_clean), ...]
        """
        if not self.db_pool:
            raise Exception("Database pool not initialized")
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    '''SELECT id, poi_type_clean 
                       FROM "PoiClean" 
                       WHERE poi_type_clean IS NOT NULL 
                         AND poi_type_clean != ''
                         AND "deletedAt" IS NULL
                       ORDER BY id'''
                )
                
                result = [(str(row["id"]), row["poi_type_clean"]) for row in rows]
                print(f"✓ Đã lấy {len(result)} địa điểm từ database")
                return result
                
        except Exception as e:
            raise Exception(f"Failed to fetch POI data: {str(e)}")
    
    async def _reset_collection(self, dimension: int, collection_name: str = None):
        """
        Xóa và tạo lại collection trong Qdrant
        
        Args:
            dimension: Số chiều của vector embeddings
            collection_name: Tên collection (default: self.collection_name_test)
        """
        target_collection = collection_name or self.collection_name_test
        print(f"🔄 Reset collection '{target_collection}'...")
        
        # Xóa collection cũ nếu tồn tại
        try:
            await self.client.delete_collection(collection_name=target_collection)
            print(f"  ✓ Đã xóa collection cũ")
        except Exception as e:
            print(f"  ℹ️  Collection chưa tồn tại: {e}")
        
        # Tạo collection mới
        await self.client.create_collection(
            collection_name=target_collection,
            vectors_config=VectorParams(
                size=dimension,
                distance=Distance.COSINE
            )
        )
        print(f"  ✓ Đã tạo collection mới với dimension {dimension}")
    
    async def _ingest_to_qdrant(self, poi_data: List[tuple], collection_name: str = None) -> Dict[str, Any]:
        """
        Ingest POI data vào Qdrant
        
        Args:
            poi_data: List[(id, poi_type_clean)]
            collection_name: Tên collection (default: self.collection_name_test)
            
        Returns:
            Dict chứa kết quả ingest
        """
        if not poi_data:
            return {
                "status": "success",
                "upserted_count": 0,
                "message": "No data to ingest"
            }
        
        if not self.embedder:
            raise Exception("Embedder not initialized")
        
        target_collection = collection_name or self.collection_name_test
        
        try:
            # Tạo embeddings cho tất cả poi_type
            print(f"🔄 Tạo embeddings cho {len(poi_data)} poi_type...")
            poi_types = [poi[1] for poi in poi_data]
            embeddings = self.embedder.generate_embeddings(poi_types)
            print(f"  ✓ Đã tạo {len(embeddings)} embeddings")
            
            # Reset collection
            embedding_dim = self.embedder.model.get_sentence_embedding_dimension()
            await self._reset_collection(embedding_dim, target_collection)
            
            # Chuẩn bị points
            print("🔄 Chuẩn bị points...")
            points = []
            for idx, (location_id, poi_type) in enumerate(poi_data):
                point = PointStruct(
                    id=location_id,  # UUID string
                    vector=embeddings[idx].tolist(),
                    payload={
                        "poi_type_clean": poi_type
                    }
                )
                points.append(point)
            
            # Upsert theo batch
            print(f"🚀 Upsert {len(points)} points vào Qdrant (batch size: {self.batch_size})...")
            total_batches = (len(points) + self.batch_size - 1) // self.batch_size
            upserted_count = 0
            
            for i in range(0, len(points), self.batch_size):
                batch = points[i:i + self.batch_size]
                await self.client.upsert(
                    collection_name=target_collection,
                    points=batch
                )
                upserted_count += len(batch)
                batch_num = i // self.batch_size + 1
                print(f"  ✓ Batch {batch_num}/{total_batches}: upserted {len(batch)} points")
            
            print(f"✅ Hoàn thành upsert!")
            
            return {
                "status": "success",
                "upserted_count": upserted_count,
                "collection_name": target_collection,
                "embedding_dimension": embedding_dim,
                "message": f"Successfully ingested {upserted_count} points to Qdrant"
            }
            
        except Exception as e:
            raise Exception(f"Failed to ingest to Qdrant: {str(e)}")
    
    async def _verify_collection(self, collection_name: str = None) -> Dict[str, Any]:
        """
        Verify collection sau khi ingest
        
        Args:
            collection_name: Tên collection (default: self.collection_name_test)
            
        Returns:
            Dict chứa thông tin collection
        """
        target_collection = collection_name or self.collection_name_test
        print(f"\n🔍 Verify collection '{target_collection}'...")
        
        try:
            # Lấy thông tin collection
            collection_info = await self.client.get_collection(collection_name=target_collection)
            
            result = {
                "collection_name": target_collection,
                "points_count": collection_info.points_count,
                "vector_dimension": collection_info.config.params.vectors.size,
                "distance_metric": str(collection_info.config.params.vectors.distance)
            }
            
            print(f"  ✓ Tổng số points: {result['points_count']}")
            print(f"  ✓ Vector dimension: {result['vector_dimension']}")
            print(f"  ✓ Distance metric: {result['distance_metric']}")
            
            return result
            
        except Exception as e:
            print(f"  ❌ Verify failed: {e}")
            return {"error": str(e)}
    
    async def ingest_all_poi(self, collection_name: str = None) -> Dict[str, Any]:
        """
        Ingest toàn bộ POI data từ PoiClean vào Qdrant
        
        Quy trình:
        1. Lấy toàn bộ data từ PoiClean
        2. Tạo embeddings từ poi_type_clean
        3. Reset collection (xóa và tạo lại)
        4. Upsert toàn bộ points
        5. Verify collection
        
        Args:
            collection_name: Tên collection (default: self.collection_name_test)
            
        Returns:
            Dict chứa kết quả ingest
        """
        target_collection = collection_name or self.collection_name_test
        
        try:
            print("="*60)
            print("🚀 BẮT ĐẦU INGEST POI DATA VÀO QDRANT")
            print("="*60)
            
            # 1. Lấy toàn bộ data từ database
            print("\n1️⃣  Fetch data từ database...")
            poi_data = await self.fetch_all_poi_data()
            
            if not poi_data:
                return {
                    "status": "success",
                    "upserted_count": 0,
                    "message": "No POI data found in database"
                }
            
            # 2. Ingest vào Qdrant (bao gồm tạo embeddings, reset collection, upsert)
            print("\n2️⃣  Ingest data vào Qdrant...")
            ingest_result = await self._ingest_to_qdrant(poi_data, target_collection)
            
            # 3. Verify collection
            print("\n3️⃣  Verify collection...")
            verify_result = await self._verify_collection(target_collection)
            
            print("\n" + "="*60)
            print("✅ HOÀN THÀNH INGEST DATA VÀO QDRANT!")
            print("="*60)
            
            return {
                **ingest_result,
                "verify": verify_result
            }
            
        except Exception as e:
            raise Exception(f"Failed to ingest all POI: {str(e)}")
