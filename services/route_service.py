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
        self.base_service = SemanticSearchBase(db_pool, redis_client, vector_store, embedder)
        
        # Get singleton instances từ base service
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
        current_datetime: Optional[datetime] = None,
        duration_mode: bool = False 
    ) -> Dict[str, Any]:
        """
        Delegate to RouteSearchService.search_combined_with_routes
        Tìm kiếm kết hợp + Xây dựng lộ trình với tùy chọn lọc theo thời gian mở cửa
        """
        return await self.route_service.build_routes(
            latitude, longitude, transportation_mode, semantic_query, user_id,
            max_time_minutes, target_places, max_routes, top_k_semantic,
            customer_like, current_datetime, duration_mode
        )
    
    async def replace_poi(
        self,
        user_id: UUID,
        route_id: str,
        poi_id_to_replace: str,
        current_datetime: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Replace POI trong route bằng POI khác cùng category
        
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
            # Khởi tạo replaced_pois_by_category nếu chưa có
            if 'replaced_pois_by_category' not in all_routes_metadata:
                all_routes_metadata['replaced_pois_by_category'] = {}
            
            replaced_pois_by_category = all_routes_metadata['replaced_pois_by_category']
            if category not in replaced_pois_by_category:
                replaced_pois_by_category[category] = []
            
            available_poi_ids = all_routes_metadata['available_pois_by_category'].get(category, [])
            total_available = len(available_poi_ids)
            
            # Lọc bỏ các POI đã có trong route VÀ POI đã từng thay thế
            current_poi_ids = {poi['poi_id'] for poi in route_metadata['pois']}
            replaced_poi_ids = set(replaced_pois_by_category[category])
            available_poi_ids = [
                pid for pid in available_poi_ids 
                if pid not in current_poi_ids and pid not in replaced_poi_ids
            ]
            
            print(f"📊 Category '{category}': Total={total_available}, In route={len(current_poi_ids)}, Replaced={len(replaced_poi_ids)}, Available={len(available_poi_ids)}")
            
            # Nếu hết POI khả dụng, reset danh sách đã thay thế và thử lại
            if not available_poi_ids:
                print(f"🔄 Category '{category}' đã hết POI - RESET replaced list (đã dùng {len(replaced_poi_ids)} POI)")
                replaced_pois_by_category[category] = []
                available_poi_ids = [
                    pid for pid in all_routes_metadata['available_pois_by_category'].get(category, [])
                    if pid not in current_poi_ids
                ]
                print(f"✅ Reset xong - Available sau reset: {len(available_poi_ids)} POI")
                
                # Nếu vẫn không có POI (đã hết hẳn), trả về success với array rỗng
                if not available_poi_ids:
                    return {
                        "status": "success",
                        "message": f"No more alternative POIs available in category '{category}'",
                        "candidates": []
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
            
            # Nếu không có POI data trong cache, trả về success với array rỗng
            if not candidate_pois:
                return {
                    "status": "success",
                    "message": f"No POI data found in cache for category '{category}'",
                    "candidates": []
                }
            
            # 6. Chọn top 3 POI tốt nhất (validate opening hours)
            # Sử dụng POI trước đó làm reference point để tính distance
            reference_point = None
            if poi_position > 0:
                prev_poi_id = route_metadata['pois'][poi_position - 1]['poi_id']
                prev_poi_ref = await self.cache_service.get_poi_data(prev_poi_id)
                if prev_poi_ref and prev_poi_ref.get('lat') and prev_poi_ref.get('lon'):
                    reference_point = (prev_poi_ref['lat'], prev_poi_ref['lon'])
            elif len(route_metadata['pois']) > 1:
                # Nếu là POI đầu, dùng POI thứ 2 làm reference
                next_poi_id = route_metadata['pois'][1]['poi_id']
                next_poi_ref = await self.cache_service.get_poi_data(next_poi_id)
                if next_poi_ref and next_poi_ref.get('lat') and next_poi_ref.get('lon'):
                    reference_point = (next_poi_ref['lat'], next_poi_ref['lon'])
            
            # Chọn top 3 POI thay thế
            top_pois = self.poi_update_service.select_top_n_pois(
                candidate_pois,
                n=3,
                current_datetime=current_datetime,
                reference_point=reference_point
            )
            
            # Nếu không có POI nào, trả về success với array rỗng
            if not top_pois:
                return {
                    "status": "success",
                    "message": f"No suitable POIs found in category '{category}'",
                    "candidates": []
                }
            
            # 7. Lấy POI cũ để tính distance
            old_poi_data = await self.cache_service.get_poi_data(poi_id_to_replace)
            
            if not old_poi_data:
                return {
                    "status": "error",
                    "error": f"Old POI data not found: {poi_id_to_replace}"
                }
            
            # 8. Lấy POI trước và sau (nếu có) để tính travel time
            prev_poi_data = None
            next_poi_data = None
            
            if poi_position > 0:
                prev_poi_id = route_metadata['pois'][poi_position - 1]['poi_id']
                prev_poi_data = await self.cache_service.get_poi_data(prev_poi_id)
            
            if poi_position < len(route_metadata['pois']) - 1:
                next_poi_id = route_metadata['pois'][poi_position + 1]['poi_id']
                next_poi_data = await self.cache_service.get_poi_data(next_poi_id)
            
            # 9. Format top 3 POI candidates với đầy đủ thông tin
            from radius_logic.route.route_config import RouteConfig
            from utils.time_utils import TimeUtils
            
            transportation_mode = all_routes_metadata.get('transportation_mode', 'DRIVING')
            formatted_candidates = []
            
            for poi in top_pois:
                # Tính travel_time từ POI trước
                travel_time_minutes = 0
                if prev_poi_data and prev_poi_data.get('lat') and prev_poi_data.get('lon'):
                    distance_km = self.poi_update_service.geo_utils.calculate_distance_haversine(
                        prev_poi_data['lat'], prev_poi_data['lon'],
                        poi['lat'], poi['lon']
                    )
                    speed = RouteConfig.TRANSPORTATION_SPEEDS.get(transportation_mode.upper(), 40)
                    travel_time_minutes = round((distance_km / speed) * 60, 1)
                
                # Stay time
                stay_time_minutes = RouteConfig.DEFAULT_STAY_TIME
                
                # Tính distance changes so với POI cũ
                distance_changes = self.poi_update_service.calculate_distance_changes(
                    old_poi_data,
                    poi,
                    prev_poi_data,
                    next_poi_data
                )
                
                time_changes = self.poi_update_service.calculate_travel_time_changes(
                    distance_changes,
                    transportation_mode
                )
                
                # Format POI
                formatted_poi = {
                    "place_id": poi['id'],
                    "place_name": poi.get('name', 'N/A'),
                    "poi_type": poi.get('poi_type', ''),
                    "poi_type_clean": poi.get('poi_type_clean', ''),
                    "main_subcategory": poi.get('main_subcategory'),
                    "specialization": poi.get('specialization'),
                    "category": category,
                    "address": poi.get('address', ''),
                    "lat": poi.get('lat'),
                    "lon": poi.get('lon'),
                    "rating": poi.get('rating', 0.5),
                    "open_hours": poi.get('open_hours', []),
                    "travel_time_minutes": travel_time_minutes,
                    "stay_time_minutes": stay_time_minutes,
                    "distance_changes": distance_changes,
                    "time_changes": time_changes
                }
                
                # Thêm arrival_time và opening_hours_today nếu có current_datetime
                if current_datetime and prev_poi_data:
                    # Tính arrival_time = current_datetime + travel_time
                    from datetime import timedelta
                    arrival_time = current_datetime + timedelta(minutes=travel_time_minutes)
                    formatted_poi['arrival_time'] = arrival_time.strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Format opening hours cho ngày arrival
                    open_hours = TimeUtils.normalize_open_hours(poi.get('open_hours'))
                    opening_hours_today = TimeUtils.get_opening_hours_for_day(open_hours, arrival_time)
                    formatted_poi['opening_hours_today'] = opening_hours_today
                
                formatted_candidates.append(formatted_poi)
            
            # 10. Lưu 3 POI candidates vào danh sách đã thay thế để không đề xuất lại
            selected_ids = [p['id'] for p in top_pois]
            for sid in selected_ids:
                if sid not in replaced_pois_by_category[category]:
                    replaced_pois_by_category[category].append(sid)
            all_routes_metadata['replaced_pois_by_category'] = replaced_pois_by_category
            
            print(f"💾 Đã lưu {len(selected_ids)} candidate(s) vào replaced list - Category '{category}' hiện có {len(replaced_pois_by_category[category])} POI đã thay thế")
            
            # Persist metadata vào Redis
            if self.redis_client:
                import json
                cache_key = f"route_metadata:{user_id}"
                await self.redis_client.setex(
                    cache_key,
                    3600,
                    json.dumps(all_routes_metadata)
                )
            
            return {
                "status": "success",
                "message": f"Found {len(formatted_candidates)} alternative POI(s) for category '{category}'",
                "old_poi_id": poi_id_to_replace,
                "category": category,
                "route_id": route_id,
                "candidates": formatted_candidates
            }
            
        except Exception as e:
            import traceback
            print(f"❌ Error in update_poi_in_route: {str(e)}")
            print(traceback.format_exc())
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def confirm_replace_poi(
        self,
        user_id: UUID,
        route_id: str,
        old_poi_id: str,
        new_poi_id: str
    ) -> Dict[str, Any]:
        """
        Xác nhận thay thế POI và cập nhật cache
        
        Args:
            user_id: UUID của user
            route_id: ID của route (1, 2, 3, ...)
            old_poi_id: ID của POI cũ bị thay thế
            new_poi_id: ID của POI mới user đã chọn
            
        Returns:
            Dict chứa thông tin route đã được cập nhật
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
            
            # 3. Tìm POI cần thay thế trong route
            poi_position = None
            old_category = None
            
            for idx, poi in enumerate(route_metadata['pois']):
                if poi['poi_id'] == old_poi_id:
                    poi_position = idx
                    old_category = poi['category']
                    break
            
            if poi_position is None:
                return {
                    "status": "error",
                    "error": f"POI {old_poi_id} not found in route"
                }
            
            # 4. Lấy thông tin POI mới từ cache
            new_poi_data = await self.cache_service.get_poi_data(new_poi_id)
            
            if not new_poi_data:
                return {
                    "status": "error",
                    "error": f"New POI data not found: {new_poi_id}"
                }
            
            # 5. Cập nhật POI trong route metadata
            route_metadata['pois'][poi_position] = {
                "poi_id": new_poi_id,
                "category": old_category
            }
            
            all_routes_metadata['routes'][route_id] = route_metadata
            
            # 6. Đánh dấu new_poi_id đã được sử dụng trong replaced_pois_by_category
            if 'replaced_pois_by_category' not in all_routes_metadata:
                all_routes_metadata['replaced_pois_by_category'] = {}
            
            replaced_pois_by_category = all_routes_metadata['replaced_pois_by_category']
            if old_category not in replaced_pois_by_category:
                replaced_pois_by_category[old_category] = []
            
            if new_poi_id not in replaced_pois_by_category[old_category]:
                replaced_pois_by_category[old_category].append(new_poi_id)
            
            all_routes_metadata['replaced_pois_by_category'] = replaced_pois_by_category
            
            print(f"✅ Confirmed replace: {old_poi_id} → {new_poi_id}")
            print(f"📊 Category '{old_category}' hiện có {len(replaced_pois_by_category[old_category])} POI đã được chọn/thay thế")
            
            # 7. Lưu lại cache
            if self.redis_client:
                import json
                cache_key = f"route_metadata:{user_id}"
                await self.redis_client.setex(
                    cache_key,
                    3600,
                    json.dumps(all_routes_metadata)
                )
            
            # 8. Trả về thông tin route đã cập nhật
            updated_pois = []
            for idx, poi in enumerate(route_metadata['pois'], 1):
                poi_data = await self.cache_service.get_poi_data(poi['poi_id'])
                if poi_data:
                    updated_pois.append(
                        self.poi_update_service.format_poi_for_response(
                            poi['poi_id'],
                            poi_data,
                            poi['category'],
                            idx
                        )
                    )
            
            return {
                "status": "success",
                "message": f"Successfully replaced POI {old_poi_id} with {new_poi_id}",
                "route_id": route_id,
                "updated_pois": updated_pois
            }
            
        except Exception as e:
            import traceback
            print(f"❌ Error in confirm_replace_poi: {str(e)}")
            print(traceback.format_exc())
            return {
                "status": "error",
                "error": str(e)
            }    
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
        Replace route: Xây dựng route mới với ID = route_id_to_replace + 1, 
        xoá route cũ, chỉ lưu route mới (tiết kiệm bộ nhớ)
        
        Args:
            user_id: UUID của user
            route_id_to_replace: ID của route cần replace (1, 2, 3, ...)
            latitude, longitude: Tọa độ user
            transportation_mode: Phương tiện di chuyển
            semantic_query: Query ngữ nghĩa
            max_time_minutes: Thời gian tối đa (phút)
            target_places: Số địa điểm mỗi lộ trình
            top_k_semantic: Số địa điểm từ semantic search
            customer_like: Tự động thêm Entertainment nếu True
            current_datetime: Thời điểm hiện tại để validate opening hours
            
        Returns:
            Dict chứa route mới đã được xây dựng
        """
        try:
            # 1. Lấy cache hiện tại để kiểm tra
            all_routes_metadata = await self.cache_service.get_route_metadata(user_id)
            
            if not all_routes_metadata:
                return {
                    "status": "error",
                    "error": f"No cache found for user {user_id}. Please build routes first."
                }
            
            # 2. Kiểm tra route_id_to_replace có tồn tại không
            route_key = str(route_id_to_replace)
            if route_key not in all_routes_metadata.get('routes', {}):
                return {
                    "status": "error",
                    "error": f"Route '{route_id_to_replace}' not found. Available routes: {list(all_routes_metadata.get('routes', {}).keys())}"
                }
            
            print(f"🔄 Replace route {route_id_to_replace}: Building route {route_id_to_replace + 1}")
            
            # 3. Build routes lại với max_routes = route_id_to_replace + 1
            new_route_id = route_id_to_replace + 1
            
            result = await self.route_service.build_routes(
                latitude=latitude,
                longitude=longitude,
                transportation_mode=transportation_mode,
                semantic_query=semantic_query,
                user_id=user_id,
                max_time_minutes=max_time_minutes,
                target_places=target_places,
                max_routes=new_route_id,  # Cộng thêm 1 để có route mới
                top_k_semantic=top_k_semantic,
                customer_like=customer_like,
                current_datetime=current_datetime,
                duration_mode=duration_mode
            )
            
            if result["status"] == "error":
                return result
            
            # 4. Lấy route cuối cùng (route_id = new_route_id)
            routes = result.get("routes", [])
            if len(routes) < new_route_id:
                return {
                    "status": "error",
                    "error": f"Failed to build route {new_route_id}. Only {len(routes)} routes built."
                }
            
            new_route = routes[new_route_id - 1]  # routes là array 0-indexed
            
            # 5. Lấy cache mới từ Redis (đã được update bởi build_routes)
            updated_cache = await self.cache_service.get_route_metadata(user_id)
            
            # 6. Xoá route cũ, chỉ giữ route mới (tiết kiệm bộ nhớ)
            new_cache_data = updated_cache.copy()
            new_cache_data['routes'] = {
                str(new_route_id): updated_cache['routes'][str(new_route_id)]
            }
            
            # 7. Lưu cache mới
            if self.redis_client:
                import json
                cache_key = f"route_metadata:{user_id}"
                await self.redis_client.setex(
                    cache_key,
                    3600,
                    json.dumps(new_cache_data)
                )
            
            print(f"✅ Replace complete: Route {route_id_to_replace} đã xoá, chỉ lưu route {new_route_id}")
            
            return {
                "status": "success",
                "message": f"Route {route_id_to_replace} replaced with route {new_route_id}",
                "old_route_id": route_id_to_replace,
                "new_route_id": new_route_id,
                "routes": [new_route]
            }
            
        except Exception as e:
            import traceback
            print(f"❌ Error in replace_route: {str(e)}")
            print(traceback.format_exc())
            return {
                "status": "error",
                "error": str(e)
            }