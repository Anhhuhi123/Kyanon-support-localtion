"""
Semantic Search Service
Service xử lý logic tìm kiếm ngữ nghĩa (semantic search) với vector embeddings
Kết hợp với filter theo danh sách ID từ PostGIS
"""
import time
from radius_logic.route import RouteBuilder
from retrieval.embeddings import EmbeddingGenerator
from typing import List, Dict, Any, Optional, Tuple
from radius_logic.information_location import LocationInfoService
from retrieval.qdrant_vector_store import QdrantVectorStore
from qdrant_client.models import Filter, FieldCondition, MatchAny


class SemanticSearchService:
    """Service xử lý logic tìm kiếm ngữ nghĩa"""
    
    def __init__(self):
        """Khởi tạo service với Qdrant và Embedding generator"""
        self.vector_store = QdrantVectorStore()
        self.embedder = EmbeddingGenerator()
        self.route_builder = RouteBuilder()
        self.location_info_service = LocationInfoService()
    
    def search_by_query(self, query: str, top_k: int = 10) -> Dict[str, Any]:
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
                k=top_k,
                query_filter=None
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
            
            # 4. Query DB để lấy thông tin đầy đủ
            db_start = time.time()
            locations_map = self.location_info_service.get_locations_by_ids(location_ids)
            db_time = time.time() - db_start
            print(f"DB query took {db_time:.3f}s")
            
            # 5. Merge semantic score với location info
            results = []
            for hit in search_results:
                location_info = locations_map.get(hit.id)
                if location_info:
                    result = {
                        "score": hit.score,
                        "poi_type": hit.payload.get("poi_type"),  # Từ Qdrant payload
                        **location_info  # Merge tất cả fields từ DB
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
    
    def search_by_query_with_filter(
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
            
            print(f"Generating embedding for query: {query}")
            embed_start = time.time()
            query_embedding = self.embedder.generate_single_embedding(query)
            embed_time = time.time() - embed_start
            
            print(f"Searching in Qdrant with {len(id_list)} point IDs filter...")
            qdrant_start = time.time()
            # Sử dụng search_by_ids thay vì search với FieldCondition
            search_results = self.vector_store.search_by_ids(
                query_embedding=query_embedding,
                point_ids=id_list,
                k=top_k
            )
            qdrant_time = time.time() - qdrant_start
            
            execution_time = time.time() - start_time
            print(f"⏱️  Embedding: {embed_time:.3f}s, Qdrant search: {qdrant_time:.3f}s")
            
            if not search_results or not isinstance(search_results, list):
                return {
                    "status": "success",
                    "query": query,
                    "filter_ids_count": len(id_list),
                    "total_results": 0,
                    "execution_time_seconds": round(execution_time, 3),
                    "results": []
                }
            
            # Lấy location IDs từ Qdrant results (point.id)
            location_ids = [hit.id for hit in search_results]
            print(f"Fetching {len(location_ids)} location details from DB...")
            
            # ko cần vì redis lưu sẵn rồi 
            # ----------------------
            # Query DB để lấy thông tin đầy đủ
            # db_start = time.time()
            # locations_map = self.location_info_service.get_locations_by_ids(location_ids)
            # print("locations_map", locations_map)
            # print("location_ids", location_ids)
            # db_time = time.time() - db_start
            # print(f"⏱️  DB query: {db_time:.3f}s")

            # ---------------------Bỏ query db----------------
            db_start = time.time()
            location_id_set = set(location_ids)  
            locations_map = {
                item["id"]: {
                    "id": item["id"],
                    "name": item["name"],
                    "lat": item["lat"],
                    "lon": item["lon"],
                    "address": item["address"],
                    "poi_type": item["poi_type"],
                    "rating": item["rating"]
                }
                for item in spatial_results
                if item["id"] in location_id_set
            }
            # print("locations_map", locations_map)
            db_time = time.time() - db_start
            print(f"⏱️  DB query: {db_time:.3f}s")
            
            # Merge semantic score với location info
            results = []
            for hit in search_results:
                location_info = locations_map.get(hit.id)
                if location_info:
                    result = {
                        "score": hit.score,
                        "poi_type": hit.payload.get("poi_type"),  # Từ Qdrant payload
                        **location_info  # Merge fields từ DB
                    }
                    results.append(result)
                else:
                    print(f"⚠️ Location {hit.id} not found in DB")
            
            return {
                "status": "success",
                "query": query,
                "filter_ids_count": len(id_list),
                "total_results": len(results),
                "execution_time_seconds": round(execution_time, 3),
                "timing_detail": {
                    "embedding_seconds": round(embed_time, 3),
                    "qdrant_search_seconds": round(qdrant_time, 3),
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
    
    def search_combined(
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
        from services.location_service import LocationService
        from config.config import Config
        
        try:
            # Đo tổng thời gian
            total_start = time.time()
            
            # 1. Tìm kiếm spatial
            print(f"\n🔍 Step 1: Spatial search...")
            location_service = LocationService(Config.get_db_connection_string())
            spatial_results = location_service.find_nearest_locations(
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
            # print(len(spatial_results["results"]))    
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
            
            # 3. Tìm kiếm semantic trong danh sách ID
            print(f"\n🔍 Step 2: Semantic search in {len(id_list)} locations...")
            semantic_start = time.time()
            semantic_results = self.search_by_query_with_filter(
                query=semantic_query,
                id_list=id_list,
                top_k=top_k_semantic,
                spatial_results = spatial_results["results"]
            )
            semantic_time = time.time() - semantic_start
            
            # Semantic results đã có đầy đủ thông tin từ DB (bao gồm rating)
            # Không cần merge rating từ spatial results nữa
            
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
            
            # Trả về CHỈ semantic results (top_k_semantic địa điểm có similarity cao nhất) + rating
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
                "timing_detail": semantic_timing,  # Pass through timing detail
                "results": semantic_results.get("results", [])
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "results": []
            }
    
    def search_combined_with_routes(
        self,
        latitude: float,
        longitude: float,
        transportation_mode: str,
        semantic_query: str,
        max_time_minutes: int = 180,
        target_places: int = 5,
        max_routes: int = 3,
        top_k_semantic: int = 10
    ) -> Dict[str, Any]:
        """
        Tìm kiếm kết hợp + Xây dựng lộ trình
        
        Workflow:
        1. Spatial search (PostGIS) → TẤT CẢ địa điểm gần (>= 50)
        2. Semantic search (Qdrant) → Top 10 địa điểm phù hợp nhất
        3. Route building (Greedy) → Top 3 lộ trình tốt nhất
        
        Args:
            latitude: Vĩ độ user
            longitude: Kinh độ user
            transportation_mode: Phương tiện di chuyển
            semantic_query: Query ngữ nghĩa
            max_time_minutes: Thời gian tối đa (phút)
            target_places: Số địa điểm mỗi lộ trình
            max_routes: Số lộ trình tối đa
            top_k_semantic: Số địa điểm từ semantic search
            
        Returns:
            Dict chứa routes (top 3 lộ trình) và metadata
        """
        try:
            total_start = time.time()
            
            # 1. Spatial + Semantic search
            search_result = self.search_combined(
                latitude=latitude,
                longitude=longitude,
                transportation_mode=transportation_mode,
                semantic_query=semantic_query,
                top_k_semantic=top_k_semantic
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
            
            # 2. Xây dựng lộ trình
            print(f"\n🔍 Step 3: Building routes from {len(semantic_places)} places...")
            route_start = time.time()
            
            user_location = (latitude, longitude)
            routes = self.route_builder.build_routes(
                user_location=user_location,
                places=semantic_places,
                transportation_mode=transportation_mode,
                max_time_minutes=max_time_minutes,
                target_places=target_places,
                max_routes=max_routes
            )
            
            route_time = time.time() - route_start
            total_time = time.time() - total_start
            
            print(f"⏱️  Route building: {route_time:.3f}s")
            print(f"⏱️  Total execution time: {total_time:.3f}s")
            print(f"✅ Generated {len(routes)} route(s)")
            
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
            print(f"❌ Error in search_combined_with_routes: {str(e)}")
            print(traceback.format_exc())
            return {
                "status": "error",
                "error": str(e),
                "routes": []
            }
