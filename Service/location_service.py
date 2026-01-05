"""
Location Service
Service layer xử lý logic nghiệp vụ cho tìm kiếm địa điểm theo tọa độ và phương tiện
Sử dụng H3 + Redis cache để tối ưu performance
"""

import time
from typing import List, Dict, Any, Tuple
from Logic.h3_radius_search import H3RadiusSearch
from config.config import Config


class LocationService:
    """Service xử lý logic tìm kiếm địa điểm với H3 + Redis cache"""
    
    def __init__(self, db_connection_string: str, redis_host: str = "localhost", redis_port: int = 6379):
        """
        Khởi tạo service với database và Redis connection
        
        Args:
            db_connection_string: PostgreSQL connection string
            redis_host: Redis host
            redis_port: Redis port
        """
        self.db_connection_string = db_connection_string
        self.h3_search = H3RadiusSearch(db_connection_string, redis_host, redis_port)
    
    def find_nearest_locations(
        self,
        latitude: float,
        longitude: float,
        transportation_mode: str
    ) -> Dict[str, Any]:
        """
        Tìm TẤT CẢ địa điểm trong bán kính (>= 50) xung quanh tọa độ theo phương tiện di chuyển
        
        Args:
            latitude: Vĩ độ điểm trung tâm
            longitude: Kinh độ điểm trung tâm
            transportation_mode: Phương tiện di chuyển (WALKING, BICYCLING, etc.)
            
        Returns:
            Dict chứa kết quả tìm kiếm với các field:
            - status: "success" hoặc "error"
            - transportation_mode: phương tiện đã sử dụng
            - center: tọa độ trung tâm
            - radius_used: bán kính cuối cùng đã dùng (mét)
            - total_results: số lượng điểm tìm thấy (>= 50 nếu có đủ)
            - results: danh sách TẤT CẢ các điểm trong bán kính với các trường:
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
        
        try:
            # Đo thời gian thực thi
            start_time = time.time()
            
            # Gọi H3 + Redis search: trả về TẤT CẢ địa điểm trong bán kính (>= 50)
            results, final_radius = self.h3_search.search_locations(
                latitude=latitude,
                longitude=longitude,
                transportation_mode=transportation_mode
            )
            
            execution_time = time.time() - start_time
            print(f"⏱️  H3 + Redis search executed in {execution_time:.3f}s")
            
            return {
                "status": "success",
                "transportation_mode": transportation_mode,
                "center": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "radius_used": final_radius,
                "total_results": len(results),
                "execution_time_seconds": round(execution_time, 3),
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
