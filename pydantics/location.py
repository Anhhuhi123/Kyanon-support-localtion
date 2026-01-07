from pydantic import BaseModel, Field

class LocationSearchRequest(BaseModel):
    """Request model cho tìm kiếm địa điểm (trả về TẤT CẢ địa điểm trong bán kính >= 50)"""
    latitude: float = Field(..., description="Vĩ độ", json_schema_extra={"example": 10.8294811})
    longitude: float = Field(..., description="Kinh độ", json_schema_extra={"example": 106.7737852})
    transportation_mode: str = Field(..., description="Phương tiện (WALKING/BICYCLING/TRANSIT/FLEXIBLE/DRIVING)", json_schema_extra={"example": "WALKING"})