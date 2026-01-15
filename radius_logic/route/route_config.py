"""
Route Builder Configuration
Tất cả constants và config cho route building
"""
from typing import Dict

class RouteConfig:
    """Cấu hình cho Route Builder"""
    
    # Thời gian tham quan
    DEFAULT_STAY_TIME = 30  # phút
    
    # Tốc độ di chuyển theo phương tiện (km/h)
    TRANSPORTATION_SPEEDS = {
        "WALKING": 5,
        "BICYCLING": 15,
        "TRANSIT": 25,
        "FLEXIBLE": 30,
        "DRIVING": 40
    }
    
    # Food categories cần kiểm tra 3 level
    FOOD_CATEGORIES = ["Restaurant", "Bar", "Cafe & Bakery"]
    
    # Bán kính tìm kiếm POI cuối (phần trăm của max_radius)
    LAST_POI_RADIUS_THRESHOLDS = [0.2, 0.4, 0.6, 0.8, 1.0]
    
    # Score weights cho POI đầu tiên
    FIRST_POI_WEIGHTS = {
        "distance": 0.1,
        "similarity": 0.45,
        "rating": 0.45
    }
    
    # Score weights cho POI cuối
    LAST_POI_WEIGHTS = {
        "distance": 0.4,
        "similarity": 0.3,
        "rating": 0.3
    }
    
    # Score weights cho POI giữa (khi similarity >= 0.8)
    MIDDLE_POI_WEIGHTS_HIGH_SIMILARITY = {
        "distance": 0.15,
        "similarity": 0.3,
        "rating": 0.3,
        "bearing": 0.25
    }
    
    # Score weights cho POI giữa (khi similarity < 0.8)
    MIDDLE_POI_WEIGHTS_LOW_SIMILARITY = {
        "distance": 0.25,
        "similarity": 0.1,
        "rating": 0.4,
        "bearing": 0.25
    }
    
    # Ngưỡng similarity để phân loại high/low
    SIMILARITY_THRESHOLD = 0.8
    
    # Bearing score mặc định (trung tính)
    DEFAULT_BEARING_SCORE = 0.5
    
    # Earth radius (km) cho Haversine
    EARTH_RADIUS_KM = 6371
    
    # Default rating nếu không có
    DEFAULT_RATING = 0.5