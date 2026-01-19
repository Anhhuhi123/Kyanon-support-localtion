"""
POI Update Logic
Xử lý logic cập nhật POI trong route: chọn POI mới, tính khoảng cách và thời gian
"""
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime
from radius_logic.route.geographic_utils import GeographicUtils


class POIUpdateService:
    """Service xử lý logic update POI trong route"""
    
    def __init__(self):
        self.geo_utils = GeographicUtils()
    
    
    def select_top_n_pois(
        self,
        candidate_pois: List[Dict[str, Any]],
        n: int = 3,
        current_datetime: Optional[datetime] = None,
        reference_point: Optional[Tuple[float, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Chọn top N POI tốt nhất từ danh sách candidates dựa trên distance + rating
        
        Args:
            candidate_pois: Danh sách POI candidates
            n: Số lượng POI cần trả về (default 3)
            current_datetime: Thời điểm hiện tại (để validate opening hours)
            reference_point: Tọa độ tham chiếu (lat, lon) để tính khoảng cách
            
        Returns:
            Danh sách top N POI (có thể ít hơn N nếu không đủ candidates)
        """
        if not candidate_pois:
            return []
        
        # Validate opening hours nếu có current_datetime (không bắt buộc)
        valid_pois = []
        invalid_pois = []
        
        if current_datetime:
            from utils.time_utils import TimeUtils
            for poi in candidate_pois:
                open_hours = TimeUtils.normalize_open_hours(poi.get('open_hours'))
                if TimeUtils.is_open_at_time(open_hours, current_datetime):
                    valid_pois.append(poi)
                else:
                    invalid_pois.append(poi)
            
            # Ưu tiên POI mở cửa, nhưng vẫn xem xét POI đóng cửa nếu không đủ
            candidate_pois = valid_pois + invalid_pois
        
        if not candidate_pois:
            return []
        
        # Nếu có reference_point thì tính combined score (distance + rating)
        if reference_point:
            from radius_logic.route.route_config import RouteConfig
            
            ref_lat, ref_lon = reference_point
            scored_pois = []
            
            # Tìm max distance để normalize
            max_distance = 0
            for poi in candidate_pois:
                if poi.get('lat') is not None and poi.get('lon') is not None:
                    dist = self.geo_utils.calculate_distance_haversine(
                        ref_lat, ref_lon, poi['lat'], poi['lon']
                    )
                    max_distance = max(max_distance, dist)
            
            # Tính combined score cho từng POI
            for poi in candidate_pois:
                if poi.get('lat') is None or poi.get('lon') is None:
                    continue
                
                # Tính distance
                distance_km = self.geo_utils.calculate_distance_haversine(
                    ref_lat, ref_lon, poi['lat'], poi['lon']
                )
                
                # Normalize distance (đảo ngược: gần = điểm cao)
                normalized_distance = distance_km / max_distance if max_distance > 0 else 0
                distance_score = 1 - normalized_distance
                
                # Rating (đã normalize 0-1)
                rating = float(poi.get('rating', RouteConfig.DEFAULT_RATING))
                
                # Combined score: 60% rating + 40% distance
                combined_score = 0.6 * rating + 0.4 * distance_score
                
                scored_pois.append((poi, combined_score))
            
            if not scored_pois:
                return []
            
            # Sắp xếp theo combined score (cao hơn = tốt hơn)
            scored_pois.sort(key=lambda x: -x[1])
            return [poi for poi, score in scored_pois[:n]]
        
        # Nếu không có reference_point, chọn theo rating cao nhất
        from radius_logic.route.route_config import RouteConfig
        candidate_pois.sort(key=lambda p: -float(p.get('rating', RouteConfig.DEFAULT_RATING)))
        return candidate_pois[:n]
    
    def calculate_distance_changes(
        self,
        old_poi_data: Dict[str, Any],
        new_poi_data: Dict[str, Any],
        prev_poi_data: Optional[Dict[str, Any]] = None,
        next_poi_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Tính toán thay đổi khoảng cách khi thay POI
        
        Args:
            old_poi_data: Thông tin POI cũ (bị thay thế)
            new_poi_data: Thông tin POI mới
            prev_poi_data: Thông tin POI trước đó (None nếu là POI đầu tiên)
            next_poi_data: Thông tin POI tiếp theo (None nếu là POI cuối)
            
        Returns:
            Dict chứa thông tin thay đổi khoảng cách
        """
        distance_changes = {}
        
        # Tính distance với POI trước (nếu có)
        if prev_poi_data:
            old_distance = self.geo_utils.calculate_distance_haversine(
                prev_poi_data['lat'], prev_poi_data['lon'],
                old_poi_data['lat'], old_poi_data['lon']
            )
            
            new_distance = self.geo_utils.calculate_distance_haversine(
                prev_poi_data['lat'], prev_poi_data['lon'],
                new_poi_data['lat'], new_poi_data['lon']
            )
            
            distance_changes['from_previous'] = {
                'old_distance_km': round(old_distance, 2),
                'new_distance_km': round(new_distance, 2),
                'difference_km': round(new_distance - old_distance, 2)
            }
        
        # Tính distance với POI sau (nếu có)
        if next_poi_data:
            old_distance = self.geo_utils.calculate_distance_haversine(
                old_poi_data['lat'], old_poi_data['lon'],
                next_poi_data['lat'], next_poi_data['lon']
            )
            
            new_distance = self.geo_utils.calculate_distance_haversine(
                new_poi_data['lat'], new_poi_data['lon'],
                next_poi_data['lat'], next_poi_data['lon']
            )
            
            distance_changes['to_next'] = {
                'old_distance_km': round(old_distance, 2),
                'new_distance_km': round(new_distance, 2),
                'difference_km': round(new_distance - old_distance, 2)
            }
        
        return distance_changes
    
    def calculate_travel_time_changes(
        self,
        distance_changes: Dict[str, Any],
        transportation_mode: str = "driving"
    ) -> Dict[str, Any]:
        """
        Tính toán thay đổi thời gian di chuyển dựa trên khoảng cách
        
        Args:
            distance_changes: Dict chứa thông tin thay đổi khoảng cách
            transportation_mode: Phương tiện di chuyển (DRIVING, WALKING, BICYCLING, etc.)
            
        Returns:
            Dict chứa thông tin thay đổi thời gian
        """
        from radius_logic.route.route_config import RouteConfig
        
        # Sử dụng speeds từ RouteConfig
        speed = RouteConfig.TRANSPORTATION_SPEEDS.get(transportation_mode.upper(), 40)
        time_changes = {}
        
        # Tính time với POI trước
        if 'from_previous' in distance_changes:
            old_time = (distance_changes['from_previous']['old_distance_km'] / speed) * 60  # minutes
            new_time = (distance_changes['from_previous']['new_distance_km'] / speed) * 60
            
            time_changes['from_previous'] = {
                'old_time_minutes': round(old_time, 1),
                'new_time_minutes': round(new_time, 1),
                'difference_minutes': round(new_time - old_time, 1)
            }
        
        # Tính time với POI sau
        if 'to_next' in distance_changes:
            old_time = (distance_changes['to_next']['old_distance_km'] / speed) * 60
            new_time = (distance_changes['to_next']['new_distance_km'] / speed) * 60
            
            time_changes['to_next'] = {
                'old_time_minutes': round(old_time, 1),
                'new_time_minutes': round(new_time, 1),
                'difference_minutes': round(new_time - old_time, 1)
            }
        
        return time_changes
    
    def format_poi_for_response(
        self,
        poi_id: str,
        poi_data: Dict[str, Any],
        category: str,
        order: int
    ) -> Dict[str, Any]:
        """
        Format POI data cho response
        
        Args:
            poi_id: ID của POI
            poi_data: Raw POI data
            category: Category của POI
            order: Thứ tự trong route
            
        Returns:
            Dict chứa POI data đã format
        """
        return {
            "place_id": poi_id,
            "place_name": poi_data.get('name', 'N/A'),
            "poi_type": poi_data.get('poi_type', ''),
            "poi_type_clean": poi_data.get('poi_type_clean', ''),
            "main_subcategory": poi_data.get('main_subcategory'),
            "specialization": poi_data.get('specialization'),
            "category": category,
            "address": poi_data.get('address', ''),
            "lat": poi_data.get('lat'),
            "lon": poi_data.get('lon'),
            "rating": poi_data.get('rating', 0.5),
            "open_hours": poi_data.get('open_hours', []),
            "order": order
        }
