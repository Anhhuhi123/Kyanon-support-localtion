"""
Route Search Service
Kết hợp search + xây dựng lộ trình tối ưu
"""
import time
from datetime import datetime
from typing import Optional
from concurrent.futures import ProcessPoolExecutor
import asyncpg
import redis.asyncio as aioredis
from services.combined_search import CombinedSearchService
from services.cache_search import CacheSearchService
from radius_logic.route import RouteBuilder
from uuid import UUID

class RouteSearchService(CombinedSearchService):
    """Service xây dựng lộ trình từ kết quả search"""
    
    def __init__(self, db_pool: asyncpg.Pool = None, redis_client: aioredis.Redis = None, 
                 process_pool: ProcessPoolExecutor = None, vector_store=None, embedder=None):
        """
        Khởi tạo route search service
        
        Args:
            db_pool: Async PostgreSQL connection pool
            redis_client: Async Redis client
            process_pool: ProcessPoolExecutor for CPU-bound tasks (route building)
            vector_store: Shared QdrantVectorStore instance
            embedder: Shared EmbeddingGenerator instance
        """
        super().__init__(db_pool, redis_client, vector_store, embedder)
        self.process_pool = process_pool
        self.route_builder = RouteBuilder()
        self.cache_service = CacheSearchService(redis_client)
    
    async def build_routes(
        self,
        latitude: float,
        longitude: float,
        transportation_mode: str,
        semantic_query: str,
        user_id: Optional[UUID] = None,
        max_time_minutes: int = 180,
        target_places: int = 5,
        max_routes: int = 3,
        top_k_semantic: int = 10,
        customer_like: bool = False,
        current_datetime: Optional[datetime] = None
    ):
        """
        Tìm kiếm kết hợp + Xây dựng lộ trình với tùy chọn lọc theo thời gian mở cửa
        
        Workflow:
        1. Spatial search (PostGIS) → TẤT CẢ địa điểm gần (>= 50), có thể lọc theo thời gian
        2. Semantic search (Qdrant) → Top 10 địa điểm phù hợp nhất
        3. Route building (Greedy) → Top 3 lộ trình tốt nhất, validate thời gian mở cửa
        
        Args:
            latitude: Vĩ độ user
            longitude: Kinh độ user
            transportation_mode: Phương tiện di chuyển
            semantic_query: Query ngữ nghĩa
            max_time_minutes: Thời gian tối đa (phút)
            target_places: Số địa điểm mỗi lộ trình
            max_routes: Số lộ trình tối đa
            top_k_semantic: Số địa điểm từ semantic search
            customer_like: Tự động thêm "Culture & heritage" nếu chỉ có "Food & Local Flavours"
            current_datetime: Thời điểm hiện tại của user (None = không lọc theo thời gian)
            
        Returns:
            Dict chứa routes (top 3 lộ trình) và metadata, bao gồm thông tin validate thời gian
        """
        try:
            total_start = time.time()
            
            # 1. Spatial + Semantic search (hỗ trợ nhiều queries) (ASYNC)
            # Pass current_datetime và max_time_minutes để lọc POI theo thời gian
            search_result = await self.search_multi_queries_and_find_locations(
                latitude=latitude,
                longitude=longitude,
                transportation_mode=transportation_mode,
                semantic_query=semantic_query,
                user_id=user_id,
                top_k_semantic=top_k_semantic,
                customer_like=customer_like,
                current_datetime=current_datetime,
                max_time_minutes=max_time_minutes
            )
            
            if search_result["status"] != "success":
                return {
                    "status": "error",
                    "error": "Search failed",
                    "search_error": search_result.get("error"),
                    "routes": []
                }
            
            semantic_places = search_result.get("results", [])
          
            if not semantic_places:
                return {
                    "status": "success",
                    "message": "No places found",
                    "query": semantic_query,
                    "spatial_info": search_result.get("spatial_info", {}),
                    "routes": []
                }
            
            # 2. Xây dựng lộ trình với validation thời gian mở cửa (ASYNC offload CPU-bound)
            print(f"\n🔍 Step 3: Building routes from {len(semantic_places)} places...")
            route_start = time.time()
            
            user_location = (latitude, longitude)
            routes = await self.route_builder.build_routes_async(
                user_location=user_location,
                places=semantic_places,
                transportation_mode=transportation_mode,
                max_time_minutes=max_time_minutes,
                target_places=target_places,
                max_routes=max_routes,
                current_datetime=current_datetime,  # Pass datetime để validate opening hours
                executor=self.process_pool  # Use process pool for CPU-bound task
            )
            
            route_time = time.time() - route_start
            total_time = time.time() - total_start
            
            print(f"⏱️  Route building: {route_time:.3f}s")
            print(f"⏱️  Total execution time: {total_time:.3f}s")
            print(f"✅ Generated {len(routes)} route(s)")
            
            # 🔥 Cache route metadata to Redis using CacheSearchService
            if self.cache_service and user_id and routes:
                await self.cache_service.cache_route_metadata(
                    user_id=user_id,
                    routes=routes,
                    semantic_places=semantic_places
                )
            
            # Lấy timing detail từ search result
            search_timing = search_result.get("timing_detail", {})
            spatial_time = search_result.get("spatial_info", {}).get("spatial_execution_time", 0)
            
            return {
                "status": "success",
                "query": semantic_query,
                "user_location": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "spatial_info": search_result.get("spatial_info", {}),
                "semantic_places_count": len(semantic_places),
                "total_execution_time_seconds": round(total_time, 3),
                "timing_breakdown": {
                    "spatial_search_seconds": round(spatial_time, 3),
                    "embedding_seconds": search_timing.get("embedding_seconds", 0),
                    "qdrant_search_seconds": search_timing.get("qdrant_search_seconds", 0),
                    "db_query_seconds": search_timing.get("db_query_seconds", 0),
                    "route_building_seconds": round(route_time, 3),
                    "total_search_seconds": round(search_result.get("total_execution_time_seconds", 0), 3)
                },
                "routes": routes
            }
            
        except Exception as e:
            import traceback
            print(f"❌ Error in build_routes: {str(e)}")
            print(traceback.format_exc())
            return {
                "status": "error",
                "error": str(e),
                "routes": []
            }
