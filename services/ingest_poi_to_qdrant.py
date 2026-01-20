"""
Service để ingest POI data từ PoiClean vào Qdrant
- Lấy toàn bộ id và poi_type_clean từ database PoiClean
- Tạo embeddings từ poi_type_clean
- Reset collection và upsert lại toàn bộ
- Lưu vào Qdrant với point.id = location id, payload chỉ chứa poi_type_clean
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from retrieval.embeddings import EmbeddingGenerator
from config.config import Config


class IngestPoiToQdrantService:
    """Service để ingest POI data vào Qdrant"""
    
    def __init__(self, db_pool=None):
        """
        Khởi tạo service
        
        Args:
            db_pool: AsyncPG connection pool
        """
        self.db_pool = db_pool
        self.qdrant_client: Optional[QdrantClient] = None
        self.embedder: Optional[EmbeddingGenerator] = None
        self.collection_name = Config.QDRANT_COLLECTION_NAME_TEST
        self.batch_size = 100
    
    async def initialize(self):
        """Khởi tạo Qdrant client và EmbeddingGenerator"""
        try:
            # Khởi tạo Qdrant client
            self.qdrant_client = QdrantClient(
                url=Config.QDRANT_URL,
                api_key=Config.QDRANT_API_KEY,
                timeout=60
            )
            print(f"✓ Đã kết nối Qdrant: {Config.QDRANT_URL}")
            
            # Khởi tạo EmbeddingGenerator
            self.embedder = EmbeddingGenerator()
            print(f"✓ Đã khởi tạo EmbeddingGenerator: {Config.EMBEDDING_MODEL}")
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to initialize Qdrant service: {str(e)}")
    
    async def fetch_all_poi_data(self) -> List[tuple]:
        """
        Lấy toàn bộ id và poi_type_clean từ PoiClean
        
        Returns:
            List[Tuple]: [(id, poi_type_clean), ...]
        """
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")
        
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
            raise HTTPException(status_code=500, detail=f"Failed to fetch POI data: {str(e)}")
    
    def _reset_collection(self, dimension: int):
        """
        Xóa và tạo lại collection trong Qdrant
        
        Args:
            dimension: Số chiều của vector embeddings
        """
        print(f"🔄 Reset collection '{self.collection_name}'...")
        
        # Xóa collection cũ nếu tồn tại
        try:
            self.qdrant_client.delete_collection(collection_name=self.collection_name)
            print(f"  ✓ Đã xóa collection cũ")
        except Exception as e:
            print(f"  ℹ️  Collection chưa tồn tại: {e}")
        
        # Tạo collection mới
        self.qdrant_client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=dimension,
                distance=Distance.COSINE
            )
        )
        print(f"  ✓ Đã tạo collection mới với dimension {dimension}")
    
    def _ingest_to_qdrant(self, poi_data: List[tuple]) -> Dict[str, Any]:
        """
        Ingest POI data vào Qdrant
        
        Args:
            poi_data: List[(id, poi_type_clean)]
            
        Returns:
            Dict chứa kết quả ingest
        """
        if not poi_data:
            return {
                "status": "success",
                "upserted_count": 0,
                "message": "No data to ingest"
            }
        
        try:
            # Tạo embeddings cho tất cả poi_type
            print(f"🔄 Tạo embeddings cho {len(poi_data)} poi_type...")
            poi_types = [poi[1] for poi in poi_data]
            embeddings = self.embedder.generate_embeddings(poi_types)
            print(f"  ✓ Đã tạo {len(embeddings)} embeddings")
            
            # Reset collection
            embedding_dim = self.embedder.model.get_sentence_embedding_dimension()
            self._reset_collection(embedding_dim)
            
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
                self.qdrant_client.upsert(
                    collection_name=self.collection_name,
                    points=batch
                )
                upserted_count += len(batch)
                batch_num = i // self.batch_size + 1
                print(f"  ✓ Batch {batch_num}/{total_batches}: upserted {len(batch)} points")
            
            print(f"✅ Hoàn thành upsert!")
            
            return {
                "status": "success",
                "upserted_count": upserted_count,
                "collection_name": self.collection_name,
                "embedding_dimension": embedding_dim,
                "message": f"Successfully ingested {upserted_count} points to Qdrant"
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to ingest to Qdrant: {str(e)}")
    
    def _verify_collection(self) -> Dict[str, Any]:
        """
        Verify collection sau khi ingest
        
        Returns:
            Dict chứa thông tin collection
        """
        print(f"\n🔍 Verify collection '{self.collection_name}'...")
        
        try:
            # Lấy thông tin collection
            collection_info = self.qdrant_client.get_collection(collection_name=self.collection_name)
            
            result = {
                "collection_name": self.collection_name,
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
    
    async def ingest_all_poi(self) -> Dict[str, Any]:
        """
        Ingest toàn bộ POI data từ PoiClean vào Qdrant
        
        Quy trình:
        1. Lấy toàn bộ data từ PoiClean
        2. Tạo embeddings từ poi_type_clean
        3. Reset collection (xóa và tạo lại)
        4. Upsert toàn bộ points
        5. Verify collection
        
        Returns:
            Dict chứa kết quả ingest
        """
        if not self.qdrant_client or not self.embedder:
            await self.initialize()
        
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
            ingest_result = self._ingest_to_qdrant(poi_data)
            
            # 3. Verify collection
            print("\n3️⃣  Verify collection...")
            verify_result = self._verify_collection()
            
            print("\n" + "="*60)
            print("✅ HOÀN THÀNH INGEST DATA VÀO QDRANT!")
            print("="*60)
            
            return {
                **ingest_result,
                "verify": verify_result
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to ingest all POI: {str(e)}")