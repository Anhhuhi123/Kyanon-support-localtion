"""
Semantic Search API
API endpoints cho tìm kiếm ngữ nghĩa với vector embeddings (Qdrant)
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from fastapi import APIRouter, HTTPException
from services.route_service import SemanticSearchService
from pydantics.route import SemanticSearchRequest, CombinedSearchRequest, RouteSearchRequest

# Initialize router
router = APIRouter(prefix="/api/v1/route", tags=["Route Search (Qdrant)"])
# Service instance sẽ được set từ api_server.py startup event
_route_service_instance = None

def get_semantic_service():
    """Lấy singleton instance của SemanticSearchService"""
    global _route_service_instance
    if _route_service_instance is None:
        # Fallback: nếu chưa init từ startup, init ngay
        from services.route_service import SemanticSearchService
        _route_service_instance = SemanticSearchService()
    return _route_service_instance


@router.post("/search")
async def semantic_search(request: SemanticSearchRequest):
    """
    Tìm kiếm địa điểm theo ngữ nghĩa (không cần filter ID)
    
    Args:
        query: Câu query tìm kiếm (vd: "Travel", "Nature & View")
        top_k: Số lượng kết quả trả về
    
    Returns:
        JSON response với danh sách địa điểm phù hợp nhất với query
    """
    try:
        result = await get_semantic_service().search_by_query(
            query=request.query,
            top_k=request.top_k
        )
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/combined")
async def combined_search(request: CombinedSearchRequest):
    """
    Tìm kiếm kết hợp: Spatial (PostGIS) + Semantic (Qdrant)
    
    Workflow:
    1. Tìm kiếm TẤT CẢ địa điểm gần (>= 50) theo tọa độ và phương tiện
    2. Lấy danh sách ID từ kết quả spatial
    3. Tìm kiếm semantic trong danh sách ID đó, trả về top_k kết quả có similarity cao nhất
    
    Args:
        latitude: Vĩ độ
        longitude: Kinh độ
        transportation_mode: Phương tiện
        semantic_query: Query ngữ nghĩa
        top_k: Số lượng kết quả semantic cuối cùng (mặc định 10)
    
    Returns:
        JSON response CHỈ với top_k địa điểm có similarity cao nhất
    """
    try:
        result = await get_semantic_service().search_combined(
            latitude=request.latitude,
            longitude=request.longitude,
            transportation_mode=request.transportation_mode,
            semantic_query=request.semantic_query,
            top_k_semantic=request.top_k
        )
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/routes")
async def route_search(request: RouteSearchRequest):
    """
    Tìm kiếm và xây dựng lộ trình tối ưu
    
    Workflow:
    1. Spatial search (PostGIS) → Tìm tất cả địa điểm gần (>= 50)
    2. Semantic search (Qdrant) → Top 10 địa điểm phù hợp nhất với nhu cầu
    3. Route building (Greedy) → Xây dựng tối đa 3 lộ trình tốt nhất
    
    Args:
        latitude: Vĩ độ user
        longitude: Kinh độ user
        transportation_mode: Phương tiện di chuyển
        semantic_query: Query ngữ nghĩa (nhu cầu người dùng)
        max_time_minutes: Thời gian tối đa (phút) - mặc định 180
        target_places: Số địa điểm mỗi lộ trình - mặc định 5
        max_routes: Số lộ trình tối đa - mặc định 3
        top_k_semantic: Số địa điểm từ semantic search - mặc định 10
    
    Returns:
        JSON response với tối đa 3 lộ trình tốt nhất
        
    Example Response:
        {
            "status": "success",
            "routes": [
                {
                    "route_id": 1,
                    "total_time_minutes": 210,
                    "travel_time_minutes": 45,
                    "stay_time_minutes": 165,
                    "total_score": 4.5,
                    "avg_score": 0.9,
                    "efficiency": 2.14,
                    "places": [
                        {
                            "place_id": "A1",
                            "place_name": "Cafe A",
                            "poi_type": "cafe",
                            "address": "...",
                            "lat": 10.77,
                            "lon": 106.70,
                            "score": 0.92,
                            "travel_time_minutes": 10,
                            "stay_time_minutes": 30
                        }
                    ]
                }
            ]
        }
    """
    try:
        result = await get_semantic_service().build_routes(
            latitude=request.latitude,
            longitude=request.longitude,
            transportation_mode=request.transportation_mode,
            semantic_query=request.semantic_query,
            max_time_minutes=request.max_time_minutes,
            target_places=request.target_places,
            max_routes=request.max_routes,
            top_k_semantic=request.top_k_semantic,
            customer_like=request.customer_like or False,
            current_datetime=request.current_time
        )
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
