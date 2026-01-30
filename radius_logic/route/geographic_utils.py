"""
Geographic Utilities
Các hàm tính toán địa lý: distance, bearing, etc.
"""
import math
from typing import List, Tuple, Dict, Any
from .route_config import RouteConfig

class GeographicUtils:

    @staticmethod
    def calculate_distance_haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Tính khoảng cách Haversine giữa 2 điểm (km)
        NHANH HƠN PostGIS rất nhiều (không cần connect DB)
        Đủ chính xác cho khoảng cách ngắn (< 100km)
        
        Args:
            lat1, lon1: Tọa độ điểm 1
            lat2, lon2: Tọa độ điểm 2
            
        Returns:
            Khoảng cách (km)
        """
        R = RouteConfig.EARTH_RADIUS_KM  # Bán kính trái đất (km)
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c


    @staticmethod
    def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Tính hướng (bearing) từ điểm 1 đến điểm 2 (độ, 0-360)
        0° = Bắc, 90° = Đông, 180° = Nam, 270° = Tây
        
        Args:
            lat1, lon1: Tọa độ điểm 1
            lat2, lon2: Tọa độ điểm 2
            
        Returns:
            Bearing (độ, 0-360)
        """
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lon = math.radians(lon2 - lon1)
        
        x = math.sin(delta_lon) * math.cos(lat2_rad)
        y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon)
        
        bearing_rad = math.atan2(x, y)
        bearing_deg = math.degrees(bearing_rad)
        
        # Chuyển về 0-360
        return (bearing_deg + 360) % 360


    @staticmethod
    def calculate_bearing_difference(bearing1: float, bearing2: float) -> float:
        """
        Tính độ chênh lệch góc giữa 2 hướng (0-180 độ)
        
        Args:
            bearing1: Hướng 1 (độ)
            bearing2: Hướng 2 (độ)
            
        Returns:
            Độ chênh lệch (0-180 độ). 0 = cùng hướng, 180 = ngược hướng
        """
        diff = abs(bearing1 - bearing2)
        if diff > 180:
            diff = 360 - diff
        return diff

    @staticmethod
    def is_poi_in_bearing_range(
        current_lat: float, 
        current_lon: float,
        poi_lat: float,
        poi_lon: float,
        target_bearing: float,
        bearing_range: float
    ) -> bool:
        """
        Kiểm tra POI có nằm trong phạm vi góc cho phép hay không
        
        Args:
            current_lat, current_lon: Vị trí hiện tại
            poi_lat, poi_lon: Vị trí POI cần kiểm tra
            target_bearing: Hướng mục tiêu (độ, 0-360)
            bearing_range: Phạm vi góc cho phép (±degrees)
                          Ví dụ: 90 = ±90° (chấp nhận POI trong nửa vòng tròn phía trước)
        
        Returns:
            True nếu POI nằm trong phạm vi, False nếu không
        """
        # Tính bearing từ vị trí hiện tại đến POI
        poi_bearing = GeographicUtils.calculate_bearing(
            current_lat, current_lon, poi_lat, poi_lon
        )
        
        # Tính góc chênh lệch
        bearing_diff = GeographicUtils.calculate_bearing_difference(
            target_bearing, poi_bearing
        )
        
        # Kiểm tra xem góc chênh lệch có nằm trong phạm vi cho phép không
        return bearing_diff <= bearing_range

    def build_distance_matrix(
        self,
        user_location: Tuple[float, float],
        places: List[Dict[str, Any]]
    ) -> List[List[float]]:
        """
        Xây dựng ma trận khoảng cách sử dụng Haversine (NHANH)
        
        Args:
            user_location: (lat, lon) của user
            places: Danh sách địa điểm
            
        Returns:
            Ma trận khoảng cách [n+1][n+1] (index 0 là user)
        """
        n = len(places)
        matrix = [[0.0] * (n + 1) for _ in range(n + 1)]
        
        # Tọa độ tất cả điểm (0 = user, 1-n = places)
        coords = [user_location] + [(p["lat"], p["lon"]) for p in places]
        
        # Tính khoảng cách giữa mọi cặp điểm bằng Haversine (NHANH)
        for i in range(n + 1):
            for j in range(i + 1, n + 1):  # Chỉ tính nửa trên, copy sang nửa dưới
                dist = self.calculate_distance_haversine(
                    coords[i][0], coords[i][1],
                    coords[j][0], coords[j][1]
                )
                matrix[i][j] = dist
                matrix[j][i] = dist  # Ma trận đối xứng
        
        return matrix
    
    