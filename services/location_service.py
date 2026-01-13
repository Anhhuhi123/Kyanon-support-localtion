"""
Location Service
Service layer xử lý logic nghiệp vụ cho tìm kiếm địa điểm theo tọa độ và phương tiện
Sử dụng H3 + Redis cache để tối ưu performance
"""
import time
from datetime import datetime
from typing import Optional
from config.config import Config
from typing import List, Dict, Any, Tuple
from radius_logic.h3_radius_search import H3RadiusSearch
from utils.time_utils import TimeUtils
import json

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
        redis_host =  Config.REDIS_HOST
        redis_port =  Config.REDIS_PORT
        self.h3_search = H3RadiusSearch(db_connection_string, redis_host, redis_port)
    
    def find_nearest_locations(
        self,
        latitude: float,
        longitude: float,
        transportation_mode: str,
        current_datetime: Optional[datetime] = None,
        max_time_minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Tìm TẤT CẢ địa điểm trong bán kính (>= 50) xung quanh tọa độ theo phương tiện di chuyển
        với tùy chọn lọc theo thời gian mở cửa
        
        Args:
            latitude: Vĩ độ điểm trung tâm
            longitude: Kinh độ điểm trung tâm
            transportation_mode: Phương tiện di chuyển (WALKING, BICYCLING, etc.)
            current_datetime: Thời điểm hiện tại của user (None = không lọc theo thời gian)
            max_time_minutes: Thời gian tối đa user có (phút) (None = không lọc)
            
        Returns:
            Dict chứa kết quả tìm kiếm với các field:
            - status: "success" hoặc "error"
            - transportation_mode: phương tiện đã sử dụng
            - center: tọa độ trung tâm
            - radius_used: bán kính cuối cùng đã dùng (mét)
            - total_results: số lượng điểm tìm thấy
            - filtered_by_time: True nếu đã lọc theo thời gian
            - time_window: {start, end} nếu có lọc theo thời gian
            - results: danh sách TẤT CẢ các điểm trong bán kính với các trường:
                * id: ID của POI
                * name: Tên địa điểm  
                * poi_type: Loại POI
                * address: Địa chỉ
                * distance_meters: Khoảng cách (mét)
                * lat, lon: Tọa độ
                * open_hours: Giờ mở cửa
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
            # print("abc")
            start_time = time.time()
            
            # Gọi H3 + Redis search: trả về TẤT CẢ địa điểm trong bán kính (>= 50)
            results, final_radius = self.h3_search.search_locations(
                latitude=latitude,
                longitude=longitude,
                transportation_mode=transportation_mode
            )
            # with open("results.json", "w", encoding="utf-8") as f:
            #     json.dump(results, f, ensure_ascii=False, indent=4)
            # print("result123",results)
            # Lọc theo thời gian nếu có current_datetime và max_time_minutes
            filtered_by_time = False
            time_window = None
            original_count = len(results)
            
            if current_datetime and max_time_minutes:
                from datetime import timedelta
                
                # Tính time window: [current_datetime, current_datetime + max_time_minutes]
                end_datetime = current_datetime + timedelta(minutes=max_time_minutes)
                time_window = {
                    "start": current_datetime.isoformat(),
                    "end": end_datetime.isoformat()
                }
                
                print(f"⏰ Filtering by time window: {current_datetime.strftime('%A %H:%M')} -> {end_datetime.strftime('%A %H:%M')}")
                
                # Lọc POI có overlap với time window
                results = TimeUtils.filter_open_pois(results, current_datetime, end_datetime)
                # with open("results1.json", "w", encoding="utf-8") as f:
                    # json.dump(results, f, ensure_ascii=False, indent=4)
                filtered_by_time = True
                 
                print(f"  📊 Before time filter: {original_count} POIs")
                print(f"  ✅ After time filter: {len(results)} POIs")
            
            execution_time = time.time() - start_time
            print(f"⏱️  H3 + Redis search executed in {execution_time:.3f}s")
            
            response = {
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
            
            # Thêm thông tin time filtering nếu có
            if filtered_by_time:
                response["filtered_by_time"] = True
                response["time_window"] = time_window
                response["original_results_count"] = original_count
            
            return response
            
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