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
from services.cache_search import CacheSearchService
from radius_logic.update_poi import POIUpdateService
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
        
        # Initialize cache and POI update services
        self.cache_service = CacheSearchService(redis_client)
        self.poi_update_service = POIUpdateService()
        
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
    
    async def update_poi_in_route(
        self,
        user_id: UUID,
        route_id: str,
        poi_id_to_replace: str,
        current_datetime: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Update POI trong route bằng POI khác cùng category
        
        Args:
            user_id: UUID của user
            route_id: ID của route (1, 2, 3, ...)
            poi_id_to_replace: ID của POI cần thay thế
            current_datetime: Thời điểm hiện tại (để validate opening hours)
            
        Returns:
            Dict chứa POI mới và thông tin route đã update
        """
        try:
            # 1. Lấy route metadata từ cache
            all_routes_metadata = await self.cache_service.get_route_metadata(user_id)
            
            if not all_routes_metadata:
                return {
                    "status": "error",
                    "error": f"Route not found in cache for user {user_id}"
                }
            
            # 2. Lấy route cụ thể
            if route_id not in all_routes_metadata.get('routes', {}):
                return {
                    "status": "error",
                    "error": f"Route '{route_id}' not found. Available routes: {list(all_routes_metadata.get('routes', {}).keys())}"
                }
            
            route_metadata = all_routes_metadata['routes'][route_id]
            
            # 3. Tìm POI cần thay thế và lấy category
            poi_to_replace = None
            poi_position = None
            
            for idx, poi in enumerate(route_metadata['pois']):
                if poi['poi_id'] == poi_id_to_replace:
                    poi_to_replace = poi
                    poi_position = idx
                    break
            
            if not poi_to_replace:
                return {
                    "status": "error",
                    "error": f"POI {poi_id_to_replace} not found in route"
                }
            
            category = poi_to_replace['category']
            
            # 4. Lấy danh sách POI available cùng category
            available_poi_ids = all_routes_metadata['available_pois_by_category'].get(category, [])
            
            # Lọc bỏ các POI đã có trong route
            current_poi_ids = {poi['poi_id'] for poi in route_metadata['pois']}
            available_poi_ids = [pid for pid in available_poi_ids if pid not in current_poi_ids]
            
            if not available_poi_ids:
                return {
                    "status": "error",
                    "error": f"No alternative POIs available in category '{category}'"
                }
            
            # 5. Lấy thông tin chi tiết POI từ cache
            candidate_pois = []
            for poi_id in available_poi_ids:
                poi_data = await self.cache_service.get_poi_data(poi_id)
                
                if poi_data:
                    poi_dict = poi_data.copy()
                    poi_dict['id'] = poi_id
                    poi_dict['category'] = category
                    candidate_pois.append(poi_dict)
            
            if not candidate_pois:
                return {
                    "status": "error",
                    "error": f"No POI data found in cache for category '{category}'"
                }
            
            # 6. Chọn POI tốt nhất (validate opening hours)
            new_poi = self.poi_update_service.select_best_poi(
                candidate_pois,
                current_datetime
            )
            
            if not new_poi:
                return {
                    "status": "error",
                    "error": f"No POIs open at {current_datetime} in category '{category}'" if current_datetime else "Failed to select POI"
                }
            
            # 7. Lấy POI cũ để tính distance
            old_poi_data = await self.cache_service.get_poi_data(poi_id_to_replace)
            
            if not old_poi_data:
                return {
                    "status": "error",
                    "error": f"Old POI data not found: {poi_id_to_replace}"
                }
            
            # 8. Lấy POI trước và sau (nếu có)
            prev_poi_data = None
            next_poi_data = None
            
            if poi_position > 0:
                prev_poi_id = route_metadata['pois'][poi_position - 1]['poi_id']
                prev_poi_data = await self.cache_service.get_poi_data(prev_poi_id)
            
            if poi_position < len(route_metadata['pois']) - 1:
                next_poi_id = route_metadata['pois'][poi_position + 1]['poi_id']
                next_poi_data = await self.cache_service.get_poi_data(next_poi_id)
            
            # 9. Tính toán distance changes
            distance_changes = self.poi_update_service.calculate_distance_changes(
                old_poi_data,
                new_poi,
                prev_poi_data,
                next_poi_data
            )
            
            # 10. Update route metadata trong cache
            route_metadata['pois'][poi_position] = {
                "poi_id": str(new_poi['id']),
                "category": category
            }
            
            all_routes_metadata['routes'][route_id] = route_metadata
            
            # Lưu lại cache
            if self.redis_client:
                import json
                cache_key = f"route_metadata:{user_id}"
                await self.redis_client.setex(
                    cache_key,
                    3600,
                    json.dumps(all_routes_metadata)
                )
            
            # 11. Format POIs đầy đủ cho response
            updated_pois_full = []
            for idx, poi in enumerate(route_metadata['pois'], 1):
                poi_data = await self.cache_service.get_poi_data(poi['poi_id'])
                
                if poi_data:
                    updated_pois_full.append(
                        self.poi_update_service.format_poi_for_response(
                            poi['poi_id'],
                            poi_data,
                            poi['category'],
                            idx
                        )
                    )
            
            return {
                "status": "success",
                "message": f"Successfully replaced POI {poi_id_to_replace} with {new_poi['id']}",
                "old_poi_id": poi_id_to_replace,
                "new_poi": new_poi,
                "category": category,
                "route_id": route_id,
                "updated_pois": updated_pois_full,
                "distance_changes": distance_changes
            }
            
        except Exception as e:
            import traceback
            print(f"❌ Error in update_poi_in_route: {str(e)}")
            print(traceback.format_exc())
            return {
                "status": "error",
                "error": str(e)
            }
