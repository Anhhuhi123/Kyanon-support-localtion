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

# Initialize service
semantic_service = SemanticSearchService()


# Request Models
class SemanticSearchRequest(BaseModel):
    """Request model cho tìm kiếm ngữ nghĩa với filter ID"""
    query: str = Field(..., description="Câu query tìm kiếm ngữ nghĩa", json_schema_extra={"example": "Travel"})
    id_list: List[str] = Field(..., description="Danh sách ID cần filter", json_schema_extra={"example": ["0f9d2009-9436-46a4-b354-b0261898a39e"]})
    top_k: Optional[int] = Field(10, description="Số lượng kết quả", json_schema_extra={"example": 10})


class CombinedSearchRequest(BaseModel):
    """Request model cho tìm kiếm kết hợp spatial + semantic"""
    latitude: float = Field(..., description="Vĩ độ", json_schema_extra={"example": 10.8294811})
    longitude: float = Field(..., description="Kinh độ", json_schema_extra={"example": 106.7737852})
    transportation_mode: str = Field(..., description="Phương tiện (WALKING/BICYCLING/TRANSIT/FLEXIBLE/DRIVING)", json_schema_extra={"example": "WALKING"})
    semantic_query: str = Field(..., description="Câu query ngữ nghĩa", json_schema_extra={"example": "Travel"})
    top_k_spatial: Optional[int] = Field(50, description="Số lượng kết quả spatial", json_schema_extra={"example": 50})
    top_k_semantic: Optional[int] = Field(10, description="Số lượng kết quả semantic cuối cùng", json_schema_extra={"example": 10})


@router.post("/search")
async def semantic_search(request: SemanticSearchRequest):
    """
    Tìm kiếm địa điểm theo ngữ nghĩa với filter danh sách ID
    
    Args:
        query: Câu query tìm kiếm (vd: "Travel", "Nature & View")
        id_list: Danh sách ID cần tìm kiếm (từ PostGIS hoặc nguồn khác)
        top_k: Số lượng kết quả trả về
    
    Returns:
        JSON response với danh sách địa điểm phù hợp nhất với query
    """
    try:
        result = semantic_service.search_by_query_with_filter(
            query=request.query,
            id_list=request.id_list,
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
    1. Tìm kiếm địa điểm gần theo tọa độ và phương tiện
    2. Lấy danh sách ID từ kết quả
    3. Tìm kiếm semantic trong danh sách ID đó
    
    Args:
        latitude: Vĩ độ
        longitude: Kinh độ
        transportation_mode: Phương tiện
        semantic_query: Query ngữ nghĩa
        top_k_spatial: Số lượng kết quả spatial
        top_k_semantic: Số lượng kết quả semantic cuối cùng
    
    Returns:
        JSON response với kết quả spatial và semantic
    """
    try:
        result = semantic_service.search_combined(
            latitude=request.latitude,
            longitude=request.longitude,
            transportation_mode=request.transportation_mode,
            semantic_query=request.semantic_query,
            top_k_spatial=request.top_k_spatial,
            top_k_semantic=request.top_k_semantic
        )
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
