"""
Semantic Search Service (Async Version - Facade Pattern)
Facade service giữ backward compatibility, delegate logic tới các service chuyên biệt:
- QdrantSearch: Core semantic search
- SpatialSearch: Spatial + semantic search
- RouteSearch: Route building with search + POI replacement
"""
from datetime import datetime
from typing import Optional, Dict, Any
from concurrent.futures import ProcessPoolExecutor
import asyncpg
import redis.asyncio as aioredis

from services.qdrant_search import QdrantSearch
from services.spatial_search import SpatialSearch
from services.route_search import RouteSearch
from uuid import UUID

class RouteService:
    """
    Facade service để giữ backward compatibility
    Delegate tất cả logic tới các service chuyên biệt
    """
    
    def __init__(self, db_pool: asyncpg.Pool = None, redis_client: aioredis.Redis = None, 
                 process_pool: ProcessPoolExecutor = None, vector_store=None, embedder=None):
        """
        Khởi tạo facade service với async resources
        
        Args:
            db_pool: Async PostgreSQL connection pool
            redis_client: Async Redis client
            process_pool: ProcessPoolExecutor for CPU-bound tasks (route building)
            vector_store: Shared QdrantVectorStore instance (với AsyncQdrantClient)
            embedder: Shared EmbeddingGenerator instance
        """
        # Khởi tạo base service với shared vector_store & embedder
        self.base_service = QdrantSearch(db_pool, redis_client, vector_store, embedder)
        
        # Get singleton instances từ base service
        vector_store = self.base_service.vector_store
        embedder = self.base_service.embedder
        
        self.combined_service = SpatialSearch(db_pool, redis_client, vector_store, embedder)
        self.route_service = RouteSearch(db_pool, redis_client, process_pool, vector_store, embedder)
    
    async def search_by_query(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """
        Delegate to QdrantSearch.search_by_query
        Tìm kiếm địa điểm theo query ngữ nghĩa (không filter ID)
        """
        return await self.base_service.search_by_query(query, top_k)
    
    # async def search_by_query_with_filter(
    #     self,
    #     query: str,
    #     id_list: List[str],
    #     top_k: int = 10,
    #     spatial_results: Optional[List[Dict[str, Any]]] = None
    # ) -> Dict[str, Any]:
    #     """
    #     Delegate to QdrantSearch.search_by_query_with_filter
    #     Tìm kiếm địa điểm theo query ngữ nghĩa với filter ID (dùng cho combined search)
    #     """
    #     return await self.base_service.search_by_query_with_filter(query, id_list, top_k, spatial_results)
    
    async def search_combined(
        self,
        latitude: float,
        longitude: float,
        transportation_mode: str,
        semantic_query: str,
        top_k_semantic: int = 10
    ) -> Dict[str, Any]:
        """
        Delegate to SpatialSearch.search_combined
        Tìm kiếm kết hợp: Spatial search (PostGIS) + Semantic search (Qdrant)
        """
        return await self.combined_service.search_combined(
            latitude, longitude, transportation_mode, semantic_query, top_k_semantic
        )
    
    # async def search_multi_queries(
    #     self,
    #     latitude: float,
    #     longitude: float,
    #     transportation_mode: str,
    #     semantic_query: str,
    #     top_k_semantic: int = 10,
    #     customer_like: bool = False,
    #     current_datetime: Optional[datetime] = None,
    #     max_time_minutes: Optional[int] = None
    # ) -> Dict[str, Any]:
    #     """
    #     Delegate to SpatialSearch.search_multi_queries_and_find_locations
    #     Tìm kiếm kết hợp với hỗ trợ nhiều queries phân cách bằng dấu phẩy
    #     """
    #     return await self.combined_service.search_multi_queries_and_find_locations(
    #         latitude, longitude, transportation_mode, semantic_query, 
    #         top_k_semantic, customer_like, current_datetime, max_time_minutes
    #     )
    
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
        current_datetime: Optional[datetime] = None,
        duration_mode: bool = False 
    ) -> Dict[str, Any]:
        """
        Delegate to RouteSearch.search_combined_with_routes
        Tìm kiếm kết hợp + Xây dựng lộ trình với tùy chọn lọc theo thời gian mở cửa
        """
        return await self.route_service.build_routes(
            latitude, longitude, transportation_mode, semantic_query, user_id,
            max_time_minutes, target_places, max_routes, top_k_semantic,
            customer_like, current_datetime, duration_mode
        )
    
    async def replace_route(
        self,
        user_id: UUID,
        route_id_to_replace: int,
        latitude: float,
        longitude: float,
        transportation_mode: str,
        semantic_query: str,
        max_time_minutes: int = 180,
        target_places: int = 5,
        top_k_semantic: int = 10,
        customer_like: bool = False,
        current_datetime: Optional[datetime] = None,
        duration_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Delegate to RouteSearch.replace_route
        Replace route: Xây dựng route mới, xoá route cũ
        """
        return await self.route_service.replace_route(
            user_id, route_id_to_replace, latitude, longitude,
            transportation_mode, semantic_query, max_time_minutes,
            target_places, top_k_semantic, customer_like,
            current_datetime, duration_mode
        )
    
    async def replace_poi(
        self,
        user_id: UUID,
        route_id: str,
        poi_id_to_replace: str,
        current_datetime: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Delegate to RouteSearch.replace_poi
        Replace POI trong route bằng POI khác cùng category
        """
        return await self.route_service.replace_poi(
            user_id, route_id, poi_id_to_replace, current_datetime
        )
    
    async def confirm_replace_poi(
        self,
        user_id: UUID,
        route_id: str,
        old_poi_id: str,
        new_poi_id: str
    ) -> Dict[str, Any]:
        """
        Delegate to RouteSearch.confirm_replace_poi
        Xác nhận thay thế POI và cập nhật cache
        """
        return await self.route_service.confirm_replace_poi(
            user_id, route_id, old_poi_id, new_poi_id
        )
    