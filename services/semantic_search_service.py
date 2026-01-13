"""
Semantic Search Service
Service xử lý logic tìm kiếm ngữ nghĩa (semantic search) với vector embeddings
Kết hợp với filter theo danh sách ID từ PostGIS
"""
import time
from datetime import datetime
from typing import Optional
from radius_logic.route import RouteBuilder
from retrieval.embeddings import EmbeddingGenerator
from typing import List, Dict, Any, Tuple
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
            # Light RAG: chỉ lấy id + score từ Qdrant (with_payload=False)
            search_results = self.vector_store.search_by_ids(
                query_embedding=query_embedding,
                point_ids=id_list,
                k=top_k,
                with_payload=False,  # Chỉ lấy id+score → nhanh hơn
                hnsw_ef=32  # Giảm ef để tăng tốc (trade-off: độ chính xác giảm ~2%)
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
            print(f"Mapping {len(location_ids)} locations from spatial_results...")
            
            # Dùng trực tiếp spatial_results (đã có full data từ find_nearest_locations)
            fetch_start = time.time()
            location_id_set = set(location_ids)
            locations_map = {
                item["id"]: item
                for item in (spatial_results or [])
                if item["id"] in location_id_set
            }
            fetch_time = time.time() - fetch_start
            print(f"⏱️  Data mapping: {fetch_time:.3f}s ({len(locations_map)}/{len(location_ids)} found)")
            
            # Merge semantic score với location info
            results = []
            for hit in search_results:
                location_info = locations_map.get(hit.id)
                if location_info:
                    result = {
                        "score": hit.score,
                        **location_info  # Merge fields
                    }
                    results.append(result)
                else:
                    print(f"⚠️ Location {hit.id} not found")
            
            return {
                "status": "success",
                "query": query,
                "filter_ids_count": len(id_list),
                "total_results": len(results),
                "execution_time_seconds": round(execution_time, 3),
                "timing_detail": {
                    "embedding_seconds": round(embed_time, 3),
                    "qdrant_search_seconds": round(qdrant_time, 3),
                    "data_fetch_seconds": round(fetch_time, 3)
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
    
    def search_combined_multi_queries(
        self,
        latitude: float,
        longitude: float,
        transportation_mode: str,
        semantic_query: str,
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
        from services.location_service import LocationService
        from config.config import Config
        
        try:
            total_start = time.time()
            
            # Split queries bằng dấu phẩy và trim whitespace
            queries = [q.strip() for q in semantic_query.split(',') if q.strip()]
            
            # Nếu customer_like=True và CHỈ có 1 query là "Food & Local Flavours", tự động thêm "Entertainments"
            if customer_like:
                if len(queries) == 1 and queries[0] == "Food & Local Flavours":
                    queries.append("Culture & heritage")
                    print(f"✨ CustomerLike=True + chỉ có 'Food & Local Flavours' → Tự động thêm 'Entertainments'")
            
            if not queries:
                return {
                    "status": "error",
                    "error": "No valid queries provided",
                    "results": []
                }
            
            print(f"\n🔍 Processing {len(queries)} queries: {queries}")
            
            # 1. Spatial search (chỉ 1 lần) với tùy chọn lọc theo thời gian
            print(f"\n🔍 Step 1: Spatial search...")
            location_service = LocationService(Config.get_db_connection_string())

            spatial_results = location_service.find_nearest_locations(
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
            # -------------------------debug------------------- 
            # spatial_results["results"]
            #   --------------------------------------------
            id_list = [loc["id"] for loc in spatial_results["results"]]
            print("id_list--------------------", len(id_list))
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
            
            # 2. Semantic search cho từng query
            # Dùng dict để track POI tốt nhất cho mỗi ID (chọn similarity cao nhất)
            poi_best_match = {}  # {place_id: {"place": place_dict, "similarity": score, "category": ..., "category_index": ...}}
            
            # Track timing và số POI của từng query
            query_details = []  # [{"query": str, "pois_count": int, "time_seconds": float, "embedding_seconds": float, "qdrant_seconds": float}]
            total_embedding_time = 0
            total_qdrant_time = 0
            
            for idx, query in enumerate(queries):
                print(f"\n🔍 Step 2.{idx+1}: Semantic search for '{query}'...")
                semantic_start = time.time()
                
                semantic_results = self.search_by_query_with_filter(
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
                        # Lần đầu gặp POI này
                        poi_best_match[place_id] = {
                            "place": place,
                            "similarity": current_similarity,
                            "category": query,
                            "category_index": idx
                        }
                    else:
                        # Đã có rồi, so sánh similarity
                        existing_similarity = poi_best_match[place_id]["similarity"]
                        if current_similarity > existing_similarity:
                            # Similarity mới cao hơn -> thay thế
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
                # kiểm tra xem thêm vào đúng chưa
                # print(f" - Place ID {place_id} assigned to category '{data['category']}' with similarity {data['similarity']:.4f}")
            
            total_time = time.time() - total_start
            
            print(f"\n✅ Total: {len(all_results)} unique POIs from {len(queries)} queries in {total_time:.3f}s")
            print(f"   (Mỗi POI chỉ thuộc 1 category có similarity cao nhất)")
            # ------------debug----------------------------------
            # with open("combined_semantic_results.json", "w", encoding="utf-8") as f:
                # import json
                # json.dump(all_results, f, ensure_ascii=False, indent=4)
            # ---------------------------------------------------- 
            return {
                "status": "success",
                "query": semantic_query,
                "queries_count": len(queries),
                "query_details": query_details,  # Thêm thông tin chi tiết mỗi query
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
    
    def search_combined_with_routes(
        self,
        latitude: float,
        longitude: float,
        transportation_mode: str,
        semantic_query: str,
        max_time_minutes: int = 180,
        target_places: int = 5,
        max_routes: int = 3,
        top_k_semantic: int = 10,
        customer_like: bool = False,
        current_datetime: Optional[datetime] = None
    ) -> Dict[str, Any]:
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
            
            # 1. Spatial + Semantic search (hỗ trợ nhiều queries)
            # Pass current_datetime và max_time_minutes để lọc POI theo thời gian
            search_result = self.search_combined_multi_queries(
                latitude=latitude,
                longitude=longitude,
                transportation_mode=transportation_mode,
                semantic_query=semantic_query,
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
            
            # 2. Xây dựng lộ trình với validation thời gian mở cửa
            print(f"\n🔍 Step 3: Building routes from {len(semantic_places)} places...")
            route_start = time.time()
            
            user_location = (latitude, longitude)
            
            routes = self.route_builder.build_routes(
                user_location=user_location,
                places=semantic_places,
                transportation_mode=transportation_mode,
                max_time_minutes=max_time_minutes,
                target_places=target_places,
                max_routes=max_routes,
                current_datetime=current_datetime  # Pass datetime để validate opening hours
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
