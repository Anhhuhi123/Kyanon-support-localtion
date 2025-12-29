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
    transportation_mode: str,
    limit: int = 10
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Tìm kiếm địa điểm với bán kính tự động tăng dần theo phương tiện
    
    Bắt đầu từ min_radius, tăng dần theo step cho đến khi:
    - Tìm đủ limit địa điểm, HOẶC
    - Đạt max_radius
    
    Args:
        db_connection_string: PostgreSQL connection string
        latitude: Vĩ độ điểm trung tâm
        longitude: Kinh độ điểm trung tâm
        transportation_mode: Phương tiện (WALKING, BICYCLING, etc.)
        limit: Số lượng kết quả tối đa trả về
        
    Returns:
        Tuple (results, final_radius):
        - results: List các địa điểm tìm thấy
        - final_radius: Bán kính cuối cùng đã sử dụng
    """
    # Lấy config cho transportation mode
    config = Config.get_transportation_config(transportation_mode)
    min_radius = config["min_radius"]
    max_radius = config["max_radius"]
    step = config["step"]
    
    current_radius = min_radius
    results = []
    
    # Kết nối database
    conn = psycopg2.connect(db_connection_string)
    cursor = conn.cursor()
    
    try:
        # Tăng dần bán kính cho đến khi tìm đủ hoặc đạt max
        while current_radius <= max_radius:
            results = _query_locations_within_radius(
                cursor=cursor,
                latitude=latitude,
                longitude=longitude,
                radius_meters=current_radius,
                limit=limit
            )
            
            # Nếu đã tìm đủ limit kết quả thì dừng
            if len(results) >= limit:
                break
            
            # Tăng bán kính
            current_radius += step
        
        return results, current_radius
        
    finally:
        cursor.close()
        conn.close()


def _query_locations_within_radius(
    cursor,
    latitude: float,
    longitude: float,
    radius_meters: int,
    limit: int
) -> List[Dict[str, Any]]:
    """
    Query địa điểm trong bán kính cụ thể (hàm nội bộ)
    
    Args:
        cursor: Database cursor
        latitude: Vĩ độ điểm trung tâm
        longitude: Kinh độ điểm trung tâm
        radius_meters: Bán kính tìm kiếm (mét)
        limit: Số lượng kết quả tối đa
        
    Returns:
        List các địa điểm tìm thấy với thông tin:
        - id: ID của POI
        - name: Tên địa điểm
        - poi_type: Loại POI
        - address: Địa chỉ
        - distance_meters: Khoảng cách (mét)
        - lat, lon: Tọa độ
    """
    # Tạo point từ lat/lon
    point_wkt = f"POINT({longitude} {latitude})"
    
    # Query địa điểm trong bán kính
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
        LIMIT %s
    """
    
    params = [point_wkt, point_wkt, radius_meters, limit]
    
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
