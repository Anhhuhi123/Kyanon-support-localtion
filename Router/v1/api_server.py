"""
Location Search API Server
API endpoint để tìm kiếm địa điểm theo tọa độ và phương tiện di chuyển
"""
import sys
import os
# Thêm thư mục gốc vào sys.path để import được các module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from Service.location_service import LocationService
from config.config import Config

# Validate config
Config.validate()

# Initialize FastAPI app
app = FastAPI(
    title="Location Search API",
    description="API tìm kiếm địa điểm gần nhất theo tọa độ và phương tiện di chuyển",
    version="1.0.0"
)

# Initialize service
location_service = LocationService(Config.get_db_connection_string())


# Request Models
class LocationSearchRequest(BaseModel):
    """Request model cho tìm kiếm địa điểm"""
    latitude: float = Field(..., description="Vĩ độ", json_schema_extra={"example": 10.8294811})
    longitude: float = Field(..., description="Kinh độ", json_schema_extra={"example": 106.7737852})
    transportation_mode: str = Field(..., description="Phương tiện (WALKING/BICYCLING/TRANSIT/FLEXIBLE/DRIVING)", json_schema_extra={"example": "WALKING"})
    top_k: Optional[int] = Field(None, description="Số lượng kết quả", json_schema_extra={"example": 10})


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Location Search API",
        "version": "1.0.0",
        "endpoints": {
            "search": "/api/v1/locations/search",
            "health": "/health",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Location Search API"
    }


@app.post("/api/v1/locations/search")
async def search_locations(request: LocationSearchRequest):
    """
    Tìm kiếm k điểm gần nhất xung quanh tọa độ theo phương tiện di chuyển
    
    Args:
        latitude: Vĩ độ điểm trung tâm
        longitude: Kinh độ điểm trung tâm
        transportation_mode: Phương tiện (WALKING, BICYCLING, TRANSIT, FLEXIBLE, DRIVING)
        top_k: Số lượng điểm muốn trả về (optional, mặc định từ config)
    
    Returns:
        JSON response với danh sách địa điểm gần nhất
    """
    try:
        result = location_service.find_nearest_locations(
            latitude=request.latitude,
            longitude=request.longitude,
            transportation_mode=request.transportation_mode,
            top_k=request.top_k
        )
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
