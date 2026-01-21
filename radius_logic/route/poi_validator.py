"""
POI Validator
Logic kiểm tra và validate POI
"""
from typing import Dict, Any
from datetime import datetime
from utils.time_utils import TimeUtils
from .route_config import RouteConfig

class POIValidator:

    
    def get_stay_time(self, place: Dict[str, Any]) -> float:
        stay = place.get("stay_time")
        try:
            return float(stay) if stay is not None else RouteConfig.DEFAULT_STAY_TIME
        except (TypeError, ValueError):
            return RouteConfig.DEFAULT_STAY_TIME

    
    def is_poi_available_at_time(
        self,
        place: Dict[str, Any],
        arrival_datetime: datetime
    ) -> bool:
        """
        Kiểm tra POI có sẵn sàng tại thời điểm đến (có đủ thời gian stay)
        
        Args:
            place: POI cần kiểm tra
            arrival_datetime: Thời điểm đến POI
            
        Returns:
            True nếu POI mở cửa và có đủ thời gian stay
        """
        if not arrival_datetime:
            return True
        
        stay_time = self.get_stay_time(place)
        return TimeUtils.has_enough_time_to_stay(
            place.get('open_hours', []), 
            arrival_datetime, 
            stay_time
        )
    
    @staticmethod
    def is_same_food_type(place1: Dict[str, Any], place2: Dict[str, Any]) -> bool:
        """
        Kiểm tra xem 2 POI có giống nhau ở CẢ 3 level hay không
        (poi_type_clean, main_subcategory, specialization)
        
        Chỉ áp dụng cho Restaurant, Bar, Cafe & Bakery.
        Return True nếu GIỐNG NHAU ở cả 3 level -> KHÔNG cho phép liên tiếp
        
        Args:
            place1: POI thứ nhất
            place2: POI thứ hai
            
        Returns:
            True nếu giống nhau ở cả 3 level (không cho phép liên tiếp)
            False nếu khác nhau ở ít nhất 1 level (cho phép liên tiếp)
        """
        # Danh sách food categories cần kiểm tra
   
        
        # Lấy poi_type_clean
        poi_type1 = place1.get("poi_type_clean", "")
        poi_type2 = place2.get("poi_type_clean", "")
        
        # Nếu không phải food category, cho phép liên tiếp (return False)
        if poi_type1 not in RouteConfig.FOOD_CATEGORIES or poi_type2 not in RouteConfig.FOOD_CATEGORIES:
            return False
        
        # Level 1: So sánh poi_type_clean
        if poi_type1 != poi_type2:
            return False  # Khác nhau ở level 1 -> cho phép liên tiếp
        
        # Level 2: So sánh main_subcategory
        main_sub1 = place1.get("main_subcategory")
        main_sub2 = place2.get("main_subcategory")
        
        if main_sub1 != main_sub2:
            return False  # Khác nhau ở level 2 -> cho phép liên tiếp
        
        # Level 3: So sánh specialization
        spec1 = place1.get("specialization")
        spec2 = place2.get("specialization")
        
        if spec1 != spec2:
            return False  # Khác nhau ở level 3 -> cho phép liên tiếp
        
        # Giống nhau ở cả 3 level -> KHÔNG cho phép liên tiếp
        return True