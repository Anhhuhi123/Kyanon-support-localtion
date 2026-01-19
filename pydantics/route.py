from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID
class SemanticSearchRequest(BaseModel):
    """Request model cho tìm kiếm ngữ nghĩa (không cần filter ID)"""
    query: str = Field(..., description="Câu query tìm kiếm ngữ nghĩa", json_schema_extra={"example": "Travel"})
    top_k: Optional[int] = Field(10, description="Số lượng kết quả", json_schema_extra={"example": 10})


class CombinedSearchRequest(BaseModel):
    """Request model cho tìm kiếm kết hợp spatial + semantic"""
    latitude: float = Field(..., description="Vĩ độ", json_schema_extra={"example": 10.774087})
    longitude: float = Field(..., description="Kinh độ", json_schema_extra={"example": 106.703535})
    transportation_mode: str = Field(..., description="Phương tiện (WALKING/BICYCLING/TRANSIT/FLEXIBLE/DRIVING)", json_schema_extra={"example": "WALKING"})
    semantic_query: str = Field(..., description="Câu query ngữ nghĩa", json_schema_extra={"example": "Travel"})
    top_k: Optional[int] = Field(10, description="Số lượng kết quả semantic cuối cùng", json_schema_extra={"example": 10})


class RouteSearchRequest(BaseModel):
    """Request model cho tìm kiếm và xây dựng lộ trình"""
    user_id: Optional[UUID] = Field(
        None,
        example="816d05bf-5b65-49d2-9087-77c4c83be655"
    )
    latitude: float = Field(..., description="Vĩ độ user", json_schema_extra={"example": 10.774087})
    longitude: float = Field(..., description="Kinh độ user", json_schema_extra={"example": 106.703535})
    transportation_mode: str = Field(..., description="Phương tiện (WALKING/BICYCLING/TRANSIT/FLEXIBLE/DRIVING)", json_schema_extra={"example": "WALKING"})
    transportation_type: Optional[str] = Field(None, description="SOLO, GROUP, ...", json_schema_extra={"example": "SOLO"})
    semantic_query: str = Field(..., description="Câu query ngữ nghĩa (nhu cầu người dùng)", json_schema_extra={"example": "Food & Local Flavours"})
    customer_like: Optional[bool] = Field(None, description="Tự động thêm Entertainment nếu True", json_schema_extra={"example": True})
    current_time: Optional[datetime] = Field(None, description="Thời điểm hiện tại của user (ISO format). Nếu None, không lọc theo thời gian mở cửa", json_schema_extra={"example": "2026-01-13T08:00:00"})
    max_time_minutes: Optional[int] = Field(180, description="Thời gian tối đa (phút)", json_schema_extra={"example": 300})
    target_places: Optional[int] = Field(5, description="Số địa điểm mỗi lộ trình", json_schema_extra={"example": 5})
    max_routes: Optional[int] = Field(3, description="Số lộ trình tối đa", json_schema_extra={"example": 1})
    top_k_semantic: Optional[int] = Field(10, description="Số địa điểm từ semantic search", json_schema_extra={"example": 10})
    replace_route: Optional[int] = Field(None, description="Route ID cần replace. Nếu set, sẽ tạo route mới với POI IDs khác và xóa route cũ", json_schema_extra={"example": 1})
    delete_cache: Optional[bool] = Field(False, description="Xóa cache của user trước khi build routes mới", json_schema_extra={"example": False})
    duration: Optional[bool] = Field(False, description="Nếu True: chọn số điểm phù hợp trong max_time_minutes (không phụ thuộc target_places)", json_schema_extra={"example": True})



class UpdatePOIRequest(BaseModel):
    """Request model cho update POI trong route"""
    user_id: UUID = Field(..., description="UUID của user", json_schema_extra={"example": "816d05bf-5b65-49d2-9087-77c4c83be655"})
    route_id: str = Field(..., description="ID của route (từ cache)", json_schema_extra={"example": "1"})
    poi_id_to_replace: str = Field(..., description="ID của POI cần thay thế", json_schema_extra={"example": "123e4567-e89b-12d3-a456-426614174000"})
    current_time: Optional[datetime] = Field(None, description="Thời điểm hiện tại của user (ISO format). Nếu None, không lọc theo thời gian mở cửa", json_schema_extra={"example": "2026-01-13T08:00:00"})

