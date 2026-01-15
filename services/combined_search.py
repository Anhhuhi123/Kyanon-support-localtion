"""
Combined Search Service
Kết hợp Spatial search (PostGIS) + Semantic search (Qdrant)
"""
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
import asyncpg
import redis.asyncio as aioredis
from services.qdrant_search import SemanticSearchBase
from services.location_service import LocationService
from services.poi_service import PoiService
from utils.time_utils import TimeUtils
from uuid import UUID

class CombinedSearchService(SemanticSearchBase):
    """Service kết hợp spatial + semantic search"""
    
    def __init__(self, db_pool: asyncpg.Pool = None, redis_client: aioredis.Redis = None,
                 vector_store=None, embedder=None):
        """
        Khởi tạo combined service
        
        Args:
            db_pool: Async PostgreSQL connection pool
            redis_client: Async Redis client
            vector_store: Shared QdrantVectorStore instance
            embedder: Shared EmbeddingGenerator instance
        """
        super().__init__(db_pool, redis_client, vector_store, embedder)
    
    async def search_combined(
        self,
        latitude: float,
        longitude: float,
        transportation_mode: str,
        semantic_query: str,
        top_k_semantic: int = 10
    ) -> Dict[str, Any]:
        """
        Tìm kiếm kết hợp: Spatial search (PostGIS) + Semantic search (Qdrant)
        
        Workflow:
        1. Tìm kiếm TẤT CẢ địa điểm gần (>= 50) theo tọa độ và phương tiện (PostGIS)
        2. Lấy danh sách ID từ kết quả bước 1
        3. Tìm kiếm semantic trong danh sách ID đó, trả về top_k_semantic kết quả có similarity cao nhất
        
        Args:
            latitude: Vĩ độ
            longitude: Kinh độ
            transportation_mode: Phương tiện di chuyển
            semantic_query: Query ngữ nghĩa (vd: "Travel", "Nature & View")
            top_k_semantic: Số lượng kết quả semantic cuối cùng (mặc định 10)
            
        Returns:
            Dict chứa CHỈ top_k_semantic địa điểm có similarity cao nhất
        """
        try:
            # Đo tổng thời gian
            total_start = time.time()
            
            # 1. Tìm kiếm spatial (ASYNC)
            print(f"\n🔍 Step 1: Spatial search...")
            location_service = LocationService(db_pool=self.db_pool, redis_client=self.redis_client)
            spatial_results = await location_service.find_nearest_locations(
                latitude=latitude,
                longitude=longitude,
                transportation_mode=transportation_mode
            )
            
            if spatial_results["status"] != "success":
                return {
                    "status": "error",
                    "error": "Spatial search failed",
                    "spatial_error": spatial_results.get("error"),
                    "results": []
                }
            
            # 2. Lấy danh sách ID từ spatial results
            id_list = [loc["id"] for loc in spatial_results["results"]]
            
            if not id_list:
                return {
                    "status": "success",
                    "message": "No locations found in spatial search",
                    "query": semantic_query,
                    "spatial_info": {
                        "radius_used": spatial_results.get("radius_used"),
                        "total_spatial_locations": 0
                    },
                    "total_results": 0,
                    "results": []
                }
            
            # 3. Tìm kiếm semantic trong danh sách ID (ASYNC)
            print(f"\n🔍 Step 2: Semantic search in {len(id_list)} locations...")
            semantic_start = time.time()
            semantic_results = await self.search_by_query_with_filter(
                query=semantic_query,
                id_list=id_list,
                top_k=top_k_semantic,
                spatial_results=spatial_results["results"]
            )
            semantic_time = time.time() - semantic_start
            
            total_time = time.time() - total_start
            spatial_time = spatial_results.get("execution_time_seconds", 0)
            
            # Lấy timing detail từ semantic search
            semantic_timing = semantic_results.get("timing_detail", {})
            
            print(f"\n⏱️  Timing breakdown:")
            print(f"   • Spatial search: {spatial_time:.3f}s")
            print(f"   • Embedding: {semantic_timing.get('embedding_seconds', 0):.3f}s")
            print(f"   • Qdrant search: {semantic_timing.get('qdrant_search_seconds', 0):.3f}s")
            print(f"   • DB query: {semantic_timing.get('db_query_seconds', 0):.3f}s")
            print(f"   • Total: {total_time:.3f}s")
            
            return {
                "status": "success",
                "query": semantic_query,
                "spatial_info": {
                    "transportation_mode": spatial_results.get("transportation_mode"),
                    "radius_used": spatial_results.get("radius_used"),
                    "total_spatial_locations": len(id_list),
                    "spatial_execution_time": spatial_results.get("execution_time_seconds")
                },
                "total_results": semantic_results.get("total_results", 0),
                "total_execution_time_seconds": round(total_time, 3),
                "timing_detail": semantic_timing,
                "results": semantic_results.get("results", [])
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "results": []
            }
    
    async def search_multi_queries_and_find_locations(
        self,
        latitude: float,
        longitude: float,
        transportation_mode: str,
        semantic_query: str,
        user_id: Optional[UUID] = None,
        top_k_semantic: int = 10,
        customer_like: bool = False,
        current_datetime: Optional[datetime] = None,
        max_time_minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Tìm kiếm kết hợp với hỗ trợ nhiều queries phân cách bằng dấu phẩy
        Mỗi query sẽ truy xuất Qdrant riêng và lấy top 10, đánh dấu category
        Có thể lọc theo thời gian mở cửa
        
        Args:
            latitude: Vĩ độ
            longitude: Kinh độ
            transportation_mode: Phương tiện di chuyển
            semantic_query: Query ngữ nghĩa (có thể nhiều queries phân cách bằng ,)
            top_k_semantic: Số lượng kết quả mỗi query (mặc định 10)
            customer_like: Tự động thêm "Culture & heritage" nếu chỉ có "Food & Local Flavours"
            current_datetime: Thời điểm hiện tại của user (None = không lọc)
            max_time_minutes: Thời gian tối đa user có (None = không lọc)
            
        Returns:
            Dict chứa tất cả POI từ các queries, mỗi POI có thêm field 'category'
        """
        try:
            total_start = time.time()
            
            # Split queries bằng dấu phẩy và trim whitespace
            original_queries = [q.strip() for q in semantic_query.split(',') if q.strip()]

            # Luôn mở rộng "Food & Local Flavours" thành ["Cafe & Bakery", "Restaurant"]
            queries = []
            for q in original_queries:
                if q == "Food & Local Flavours":
                    queries.extend(["Cafe & Bakery", "Restaurant"])
                else:
                    queries.append(q)
            
            # Nếu customer_like=True và input ban đầu CHỈ có 1 query là "Food & Local Flavours", tự động thêm "Culture & heritage"
            if customer_like:
                if len(original_queries) == 1 and original_queries[0] == "Food & Local Flavours":
                    if "Culture & heritage" not in queries:
                        queries.append("Culture & heritage")
                        print(f"✨ CustomerLike=True + single 'Food & Local Flavours' → Tự động thêm 'Culture & heritage'")
            
            # 🍽️ MEAL TIME LOGIC: Tự động thêm Restaurant nếu có overlap với meal times
            if current_datetime and max_time_minutes:
                meal_check = TimeUtils.check_overlap_with_meal_times(current_datetime, max_time_minutes)
                
                # Nếu cần restaurant và user không chọn Food & Local Flavours
                if meal_check["needs_restaurant"] and "Food & Local Flavours" not in original_queries:
                    if "Restaurant" not in queries:
                        queries.append("Restaurant")
                        print(f"🍽️  Tự động thêm 'Restaurant' vì overlap {meal_check['lunch_overlap_minutes']}m lunch / {meal_check['dinner_overlap_minutes']}m dinner")

            if not queries:
                return {
                    "status": "error",
                    "error": "No valid queries provided",
                    "results": []
                }
            
            print(f"\n🔍 Processing {len(queries)} queries: {queries}")
            
            # 1. Spatial search (chỉ 1 lần) với tùy chọn lọc theo thời gian (ASYNC)
            print(f"\n🔍 Step 1: Spatial search...")
            location_service = LocationService(db_pool=self.db_pool, redis_client=self.redis_client)
            spatial_results = await location_service.find_nearest_locations(
                latitude=latitude,
                longitude=longitude,
                transportation_mode=transportation_mode,
                current_datetime=current_datetime,
                max_time_minutes=max_time_minutes
            )
            
            if spatial_results["status"] != "success":
                return {
                    "status": "error",
                    "error": "Spatial search failed",
                    "spatial_error": spatial_results.get("error"),
                    "results": []
                }
            
            id_list = [loc["id"] for loc in spatial_results["results"]]
          
            if not id_list:
                return {
                    "status": "success",
                    "message": "No locations found in spatial search",
                    "query": semantic_query,
                    "spatial_info": {
                        "radius_used": spatial_results.get("radius_used"),
                        "total_spatial_locations": 0
                    },
                    "results": []
                }
            if user_id:
                # get_visited_pois_by_user
                visited_poi_ids = PoiService.get_visited_pois_by_user(user_id) or []
                visited_set = {str(pid) for pid in visited_poi_ids}
                id_list = [pid for pid in id_list if pid not in visited_set]
            
            # 2. Semantic search cho từng query
            # Dùng dict để track POI tốt nhất cho mỗi ID (chọn similarity cao nhất)
            poi_best_match = {}
            
            # Track timing và số POI của từng query
            query_details = []
            total_embedding_time = 0
            total_qdrant_time = 0
            
            for idx, query in enumerate(queries):
                print(f"\n🔍 Step 2.{idx+1}: Semantic search for '{query}'...")
                semantic_start = time.time()
                
                semantic_results = await self.search_by_query_with_filter(
                    query=query,
                    id_list=id_list,
                    top_k=top_k_semantic,
                    spatial_results=spatial_results["results"]
                )
                
                semantic_time = time.time() - semantic_start
                
                # Lấy timing detail từ kết quả
                timing_detail = semantic_results.get("timing_detail", {})
                embed_time = timing_detail.get("embedding_seconds", 0)
                qdrant_time = timing_detail.get("qdrant_search_seconds", 0)
                
                total_embedding_time += embed_time
                total_qdrant_time += qdrant_time
                
                results_count = len(semantic_results.get('results', []))
                print(f"   Query '{query}' took {semantic_time:.3f}s, found {results_count} results")
                
                # Track detail của query này
                query_details.append({
                    "query": query,
                    "pois_count": results_count,
                    "time_seconds": round(semantic_time, 3),
                    "embedding_seconds": round(embed_time, 3),
                    "qdrant_search_seconds": round(qdrant_time, 3)
                })
                
                # Với mỗi POI, chỉ giữ lại option có similarity cao nhất
                for place in semantic_results.get('results', []):
                    place_id = place.get('id')
                    current_similarity = place.get('score', 0.0)
                    
                    if place_id not in poi_best_match:
                        poi_best_match[place_id] = {
                            "place": place,
                            "similarity": current_similarity,
                            "category": query,
                            "category_index": idx
                        }
                    else:
                        existing_similarity = poi_best_match[place_id]["similarity"]
                        if current_similarity > existing_similarity:
                            poi_best_match[place_id] = {
                                "place": place,
                                "similarity": current_similarity,
                                "category": query,
                                "category_index": idx
                            }
            
            # Chuyển dict về list và gán category
            all_results = []
            for place_id, data in poi_best_match.items():
                place = data["place"]
                place['category'] = data["category"]
                place['category_index'] = data["category_index"]
                all_results.append(place)
            
            total_time = time.time() - total_start
            
            print(f"\n✅ Total: {len(all_results)} unique POIs from {len(queries)} queries in {total_time:.3f}s")
            print(f"   (Mỗi POI chỉ thuộc 1 category có similarity cao nhất)")
            
            return {
                "status": "success",
                "query": semantic_query,
                "queries_count": len(queries),
                "query_details": query_details,
                "spatial_info": {
                    "transportation_mode": spatial_results.get("transportation_mode"),
                    "radius_used": spatial_results.get("radius_used"),
                    "total_spatial_locations": len(id_list),
                    "spatial_execution_time": spatial_results.get("execution_time_seconds")
                },
                "total_results": len(all_results),
                "total_execution_time_seconds": round(total_time, 3),
                "timing_detail": {
                    "embedding_seconds": round(total_embedding_time, 3),
                    "qdrant_search_seconds": round(total_qdrant_time, 3)
                },
                "results": all_results
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "results": []
            }
