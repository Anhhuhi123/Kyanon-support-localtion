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
    
    def select_best_poi(
        self,
        candidate_pois: List[Dict[str, Any]],
        current_datetime: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Chọn POI tốt nhất từ danh sách candidates
        
        Args:
            candidate_pois: Danh sách POI candidates
            current_datetime: Thời điểm hiện tại (để validate opening hours)
            
        Returns:
            POI được chọn hoặc None nếu không có POI phù hợp
        """
        if not candidate_pois:
            return None
        
        # Validate opening hours nếu có current_datetime
        if current_datetime:
            from utils.time_utils import TimeUtils
            valid_pois = []
            
            for poi in candidate_pois:
                # Normalize open_hours nếu cần
                open_hours = TimeUtils.normalize_open_hours(poi.get('open_hours'))
                if TimeUtils.is_open_at_time(open_hours, current_datetime):
                    valid_pois.append(poi)
            
            if not valid_pois:
                return None
            
            candidate_pois = valid_pois
        
        # TODO: Có thể thêm logic ranking phức tạp hơn (rating, distance, popularity...)
        # Hiện tại chọn POI đầu tiên
        return candidate_pois[0]
    
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
            transportation_mode: Phương tiện di chuyển (driving, walking, cycling)
            
        Returns:
            Dict chứa thông tin thay đổi thời gian
        """
        # Average speeds (km/h)
        speeds = {
            "driving": 40,
            "walking": 5,
            "cycling": 15
        }
        
        speed = speeds.get(transportation_mode, 40)
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
