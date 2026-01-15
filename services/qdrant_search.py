"""
Semantic Search Base Service
Core semantic search với Qdrant vector embeddings
"""
import time
from typing import Optional, List, Dict, Any
import asyncpg
import redis.asyncio as aioredis
from retrieval.embeddings import EmbeddingGenerator
from retrieval.qdrant_vector_store import QdrantVectorStore
from radius_logic.information_location import LocationInfoService
from qdrant_client.models import Filter, FieldCondition, MatchAny


class SemanticSearchBase:
    """Base service cho semantic search với Qdrant"""
    
    # Singleton instances shared across all service layers
    _vector_store = None
    _embedder = None
    
    def __init__(self, db_pool: asyncpg.Pool = None, redis_client: aioredis.Redis = None, 
                 vector_store: QdrantVectorStore = None, embedder: EmbeddingGenerator = None):
        """
        Khởi tạo base service
        
        Args:
            db_pool: Async PostgreSQL connection pool
            redis_client: Async Redis client
            vector_store: Shared QdrantVectorStore instance (optional, will create if None)
            embedder: Shared EmbeddingGenerator instance (optional, will create if None)
        """
        self.db_pool = db_pool
        self.redis_client = redis_client
        
        # Use shared instances to avoid duplicate loading
        if vector_store is not None:
            self.vector_store = vector_store
        elif SemanticSearchBase._vector_store is None:
            SemanticSearchBase._vector_store = QdrantVectorStore()
            self.vector_store = SemanticSearchBase._vector_store
        else:
            self.vector_store = SemanticSearchBase._vector_store
            
        if embedder is not None:
            self.embedder = embedder
        elif SemanticSearchBase._embedder is None:
            SemanticSearchBase._embedder = EmbeddingGenerator()
            self.embedder = SemanticSearchBase._embedder
        else:
            self.embedder = SemanticSearchBase._embedder
            
        self.location_info_service = LocationInfoService(db_pool=db_pool, redis_client=redis_client)
    
    async def search_by_query(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """
        Tìm kiếm địa điểm theo query ngữ nghĩa (không filter ID)
        
        Args:
            query: Câu query tìm kiếm (vd: "Travel", "Nature & View")
            top_k: Số lượng kết quả trả về tối đa
            
        Returns:
            Dict chứa kết quả với các trường:
            - status: "success" hoặc "error"
            - query: query đã tìm kiếm
            - total_results: số lượng kết quả
            - execution_time_seconds: thời gian thực thi
            - results: danh sách địa điểm với score tương đồng
        """
        try:
            # Đo thời gian
            start_time = time.time()
            
            # 1. Sinh embedding cho query
            print(f"Generating embedding for query: {query}")
            embed_start = time.time()
            query_embedding = self.embedder.generate_single_embedding(query)
            embed_time = time.time() - embed_start
            
            # 2. Tìm kiếm trong Qdrant (không filter)
            print(f"Searching in Qdrant for top {top_k} results...")
            search_start = time.time()
            search_results = self.vector_store.search(
                query_embedding=query_embedding,
                k=top_k
         )
            search_time = time.time() - search_start
            
            total_time = time.time() - start_time
            print(f"⏱️  search_by_query executed in {total_time:.3f}s (Embed: {embed_time:.3f}s + Search: {search_time:.3f}s)")
            print(f"Search returned {len(search_results) if search_results else 0} results")
            
            # Kiểm tra nếu kết quả rỗng
            if not search_results:
                print("⚠️ No results found")
                return {
                    "status": "success",
                    "query": query,
                    "total_results": 0,
                    "execution_time_seconds": round(total_time, 3),
                    "timing_breakdown": {
                        "embedding_seconds": round(embed_time, 3),
                        "search_seconds": round(search_time, 3)
                    },
                    "results": []
                }
            
            # 3. Lấy location IDs từ Qdrant results
            location_ids = [hit.id for hit in search_results]  # hit.id là point.id
            print(f"Fetching {len(location_ids)} location details from DB...")
            
            # 4. Query DB để lấy thông tin đầy đủ (ASYNC)
            db_start = time.time()
            locations_map = await self.location_info_service.get_locations_by_ids(location_ids)
            db_time = time.time() - db_start
            print(f"DB query took {db_time:.3f}s")
            
            # 5. Merge semantic score với location info
            results = []
            for hit in search_results:
                location_info = locations_map.get(hit.id)
                if location_info:
                    result = {
                        "score": hit.score,
                        **location_info  # Merge tất cả fields từ DB (bao gồm poi_type)
                    }
                    results.append(result)
                else:
                    print(f"⚠️ Location {hit.id} not found in DB")
            
            return {
                "status": "success",
                "query": query,
                "total_results": len(results),
                "execution_time_seconds": round(total_time, 3),
                "timing_breakdown": {
                    "embedding_seconds": round(embed_time, 3),
                    "search_seconds": round(search_time, 3)
                },
                "results": results
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "query": query,
                "total_results": 0,
                "results": []
            }
    
    async def search_by_query_with_filter(
        self,
        query: str,
        id_list: List[str],
        top_k: int = 10,
        spatial_results: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Tìm kiếm địa điểm theo query ngữ nghĩa với filter ID (dùng cho combined search)
        
        Args:
            query: Câu query tìm kiếm
            id_list: Danh sách ID cần filter
            top_k: Số lượng kết quả
            spatial_results: Optional list các địa điểm từ spatial search (để merge info)
            
        Returns:
            Dict chứa kết quả
        """
        try:
            start_time = time.time()
            
            if not id_list or len(id_list) == 0:
                return {
                    "status": "error",
                    "error": "Empty ID list provided",
                    "query": query,
                    "total_results": 0,
                    "results": []
                }
            
            # 1. Sinh embedding cho query
            embed_start = time.time()
            query_embedding = self.embedder.generate_single_embedding(query)
            embed_time = time.time() - embed_start
            
            # 2. Tìm kiếm trong Qdrant với filter theo ID list
            print(f"Searching in Qdrant with filter on {len(id_list)} IDs...")
            search_start = time.time()
            
            # Qdrant filter với HasIdCondition
            search_results = self.vector_store.search_by_ids(
                query_embedding=query_embedding,
                point_ids=id_list,
                k=top_k,
                with_payload=True
            )
            
            search_time = time.time() - search_start
            total_time = time.time() - start_time
            
            print(f"⏱️  search_by_query_with_filter executed in {total_time:.3f}s")
            print(f"   Embedding: {embed_time:.3f}s, Qdrant search: {search_time:.3f}s")
            print(f"   Found {len(search_results) if search_results else 0} results")
            
            # Nếu không có kết quả
            if not search_results:
                return {
                    "status": "success",
                    "query": query,
                    "id_list_size": len(id_list),
                    "total_results": 0,
                    "execution_time_seconds": round(total_time, 3),
                    "timing_detail": {
                        "embedding_seconds": round(embed_time, 3),
                        "qdrant_search_seconds": round(search_time, 3)
                    },
                    "results": []
                }
            
            # 3. Lấy location IDs từ Qdrant results
            location_ids = [hit.id for hit in search_results]
            
            # 4. Query DB để lấy thông tin đầy đủ (ASYNC)
            db_start = time.time()
            locations_map = await self.location_info_service.get_locations_by_ids(location_ids)
            db_time = time.time() - db_start
            
            # 5. Merge semantic score với location info
            results = []
            for hit in search_results:
                location_info = locations_map.get(hit.id)
                if location_info:
                    result = {
                        "score": hit.score,
                        **location_info
                    }
                    
                    # Merge distance và open_hours từ spatial results nếu có
                    if spatial_results:
                        spatial_match = next((s for s in spatial_results if s["id"] == hit.id), None)
                        if spatial_match:
                            result["distance_meters"] = spatial_match.get("distance_meters")
                            result["open_hours"] = spatial_match.get("open_hours", [])
                    
                    results.append(result)
            
            return {
                "status": "success",
                "query": query,
                "id_list_size": len(id_list),
                "total_results": len(results),
                "execution_time_seconds": round(total_time, 3),
                "timing_detail": {
                    "embedding_seconds": round(embed_time, 3),
                    "qdrant_search_seconds": round(search_time, 3),
                    "db_query_seconds": round(db_time, 3)
                },
                "results": results
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "query": query,
                "total_results": 0,
                "results": []
            }
