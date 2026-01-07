"""
Location API
API endpoints cho tìm kiếm địa điểm theo tọa độ và phương tiện di chuyển (PostGIS)
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from config.config import Config
from fastapi import APIRouter, HTTPException
from pydantics.location import LocationSearchRequest
from services.location_service import LocationService

# Initialize router
router = APIRouter(prefix="/api/v1/locations", tags=["Location Search (PostGIS)"])

# Initialize service
location_service = LocationService(Config.get_db_connection_string())

@router.post("/search")
async def search_locations(request: LocationSearchRequest):
    """
    Tìm kiếm TẤT CẢ địa điểm gần nhất (>= 50) xung quanh tọa độ theo phương tiện di chuyển
    
    Args:
        latitude: Vĩ độ điểm trung tâm
        longitude: Kinh độ điểm trung tâm
        transportation_mode: Phương tiện (WALKING, BICYCLING, TRANSIT, FLEXIBLE, DRIVING)
    
    Returns:
        JSON response với danh sách TẤT CẢ địa điểm trong bán kính
    """
    try:
        result = location_service.find_nearest_locations(
            latitude=request.latitude,
            longitude=request.longitude,
            transportation_mode=request.transportation_mode
        )
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
