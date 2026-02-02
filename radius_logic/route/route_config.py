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
    
    # Earth radius (km) cho Haversine
    EARTH_RADIUS_KM = 6371
    
    # Default rating nếu không có
    DEFAULT_RATING = 0.5
    
    # ============================================================
    # CIRCULAR ROUTING CONFIG (90° turns instead of straight)
    # ============================================================
    
    # Enable/disable circular routing (False = zigzag/straight, True = circular/90°)
    USE_CIRCULAR_ROUTING = True
    
    # Tolerance for 90° turns (±degrees)
    # - 5° = strict (85-95°, 265-275°) → route vuông vức
    # - 10° = moderate (80-100°, 260-280°) → route cân bằng
    # - 20° = loose (70-110°, 250-290°) → route linh hoạt
    CIRCULAR_ANGLE_TOLERANCE = 10.0
    
    # Prefer right turn when both right and left candidates available
    CIRCULAR_PREFER_RIGHT_TURN = True
    
    # Direction preference for circular routing
    # Options:
    # - "right": Always turn right (clockwise route)
    # - "left": Always turn left (counter-clockwise route)
    # - "auto": Automatically pick direction with more POI candidates from first POI
    CIRCULAR_DIRECTION_PREFERENCE = "auto"
    
    # Bearing score weights cho circular routing (middle POI)
    # Tăng weight của bearing để ép POI theo góc 90°
    MIDDLE_POI_WEIGHTS_CIRCULAR = {
        "distance": 0.3,
        "similarity": 0.1,
        "rating": 0.2,
        "bearing": 0.4  # Tăng weight để ưu tiên 90°
    }
    
    # Bearing score weights cho circular routing (last POI)
    LAST_POI_WEIGHTS_CIRCULAR = {
        "distance": 0.4,
        "similarity": 0.1,
        "rating": 0.2,
        "bearing": 0.3  # Vẫn ưu tiên gần user nhưng có bearing
    }