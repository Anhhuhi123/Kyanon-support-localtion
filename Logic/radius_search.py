"""
Radius Search Functions
Các hàm tiện ích để tìm kiếm địa điểm trong bán kính theo phương tiện di chuyển
"""

import psycopg2
from typing import List, Dict, Any, Tuple
from config.config import Config


def search_locations(
    db_connection_string: str,
    latitude: float,
    longitude: float,
    transportation_mode: str
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Tìm kiếm TẤT CẢ địa điểm trong bán kính tăng dần cho đến khi >= 50 điểm
    
    Bắt đầu từ min_radius, tăng dần theo step cho đến khi:
    - Tìm được ít nhất 50 địa điểm, HOẶC
    - Đạt max_radius
    
    Args:
        db_connection_string: PostgreSQL connection string
        latitude: Vĩ độ điểm trung tâm
        longitude: Kinh độ điểm trung tâm
        transportation_mode: Phương tiện (WALKING, BICYCLING, etc.)
        
    Returns:
        Tuple (results, final_radius):
        - results: List TẤT CẢ các địa điểm trong bán kính (>= 50 nếu có đủ)
        - final_radius: Bán kính cuối cùng đã sử dụng
    """
    # Lấy config cho transportation mode
    config = Config.get_transportation_config(transportation_mode)
    min_radius = config["min_radius"]
    max_radius = config["max_radius"]
    step = config["step"]
    
    MIN_REQUIRED_RESULTS = 50  # Số lượng tối thiểu phải tìm được
    
    current_radius = min_radius
    results = []
    
    # Kết nối database
    conn = psycopg2.connect(db_connection_string)
    cursor = conn.cursor()
    
    try:
        # Tăng dần bán kính cho đến khi có >= 50 điểm hoặc đạt max
        while current_radius <= max_radius:
            results = _query_locations_within_radius(
                cursor=cursor,
                latitude=latitude,
                longitude=longitude,
                radius_meters=current_radius
            )
            
            # Nếu đã tìm được >= 50 kết quả thì dừng
            if len(results) >= MIN_REQUIRED_RESULTS:
                print(f"Found {len(results)} locations (target: >= {MIN_REQUIRED_RESULTS}), stopping at radius {current_radius}m")
                break
            
            # Tăng bán kính
            print(f"Found {len(results)} locations (< {MIN_REQUIRED_RESULTS}), increasing radius to {current_radius + step}m")
            current_radius += step
        
        # Warning nếu đạt max mà chưa đủ
        if len(results) < MIN_REQUIRED_RESULTS:
            print(f"⚠️  WARNING: Reached max_radius ({max_radius}m) but only found {len(results)} locations (target: >= {MIN_REQUIRED_RESULTS})")
            print(f"    Consider: 1) Increasing max_radius, 2) Check if database has enough data in this area")
        
        return results, current_radius
        
    finally:
        cursor.close()
        conn.close()


def _query_locations_within_radius(
    cursor,
    latitude: float,
    longitude: float,
    radius_meters: int
) -> List[Dict[str, Any]]:
    """
    Query TẤT CẢ địa điểm trong bán kính cụ thể (hàm nội bộ)
    
    Args:
        cursor: Database cursor
        latitude: Vĩ độ điểm trung tâm
        longitude: Kinh độ điểm trung tâm
        radius_meters: Bán kính tìm kiếm (mét)
        
    Returns:
        List TẤT CẢ các địa điểm trong bán kính với thông tin:
        - id: ID của POI
        - name: Tên địa điểm
        - poi_type: Loại POI
        - address: Địa chỉ
        - distance_meters: Khoảng cách (mét)
        - lat, lon: Tọa độ
    """
    # Tạo point từ lat/lon
    point_wkt = f"POINT({longitude} {latitude})"
    
    # Query TẤT CẢ địa điểm trong bán kính (không giới hạn LIMIT)
    query = """
        SELECT 
            id,
            name,
            poi_type,
            address,
            ST_Distance(
                geom::geography,
                ST_GeomFromText(%s, 4326)::geography
            ) AS distance_meters,
            lat,
            long
        FROM poi_locations
        WHERE ST_DWithin(
            geom::geography,
            ST_GeomFromText(%s, 4326)::geography,
            %s
        )
        ORDER BY distance_meters ASC
    """
    
    params = [point_wkt, point_wkt, radius_meters]
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    # Convert sang list of dict
    return [
        {
            "id": row[0],
            "name": row[1],
            "poi_type": row[2],
            "address": row[3],
            "distance_meters": round(row[4], 2),
            "lat": row[5],
            "lon": row[6]
        }
        for row in rows
    ]
