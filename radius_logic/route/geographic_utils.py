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

    def filter_perpendicular_candidates(
        self,
        candidates: List[int],
        prev_bearing: float,
        places: List[Dict[str, Any]],
        current_lat: float,
        current_lon: float,
        tolerance: float = 10.0
    ) -> Tuple[List[int], List[int]]:
        """
        Lọc candidates thành 2 nhóm: right turn (90°) và left turn (270°)
        
        Dùng cho circular routing để tìm POI tạo góc vuông với hướng di chuyển hiện tại.
        
        Args:
            candidates: List POI indices chưa sử dụng
            prev_bearing: Hướng di chuyển trước đó (0-360°)
            places: Danh sách POI đầy đủ
            current_lat: Latitude vị trí hiện tại
            current_lon: Longitude vị trí hiện tại
            tolerance: Dung sai góc (mặc định ±10°)
            
        Returns:
            (right_candidates, left_candidates): 
            - right_candidates: POI nằm ở góc 80-100° (rẽ phải)
            - left_candidates: POI nằm ở góc 260-280° (rẽ trái)
            
        Examples:
            >>> geo = GeographicUtils()
            >>> # prev_bearing = 0° (hướng Bắc)
            >>> # Rẽ phải = 90° (Đông), Rẽ trái = 270° (Tây)
            >>> right, left = geo.filter_perpendicular_candidates(
            ...     candidates=[0, 1, 2],
            ...     prev_bearing=0,
            ...     places=poi_list,
            ...     current_lat=21.0,
            ...     current_lon=105.0,
            ...     tolerance=10.0
            ... )
        """
        right_candidates = []  # 80-100° (right turn)
        left_candidates = []   # 260-280° (left turn)
        
        # Tính target bearings cho right và left turn
        target_right = (prev_bearing + 90) % 360  # Rẽ phải 90°
        target_left = (prev_bearing - 90) % 360   # Rẽ trái 90° (= +270°)
        
        for idx in candidates:
            poi = places[idx]
            
            # Tính bearing từ vị trí hiện tại đến POI này
            bearing_to_poi = self.calculate_bearing(
                current_lat, current_lon,
                poi["lat"], poi["lon"]
            )
            
            # Check right turn (90° ±tolerance)
            diff_right = self.calculate_bearing_difference(target_right, bearing_to_poi)
            if diff_right <= tolerance:
                right_candidates.append(idx)
            
            # Check left turn (270° ±tolerance)
            diff_left = self.calculate_bearing_difference(target_left, bearing_to_poi)
            if diff_left <= tolerance:
                left_candidates.append(idx)
        
        return right_candidates, left_candidates