"""
Location Service
Service layer xử lý logic nghiệp vụ cho tìm kiếm địa điểm theo tọa độ và phương tiện
"""

from typing import List, Dict, Any, Tuple
from Logic.radius_search import search_locations
from config.config import Config


class LocationService:
    """Service xử lý logic tìm kiếm địa điểm"""
    
    def __init__(self, db_connection_string: str):
        """
        Khởi tạo service với database connection string
        
        Args:
            db_connection_string: PostgreSQL connection string
        """
        self.db_connection_string = db_connection_string
    
    def find_nearest_locations(
        self,
        latitude: float,
        longitude: float,
        transportation_mode: str,
        top_k: int = None
    ) -> Dict[str, Any]:
        """
        Tìm k điểm gần nhất xung quanh tọa độ theo phương tiện di chuyển
        
        Args:
            latitude: Vĩ độ điểm trung tâm
            longitude: Kinh độ điểm trung tâm
            transportation_mode: Phương tiện di chuyển (WALKING, BICYCLING, etc.)
            top_k: Số lượng điểm muốn trả về (mặc định lấy từ Config.TOP_K_RESULTS)
            
        Returns:
            Dict chứa kết quả tìm kiếm với các field:
            - status: "success" hoặc "error"
            - transportation_mode: phương tiện đã sử dụng
            - center: tọa độ trung tâm
            - radius_used: bán kính cuối cùng đã dùng (mét)
            - total_results: số lượng điểm tìm thấy
            - results: danh sách các điểm với các trường:
                * id: ID của POI
                * name: Tên địa điểm  
                * poi_type: Loại POI
                * address: Địa chỉ
                * distance_meters: Khoảng cách (mét)
                * lat, lon: Tọa độ
        """
        # Validate transportation mode
        if not Config.validate_transportation_mode(transportation_mode):
            return {
                "status": "error",
                "error": f"Invalid transportation mode: {transportation_mode}",
                "valid_modes": list(Config.TRANSPORTATION_CONFIG.keys())
            }
        
        # Lấy top_k từ config nếu không được cung cấp
        if top_k is None:
            top_k = Config.TOP_K_RESULTS
        
        try:
            # Gọi hàm tìm kiếm từ Logic layer
            results, final_radius = search_locations(
                db_connection_string=self.db_connection_string,
                latitude=latitude,
                longitude=longitude,
                transportation_mode=transportation_mode,
                limit=top_k
            )
            
            return {
                "status": "success",
                "transportation_mode": transportation_mode,
                "center": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "radius_used": final_radius,
                "total_results": len(results),
                "results": results
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "transportation_mode": transportation_mode,
                "center": {
                    "latitude": latitude,
                    "longitude": longitude
                }
            }
