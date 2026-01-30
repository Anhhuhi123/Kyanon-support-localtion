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
        "BIKE": 15,
        "CAR": 25,
        "FLEXIBLE": 30
    }
    # Food categories cần kiểm tra 3 level
    FOOD_CATEGORIES = ["Restaurant", "Bar", "Cafe & Bakery"]
    
    # Bán kính tìm kiếm POI cuối (phần trăm của max_radius)
    LAST_POI_RADIUS_THRESHOLDS = [0.2, 0.4, 0.6, 0.8, 1.0]
    
    # Score weights cho POI đầu tiên
    FIRST_POI_WEIGHTS = {
        "distance": 0.5,
        "similarity": 0.1,
        "rating": 0.4
    }
    
    # Score weights cho POI cuối
    LAST_POI_WEIGHTS = {
        "distance": 0.6,
        "similarity": 0.1,
        "rating": 0.3
    }
    
    # Score weights cho POI giữa (khi similarity >= 0.8)
    MIDDLE_POI_WEIGHTS_HIGH_SIMILARITY = {
        "distance": 0.4,
        "similarity": 0.1,
        "rating": 0.25,
        "bearing": 0.25
    }
    
    # Score weights cho POI giữa (khi similarity < 0.8)
    MIDDLE_POI_WEIGHTS_LOW_SIMILARITY = {
        "distance": 0.4,
        "similarity": 0.1,
        "rating": 0.25,
        "bearing": 0.25
    }
    
    # Ngưỡng similarity để phân loại high/low
    SIMILARITY_THRESHOLD = 0.8
    
    # Bearing score mặc định (trung tính)
    DEFAULT_BEARING_SCORE = 0.5
    
    # Bearing range filter (cone-based POI selection)
    INITIAL_BEARING_RANGE = 90  # Bắt đầu với ±90° (tổng 180°, nửa vòng tròn phía trước)
    BEARING_RANGE_EXPANSION_STEP = 30  # Mở rộng thêm 30° mỗi lần
    MAX_BEARING_RANGE = 180  # Tối đa ±180° (toàn bộ 360°)
    
    # Earth radius (km) cho Haversine
    EARTH_RADIUS_KM = 6371
    
    # Default rating nếu không có
    DEFAULT_RATING = 0.5