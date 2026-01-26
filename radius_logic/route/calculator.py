"""
Score Calculator
Logic tính điểm kết hợp cho POI
"""
from typing import List, Dict, Any, Tuple, Optional
from .route_config import RouteConfig
from .geographic_utils import GeographicUtils

class Calculator:

    def __init__(self, geographic_utils: GeographicUtils):
        self.geo = geographic_utils

    def calculate_travel_time(self, distance_km: float, transportation_mode: str) -> float:
        """
        Tính thời gian di chuyển (phút)
        
        Args:
            distance_km: Khoảng cách (km)
            transportation_mode: Phương tiện
            
        Returns:
            Thời gian (phút)
        """
        speed = RouteConfig.TRANSPORTATION_SPEEDS.get(transportation_mode.upper(), 30)
        return (distance_km / speed) * 60  # Chuyển giờ sang phút
    
    def get_stay_time(self, poi_type: str, stay_time: Optional[float] = None) -> float:
        if stay_time is not None:
            try:
                return float(stay_time)
            except (TypeError, ValueError):
                pass
        return RouteConfig.DEFAULT_STAY_TIME

    def calculate_combined_score(
        self,
        place_idx: int,
        current_pos: int,
        places: List[Dict[str, Any]],
        distance_matrix: List[List[float]],
        max_distance: float,
        is_first: bool = False,
        is_last: bool = False,
        start_pos_index: Optional[int] = None,
        prev_bearing: Optional[float] = None,
        user_location: Optional[Tuple[float, float]] = None
    ) -> float:
        """
        Tính điểm kết hợp: distance + similarity + rating + bearing (hướng)
        
        Công thức:
        - POI đầu: 0.1*distance + 0.45*similarity + 0.45*rating
        - POI giữa: thêm yếu tố bearing để tránh zíc zắc
          + Nếu similarity >= 0.8: 0.15*distance + 0.5*similarity + 0.3*rating + 0.05*bearing
          + Nếu similarity < 0.8:  0.25*distance + 0.1*similarity + 0.4*rating + 0.25*bearing
        - POI cuối: ưu tiên gần user (0.4*distance + 0.3*similarity + 0.3*rating)
        
        Args:
            place_idx: Index địa điểm cần tính (0-based trong places list)
            current_pos: Vị trí hiện tại (0 = user, 1-n = places)
            places: Danh sách địa điểm
            distance_matrix: Ma trận khoảng cách
            max_distance: Khoảng cách tối đa để normalize
            is_first: Có phải POI đầu tiên không
            is_last: Có phải POI cuối cùng không
            prev_bearing: Hướng di chuyển trước đó (cho POI giữa)
            user_location: Tọa độ user (lat, lon) để tính bearing
            
        Returns:
            Combined score (cao hơn = tốt hơn)
        """
        place = places[place_idx]
        
        # similarity (score từ Qdrant, đã normalize 0-1)
        similarity = place["score"]
        
        # rating (normalize_stars_reviews từ DB, đã normalize 0-1)
        rating = float(place.get("rating") or RouteConfig.DEFAULT_RATING)
        
        # Nếu là POI cuối, tính khoảng cách từ place đến user (index 0)
        # Ngược lại tính khoảng cách từ current_pos đến place
        if is_last:
            distance_km = distance_matrix[place_idx + 1][0]  # Khoảng cách place -> user
        else:
            distance_km = distance_matrix[current_pos][place_idx + 1]  # Khoảng cách current -> place
        
        # Normalize distance (đảo ngược: gần = điểm cao)
        normalized_distance = distance_km / max_distance if max_distance > 0 else 0
        distance_score = 1 - normalized_distance
        
        # Tính bearing score (chỉ cho POI giữa)
        bearing_score = RouteConfig.DEFAULT_BEARING_SCORE  # Mặc định trung tính
        if not is_first and not is_last and prev_bearing is not None and user_location:
            # Lấy tọa độ điểm hiện tại và điểm tiếp theo
            if current_pos == 0:  # Từ user
                current_lat, current_lon = user_location
            else:
                current_place = places[current_pos - 1]
                current_lat, current_lon = current_place["lat"], current_place["lon"]
            
            next_place = places[place_idx]
            next_lat, next_lon = next_place["lat"], next_place["lon"]
            
            # Tính hướng từ điểm hiện tại đến điểm tiếp theo
            current_bearing = self.geo.calculate_bearing(current_lat, current_lon, next_lat, next_lon)
            
            # Tính độ chênh lệch góc (0-180)
            bearing_diff = self.geo.calculate_bearing_difference(prev_bearing, current_bearing)
            
            # Chuyển thành điểm: 0° (cùng hướng) = 1.0, 180° (ngược hướng) = 0.0
            bearing_score = 1.0 - (bearing_diff / 180.0)
        
        # Tính combined score theo công thức
        if is_first:
            # POI đầu: 0.1*distance + 0.45*similarity + 0.45*rating
            weights = RouteConfig.FIRST_POI_WEIGHTS
            combined = (
                weights["distance"] * distance_score +
                weights["similarity"] * similarity +
                weights["rating"] * rating
            )
        elif is_last:
            # POI cuối: ưu tiên gần user
            weights = RouteConfig.LAST_POI_WEIGHTS
            combined = (
                weights["distance"] * distance_score +
                weights["similarity"] * similarity +
                weights["rating"] * rating
            )
        else:
            # POI giữa: thêm yếu tố bearing để tránh zíc zắc
            if similarity >= RouteConfig.SIMILARITY_THRESHOLD:
                weights = RouteConfig.MIDDLE_POI_WEIGHTS_HIGH_SIMILARITY
                combined = (
                weights["distance"] * distance_score +
                weights["similarity"] * similarity +
                weights["rating"] * rating +
                weights["bearing"] * bearing_score
            )
            else:
                weights = RouteConfig.MIDDLE_POI_WEIGHTS_LOW_SIMILARITY
                combined = (
                weights["distance"] * distance_score +
                weights["similarity"] * similarity +
                weights["rating"] * rating +
                weights["bearing"] * bearing_score
            )
        
        return combined

    