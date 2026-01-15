"""
Semantic Search Service (Async Version - Facade Pattern)
Facade service giữ backward compatibility, delegate logic tới các service chuyên biệt:
- SemanticSearchBase: Core semantic search
- CombinedSearchService: Spatial + semantic search
- RouteSearchService: Route building with search
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from concurrent.futures import ProcessPoolExecutor
import asyncpg
import redis.asyncio as aioredis

from services.qdrant_search import SemanticSearchBase
from services.combined_search import CombinedSearchService
from services.route_search import RouteSearchService
from uuid import UUID

class SemanticSearchService:
    """
    Facade service để giữ backward compatibility
    Delegate tất cả logic tới các service chuyên biệt
    """
    
    def __init__(self, db_pool: asyncpg.Pool = None, redis_client: aioredis.Redis = None, process_pool: ProcessPoolExecutor = None):
        """
        Khởi tạo facade service với async resources
        
        Args:
            db_pool: Async PostgreSQL connection pool
            redis_client: Async Redis client
            process_pool: ProcessPoolExecutor for CPU-bound tasks (route building)
        """
        # Khởi tạo base service trước (tạo singleton instances lần đầu)
        self.base_service = SemanticSearchBase(db_pool, redis_client)
        
        # Share singleton instances với các service con để tránh load lại
        vector_store = self.base_service.vector_store
        embedder = self.base_service.embedder
        
        self.combined_service = CombinedSearchService(db_pool, redis_client, vector_store, embedder)
        self.route_service = RouteSearchService(db_pool, redis_client, process_pool, vector_store, embedder)
        
        # Keep references for backward compatibility
        self.db_pool = db_pool
        self.redis_client = redis_client
        self.process_pool = process_pool
    
    async def search_by_query(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """
        Delegate to SemanticSearchBase.search_by_query
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
    #     Delegate to SemanticSearchBase.search_by_query_with_filter
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
        Delegate to CombinedSearchService.search_combined
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
    #     Delegate to CombinedSearchService.search_multi_queries_and_find_locations
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
        current_datetime: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Delegate to RouteSearchService.search_combined_with_routes
        Tìm kiếm kết hợp + Xây dựng lộ trình với tùy chọn lọc theo thời gian mở cửa
        """
        return await self.route_service.build_routes(
            latitude, longitude, transportation_mode, semantic_query, user_id,
            max_time_minutes, target_places, max_routes, top_k_semantic,
            customer_like, current_datetime
        )
