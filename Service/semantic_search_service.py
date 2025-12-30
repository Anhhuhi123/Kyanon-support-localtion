"""
Semantic Search Service
Service xử lý logic tìm kiếm ngữ nghĩa (semantic search) với vector embeddings
Kết hợp với filter theo danh sách ID từ PostGIS
"""

from typing import List, Dict, Any
from retrieval.qdrant_vector_store import QdrantVectorStore
from retrieval.embeddings import EmbeddingGenerator
from qdrant_client.models import Filter, FieldCondition, MatchAny


class SemanticSearchService:
    """Service xử lý logic tìm kiếm ngữ nghĩa"""
    
    def __init__(self):
        """Khởi tạo service với Qdrant và Embedding generator"""
        self.vector_store = QdrantVectorStore()
        self.embedder = EmbeddingGenerator()
    
    def search_by_query_with_filter(
        self,
        query: str,
        id_list: List[str],
        top_k: int = 10
    ) -> Dict[str, Any]:
        """
        Tìm kiếm địa điểm theo query ngữ nghĩa, chỉ trong danh sách ID cho trước
        
        Args:
            query: Câu query tìm kiếm (vd: "Travel", "Nature & View")
            id_list: Danh sách ID của các địa điểm cần tìm kiếm (từ PostGIS)
            top_k: Số lượng kết quả trả về tối đa
            
        Returns:
            Dict chứa kết quả với các trường:
            - status: "success" hoặc "error"
            - query: query đã tìm kiếm
            - total_results: số lượng kết quả
            - results: danh sách địa điểm với score tương đồng
        """
        try:
            # Kiểm tra danh sách ID
            if not id_list or len(id_list) == 0:
                return {
                    "status": "error",
                    "error": "Empty ID list provided",
                    "query": query,
                    "total_results": 0,
                    "results": []
                }
            
            # 1. Sinh embedding cho query
            print(f"Generating embedding for query: {query}")
            query_embedding = self.embedder.generate_single_embedding(query)
            
            # 2. Tạo filter để chỉ tìm trong danh sách ID
            print(f"Creating filter for {len(id_list)} IDs: {id_list[:3]}...")  # Show first 3 IDs
            id_filter = Filter(
                must=[
                    FieldCondition(
                        key="id",
                        match=MatchAny(any=id_list)
                    )
                ]
            )
            
            # 3. Tìm kiếm trong Qdrant với filter
            print(f"Searching in Qdrant with {len(id_list)} IDs filter...")
            search_results = self.vector_store.search(
                query_embedding=query_embedding,
                k=top_k,
                query_filter=id_filter
            )
            
            print(f"Search returned {len(search_results) if search_results else 0} results")
            
            # Kiểm tra nếu kết quả rỗng hoặc không hợp lệ
            if not search_results or not isinstance(search_results, list):
                print("⚠️ No results found or invalid search results")
                return {
                    "status": "success",
                    "query": query,
                    "filter_ids_count": len(id_list),
                    "total_results": 0,
                    "results": []
                }
            
            # 4. Format kết quả
            results = []
            for hit in search_results:
                result = {
                    "score": hit.score,
                    "id": hit.payload.get("id"),
                    "name": hit.payload.get("name"),
                    "poi_type": hit.payload.get("poi_type"),
                    "address": hit.payload.get("address"),
                    "lat": hit.payload.get("lat"),
                    "lon": hit.payload.get("long"),
                    "text": hit.payload.get("text")
                }
                results.append(result)
            
            return {
                "status": "success",
                "query": query,
                "filter_ids_count": len(id_list),
                "total_results": len(results),
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
        top_k_spatial: int = 50,
        top_k_semantic: int = 10
    ) -> Dict[str, Any]:
        """
        Tìm kiếm kết hợp: Spatial search (PostGIS) + Semantic search (Qdrant)
        
        Workflow:
        1. Tìm kiếm địa điểm gần theo tọa độ và phương tiện (PostGIS)
        2. Lấy danh sách ID từ kết quả bước 1
        3. Tìm kiếm semantic trong danh sách ID đó (Qdrant)
        
        Args:
            latitude: Vĩ độ
            longitude: Kinh độ
            transportation_mode: Phương tiện di chuyển
            semantic_query: Query ngữ nghĩa (vd: "Travel", "Nature & View")
            top_k_spatial: Số lượng kết quả spatial search
            top_k_semantic: Số lượng kết quả semantic cuối cùng
            
        Returns:
            Dict chứa kết quả kết hợp
        """
        from Service.location_service import LocationService
        from config.config import Config
        
        try:
            # 1. Tìm kiếm spatial
            location_service = LocationService(Config.get_db_connection_string())
            spatial_results = location_service.find_nearest_locations(
                latitude=latitude,
                longitude=longitude,
                transportation_mode=transportation_mode,
                top_k=top_k_spatial
            )
            
            if spatial_results["status"] != "success":
                return {
                    "status": "error",
                    "error": "Spatial search failed",
                    "spatial_error": spatial_results.get("error"),
                    "results": []
                }
            
            # 2. Lấy danh sách ID
            id_list = [loc["id"] for loc in spatial_results["results"]]
            
            if not id_list:
                return {
                    "status": "success",
                    "message": "No locations found in spatial search",
                    "spatial_results": spatial_results,
                    "semantic_results": {
                        "status": "success",
                        "query": semantic_query,
                        "total_results": 0,
                        "results": []
                    }
                }
            
            # 3. Tìm kiếm semantic trong danh sách ID
            semantic_results = self.search_by_query_with_filter(
                query=semantic_query,
                id_list=id_list,
                top_k=top_k_semantic
            )
            
            return {
                "status": "success",
                "spatial_results": spatial_results,
                "semantic_results": semantic_results
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "results": []
            }
