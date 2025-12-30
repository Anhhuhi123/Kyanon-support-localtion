"""
Semantic Search API
API endpoints cho tìm kiếm ngữ nghĩa với vector embeddings (Qdrant)
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from Service.semantic_search_service import SemanticSearchService

# Initialize router
router = APIRouter(prefix="/api/v1/semantic", tags=["Semantic Search (Qdrant)"])

# Service instance sẽ được set từ api_server.py startup event
_semantic_service_instance = None


def get_semantic_service():
    """Lấy singleton instance của SemanticSearchService"""
    global _semantic_service_instance
    if _semantic_service_instance is None:
        # Fallback: nếu chưa init từ startup, init ngay
        from Service.semantic_search_service import SemanticSearchService
        _semantic_service_instance = SemanticSearchService()
    return _semantic_service_instance


# Request Models
class SemanticSearchRequest(BaseModel):
    """Request model cho tìm kiếm ngữ nghĩa (không cần filter ID)"""
    query: str = Field(..., description="Câu query tìm kiếm ngữ nghĩa", json_schema_extra={"example": "Travel"})
    top_k: Optional[int] = Field(10, description="Số lượng kết quả", json_schema_extra={"example": 10})


class CombinedSearchRequest(BaseModel):
    """Request model cho tìm kiếm kết hợp spatial + semantic"""
    latitude: float = Field(..., description="Vĩ độ", json_schema_extra={"example": 10.8294811})
    longitude: float = Field(..., description="Kinh độ", json_schema_extra={"example": 106.7737852})
    transportation_mode: str = Field(..., description="Phương tiện (WALKING/BICYCLING/TRANSIT/FLEXIBLE/DRIVING)", json_schema_extra={"example": "WALKING"})
    semantic_query: str = Field(..., description="Câu query ngữ nghĩa", json_schema_extra={"example": "Travel"})
    top_k: Optional[int] = Field(10, description="Số lượng kết quả semantic cuối cùng", json_schema_extra={"example": 10})


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
        result = get_semantic_service().search_by_query(
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
        result = get_semantic_service().search_combined(
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
